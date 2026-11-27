use crate::adapter::{AdapterError, Event, StreamKind};
use crate::proxy::{Proxy, ProxyStream};
use crate::unit::qty::QtyNormalization;
use crate::{Ticker, TickerInfo, Trade, UnixMs};

use bytes::Bytes;
use fastwebsockets::{
    FragmentCollectorRead, Frame, OpCode, Payload, WebSocket, WebSocketWrite,
};
use http_body_util::Empty;
use hyper::{
    Request,
    header::{CONNECTION, UPGRADE},
    upgrade::Upgraded,
};
use hyper_util::rt::{TokioExecutor, TokioIo};
use rustc_hash::FxHashMap;
use tokio::io::{AsyncRead, AsyncWrite};
use tokio::time::Instant;
use tokio_rustls::{
    TlsConnector,
    rustls::{ClientConfig, pki_types::ServerName},
};
use url::Url;

use futures::StreamExt;
#[cfg(not(feature = "unbounded-channel"))]
use futures::channel::mpsc::Sender;
use futures::channel::mpsc::{UnboundedReceiver, UnboundedSender};
use std::sync::{Arc, LazyLock};
use std::time::Duration;

const HEARTBEAT_PONG_FAILED_REASON: &str = "Failed to reply pong";
const HEARTBEAT_TIMEOUT_REASON: &str = "Heartbeat timeout (no websocket activity)";

const TLS_HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(10);
const WS_HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(15);

pub(super) const TCP_CONNECT_TIMEOUT: Duration = Duration::from_secs(10);

const MAX_DRAIN_PER_TICK: usize = 256;

pub(super) static TLS_CONNECTOR: LazyLock<TlsConnector> = LazyLock::new(|| {
    let root_store = tokio_rustls::rustls::RootCertStore::from_iter(
        webpki_roots::TLS_SERVER_ROOTS.iter().cloned(),
    );

    let config = ClientConfig::builder()
        .with_root_certificates(root_store)
        .with_no_client_auth();

    TlsConnector::from(Arc::new(config))
});

enum AnySender<T> {
    #[cfg(not(feature = "unbounded-channel"))]
    Bounded(Sender<T>),
    Unbounded(UnboundedSender<T>),
}

impl<T> AnySender<T> {
    fn send(&mut self, item: T) -> Result<(), futures::channel::mpsc::TrySendError<T>> {
        match self {
            #[cfg(not(feature = "unbounded-channel"))]
            AnySender::Bounded(tx) => tx.try_send(item),
            AnySender::Unbounded(tx) => tx.unbounded_send(item),
        }
    }
}

enum AnyReceiver<T> {
    #[cfg(not(feature = "unbounded-channel"))]
    Bounded(futures::channel::mpsc::Receiver<T>),
    Unbounded(UnboundedReceiver<T>),
}

impl<T> futures::Stream for AnyReceiver<T> {
    type Item = T;

    fn poll_next(
        self: std::pin::Pin<&mut Self>,
        cx: &mut std::task::Context<'_>,
    ) -> std::task::Poll<Option<Self::Item>> {
        match self.get_mut() {
            #[cfg(not(feature = "unbounded-channel"))]
            AnyReceiver::Bounded(rx) => std::pin::Pin::new(rx).poll_next(cx),
            AnyReceiver::Unbounded(rx) => std::pin::Pin::new(rx).poll_next(cx),
        }
    }
}

impl<T> AnyReceiver<T> {
    fn try_recv(&mut self) -> Option<T> {
        match self {
            #[cfg(not(feature = "unbounded-channel"))]
            AnyReceiver::Bounded(rx) => rx.try_recv().ok(),
            AnyReceiver::Unbounded(rx) => rx.try_recv().ok(),
        }
    }
}

fn channel<T>(_capacity: usize) -> (AnySender<T>, AnyReceiver<T>) {
    #[cfg(not(feature = "unbounded-channel"))]
    {
        let (tx, rx) = futures::channel::mpsc::channel(_capacity);
        (AnySender::Bounded(tx), AnyReceiver::Bounded(rx))
    }
    #[cfg(feature = "unbounded-channel")]
    {
        let (tx, rx) = futures::channel::mpsc::unbounded();
        (AnySender::Unbounded(tx), AnyReceiver::Unbounded(rx))
    }
}

pub(super) struct ChannelStream<T> {
    receiver: AnyReceiver<T>,
    task: tokio::task::JoinHandle<()>,
}

impl<T> futures::Stream for ChannelStream<T> {
    type Item = T;

    fn poll_next(
        self: std::pin::Pin<&mut Self>,
        cx: &mut std::task::Context<'_>,
    ) -> std::task::Poll<Option<Self::Item>> {
        std::pin::Pin::new(&mut self.get_mut().receiver).poll_next(cx)
    }
}

impl<T> Drop for ChannelStream<T> {
    fn drop(&mut self) {
        self.task.abort();
    }
}

#[derive(Clone, Debug)]
pub(super) struct WsSession {
    streams: Arc<[StreamKind]>,
}

/// How often [`on_tick`](WsAdapter::on_tick) fires. Also serves as the time-bucket
/// granularity for trade aggregation — trades within one interval are collapsed
/// into a single [`Event::TradesReceived`].
const ADAPTER_TICK_INTERVAL: Duration = Duration::from_micros(33_333);

pub(super) trait WsAdapter {
    /// Selects the transport heartbeat policy for this adapter.
    ///
    /// The session reads this policy after each successful connection. The
    /// policy owns all venue-specific timing and wire-format decisions, while
    /// the shared transport handles frame activity and control replies.
    fn heartbeat_policy(&self) -> HeartbeatPolicy;

    /// Connects to the WebSocket and returns a transport for it.
    /// This will be retried indefinitely until it succeeds, with an exponential backoff
    /// between attempts (base ~500ms, doubling, capped at 30s, with jitter).
    fn connect(&mut self) -> impl std::future::Future<Output = Result<WsTransport, String>> + Send;

    /// Tick interval controlling how often [`on_tick`](WsAdapter::on_tick) is called
    /// and the time-bucket granularity for trade aggregation.
    fn tick_interval(&self) -> Duration {
        ADAPTER_TICK_INTERVAL
    }

    /// Called when a connection is established.
    /// This is called on every successful connection, including after reconnects.
    fn on_connected(&mut self) -> impl std::future::Future<Output = Vec<Event>> + Send;

    /// Called periodically while connected, at the cadence returned by
    /// [`tick_interval`].
    ///
    /// This is where **trade adapters** flush their [`TradeBuffer`] — trades are
    /// batched across one tick interval and emerge as a single
    /// [`Event::TradesReceived`]. Non-trade adapters leave this as the default
    /// no-op because they push events directly in [`on_text`](Self::on_text).
    fn on_tick(&mut self) -> impl std::future::Future<Output = Vec<Event>> + Send {
        async { Vec::new() }
    }

    /// Called when a text message is received.
    ///
    /// Adapters parse incoming data and return resulting `Event`s.
    /// The session loop sends them to the output channel.
    /// If the output channel is full, events are silently dropped
    ///
    /// **Flush model**: non-trade adapters return events here directly.
    /// Trade adapters only buffer into [`TradeBuffer`] here and return
    /// events later in [`on_tick`](Self::on_tick).
    fn on_text(
        &mut self,
        payload: &[u8],
    ) -> impl std::future::Future<Output = Result<Vec<Event>, String>> + Send;

    /// Called when the connection is closed or a fatal error occurs.
    fn on_disconnected(
        &mut self,
        reason: &str,
    ) -> impl std::future::Future<Output = Vec<Event>> + Send;
}

impl WsSession {
    pub(super) fn new(streams: Arc<[StreamKind]>) -> Self {
        Self { streams }
    }

    pub(super) fn run<A: WsAdapter + Send + 'static>(self, mut adapter: A) -> ChannelStream<Event> {
        let (mut event_tx, event_rx) = channel(512);

        let streams = Arc::clone(&self.streams);

        let task = tokio::spawn(async move {
            if streams.is_empty() {
                let _ = event_tx.send(Event::Disconnected(
                    streams,
                    "Empty stream payload".to_string(),
                ));
                return;
            }

            let mut backoff = ReconnectBackoff::new();

            loop {
                let transport = match adapter.connect().await {
                    Ok(t) => t,
                    Err(reason) => {
                        let _ = event_tx.send(Event::Disconnected(Arc::clone(&streams), reason));
                        tokio::time::sleep(backoff.delay()).await;
                        backoff.record_failure();
                        continue;
                    }
                };

                let heartbeat_policy = adapter.heartbeat_policy();

                let (frame_tx, mut frame_rx) = {
                    let (tx, rx) = futures::channel::mpsc::unbounded();
                    (AnySender::Unbounded(tx), AnyReceiver::Unbounded(rx))
                };
                let io_handle = tokio::spawn(transport.read_frame(heartbeat_policy, frame_tx));

                for event in adapter.on_connected().await {
                    let _ = event_tx.send(event);
                }
                let _ = event_tx.send(Event::Connected(Arc::clone(&streams)));

                let tick_interval = adapter.tick_interval();
                let tick_sleep = tokio::time::sleep(tick_interval);
                tokio::pin!(tick_sleep);

                let disconnect_reason = loop {
                    tokio::select! {
                        biased;
                        frame = frame_rx.next() => {
                            let mut disconnect_reason: Option<String> = None;

                            match frame {
                                Some(Ok(payload)) => {
                                    backoff.record_success();

                                    if !payload.is_empty() {
                                        match adapter.on_text(&payload).await {
                                            Ok(events) => {
                                                for event in events {
                                                    let _ = event_tx.send(event);
                                                }
                                            }
                                            Err(reason) => {
                                                disconnect_reason = Some(reason);
                                            }
                                        }
                                    }

                                    if disconnect_reason.is_none() {
                                       let mut drained = 0;
                                        while drained < MAX_DRAIN_PER_TICK {
                                            let Some(drain) = frame_rx.try_recv() else { break };
                                            drained += 1;
                                            match drain {
                                                Ok(payload) => {
                                                    match adapter.on_text(&payload).await {
                                                        Ok(events) => {
                                                            for event in events {
                                                                let _ = event_tx.send(event);
                                                            }
                                                        }
                                                        Err(reason) => {
                                                            disconnect_reason = Some(reason);
                                                            break;
                                                        }
                                                    }
                                                }
                                                Err(reason) => {
                                                    disconnect_reason = Some(reason);
                                                    break;
                                                }
                                            }
                                        }
                                    }
                                }
                                Some(Err(reason)) => {
                                    disconnect_reason = Some(reason);
                                }
                                None => {
                                    disconnect_reason = Some(
                                        "I/O task exited".to_string(),
                                    );
                                }
                            }

                            if let Some(reason) = disconnect_reason {
                                break Some(reason);
                            }
                        }
                        _ = &mut tick_sleep => {
                            for event in adapter.on_tick().await {
                                let _ = event_tx.send(event);
                            }
                            tick_sleep
                                .as_mut()
                                .reset(tokio::time::Instant::now() + tick_interval);
                        }
                    }
                };

                if io_handle.is_finished() {
                    if let Err(e) = io_handle.await {
                        log::error!("WebSocket I/O task panicked (reconnecting): {e}");
                    }
                } else {
                    io_handle.abort();
                }

                if let Some(reason) = disconnect_reason {
                    for event in adapter.on_disconnected(&reason).await {
                        let _ = event_tx.send(event);
                    }
                    let _ = event_tx.send(Event::Disconnected(Arc::clone(&streams), reason));
                }

                tokio::time::sleep(backoff.delay()).await;
                backoff.record_failure();
            }
        });

        ChannelStream {
            receiver: event_rx,
            task,
        }
    }
}

/// Transport-level keepalive strategy for a WebSocket adapter.
///
/// Activity is recorded for every complete inbound frame, including control
/// frames. The policy closes the connection when no complete inbound frame
/// arrives within `silence_timeout`.
#[derive(Clone, Copy, Debug)]
pub(super) enum HeartbeatPolicy {
    /// Rely on protocol-level pings sent by the server.
    ///
    /// The transport still replies to incoming WebSocket Ping frames, but it
    /// never sends a proactive heartbeat.
    ServerDriven { silence_timeout: Duration },
}

impl HeartbeatPolicy {
    /// Creates a [`ServerDriven`](HeartbeatPolicy::ServerDriven) policy
    /// that only observes server-driven activity.
    pub(super) const fn server_driven(silence_timeout: Duration) -> Self {
        Self::ServerDriven { silence_timeout }
    }
}

struct WsHeartbeat {
    silence_timeout: Duration,
    last_activity: Instant,
}

impl WsHeartbeat {
    fn new(policy: HeartbeatPolicy, now: Instant) -> Self {
        let HeartbeatPolicy::ServerDriven { silence_timeout } = policy;
        Self {
            silence_timeout,
            last_activity: now,
        }
    }

    fn next_deadline(&self) -> Instant {
        self.last_activity + self.silence_timeout
    }

    fn is_timed_out(&self, now: Instant) -> bool {
        now >= self.next_deadline()
    }

    fn mark_activity(&mut self, now: Instant) {
        self.last_activity = now;
    }
}

struct WsConnection<R, W> {
    reader: FragmentCollectorRead<R>,
    writer: WebSocketWrite<W>,
    heartbeat: WsHeartbeat,
    frame_tx: AnySender<Result<Vec<u8>, String>>,
}

impl<R, W> WsConnection<R, W>
where
    R: AsyncRead + Unpin,
    W: AsyncWrite + Unpin,
{
    fn new(
        reader: FragmentCollectorRead<R>,
        writer: WebSocketWrite<W>,
        heartbeat_policy: HeartbeatPolicy,
        frame_tx: AnySender<Result<Vec<u8>, String>>,
    ) -> Self {
        Self {
            reader,
            writer,
            heartbeat: WsHeartbeat::new(heartbeat_policy, Instant::now()),
            frame_tx,
        }
    }

    async fn run(self) {
        let Self {
            mut reader,
            mut writer,
            mut heartbeat,
            mut frame_tx,
        } = self;

        loop {
            let mut no_control_send =
                |_frame: Frame<'_>| std::future::ready(Ok::<(), std::io::Error>(()));
            let mut read_future = Box::pin(reader.read_frame(&mut no_control_send));

            let outcome = loop {
                let deadline = heartbeat.next_deadline();

                tokio::select! {
                    biased;
                    result = &mut read_future => break Ok(result),
                    _ = tokio::time::sleep_until(deadline) => {
                        if heartbeat.is_timed_out(Instant::now()) {
                            break Err(HEARTBEAT_TIMEOUT_REASON);
                        }
                    }
                }
            };

            drop(read_future);

            let message = match outcome {
                Ok(Ok(message)) => message,
                Ok(Err(error)) => {
                    let _ = frame_tx.send(Err(format!("Error reading frame: {error}")));
                    break;
                }
                Err(reason) => {
                    let _ = frame_tx.send(Err(reason.to_string()));
                    break;
                }
            };

            heartbeat.mark_activity(Instant::now());

            let keep_connection = match message.opcode {
                OpCode::Text => {
                    let payload = Vec::from(&message.payload[..]);
                    frame_tx.send(Ok(payload)).is_ok()
                }
                OpCode::Ping => {
                    let payload = Vec::from(message.payload);
                    if writer
                        .write_frame(Frame::pong(Payload::Owned(payload)))
                        .await
                        .is_err()
                    {
                        let _ = frame_tx.send(Err(HEARTBEAT_PONG_FAILED_REASON.into()));
                        false
                    } else {
                        frame_tx.send(Ok(Vec::new())).is_ok()
                    }
                }
                OpCode::Close => {
                    let payload = Vec::from(message.payload);
                    let close_reason = format_close_frame_reason(&payload);
                    let _ = writer
                        .write_frame(Frame::close_raw(Payload::Owned(payload)))
                        .await;
                    let _ = frame_tx.send(Err(close_reason));
                    false
                }
                _ => true,
            };

            if !keep_connection {
                break;
            }

            if heartbeat.is_timed_out(Instant::now()) {
                let _ = frame_tx.send(Err(HEARTBEAT_TIMEOUT_REASON.to_string()));
                break;
            }
        }
    }
}

fn format_close_frame_reason(payload: &[u8]) -> String {
    const MAX_CLOSE_REASON_CHARS: usize = 512;
    match payload {
        [] => "Connection closed by peer: no status code or reason".to_string(),
        [_] => "Connection closed by peer: invalid close payload (one byte)".to_string(),
        [code_high, code_low, reason @ ..] => {
            let code = u16::from_be_bytes([*code_high, *code_low]);
            let close_code = fastwebsockets::CloseCode::from(code);
            let reason = match std::str::from_utf8(reason) {
                Ok("") => "no reason".to_string(),
                Ok(reason) => {
                    let mut chars = reason.chars();
                    let preview: String = chars.by_ref().take(MAX_CLOSE_REASON_CHARS).collect();
                    let suffix = if chars.next().is_some() {
                        " (truncated)"
                    } else {
                        ""
                    };
                    format!("reason={preview:?}{suffix}")
                }
                Err(_) => format!("reason=<invalid UTF-8, {} bytes>", reason.len()),
            };

            format!("Connection closed by peer: code={code} ({close_code:?}), {reason}")
        }
    }
}

pub(super) struct WsTransport(WebSocket<TokioIo<Upgraded>>);

impl WsTransport {
    /// Reads frames, handles heartbeat and Ping/Pong at transport level,
    /// forwards text frames to the processor task.
    async fn read_frame(
        self,
        heartbeat_policy: HeartbeatPolicy,
        frame_tx: AnySender<Result<Vec<u8>, String>>,
    ) {
        let (mut reader, writer) = self.0.split(tokio::io::split);
        reader.set_auto_pong(false);
        reader.set_auto_close(false);

        let reader = FragmentCollectorRead::new(reader);
        WsConnection::new(reader, writer, heartbeat_policy, frame_tx)
            .run()
            .await;
    }

    pub(super) async fn establish(
        domain: &str,
        url: &str,
        proxy_cfg: Option<&Proxy>,
    ) -> Result<Self, AdapterError> {
        let parsed = Url::parse(url).map_err(|e| AdapterError::InvalidRequest(e.to_string()))?;

        let url_host = parsed.host_str().ok_or_else(|| {
            AdapterError::InvalidRequest("Missing host in websocket URL".to_string())
        })?;

        if !url_host.eq_ignore_ascii_case(domain) {
            return Err(AdapterError::InvalidRequest(format!(
                "WebSocket URL host mismatch: url_host={url_host}, domain_arg={domain}"
            )));
        }

        let target_port = parsed.port_or_known_default().ok_or_else(|| {
            AdapterError::InvalidRequest("Missing port for websocket URL".to_string())
        })?;

        let tcp_stream = ProxyStream::connect_tcp(domain, target_port, proxy_cfg).await?;

        match parsed.scheme() {
            "wss" => {
                let tls_stream = tokio::time::timeout(
                    TLS_HANDSHAKE_TIMEOUT,
                    Self::upgrade_to_tls(tcp_stream, domain),
                )
                .await
                .map_err(|_| {
                    AdapterError::WebsocketError("TLS handshake to target timed out".to_string())
                })??;

                tokio::time::timeout(
                    WS_HANDSHAKE_TIMEOUT,
                    Self::handshake_tls(tls_stream, domain, &parsed),
                )
                .await
                .map_err(|_| {
                    AdapterError::WebsocketError("WebSocket handshake timed out".to_string())
                })?
            }
            "ws" => tokio::time::timeout(
                WS_HANDSHAKE_TIMEOUT,
                Self::handshake_tcp(tcp_stream, domain, &parsed),
            )
            .await
            .map_err(|_| {
                AdapterError::WebsocketError("WebSocket handshake timed out".to_string())
            })?,
            _ => Err(AdapterError::InvalidRequest(
                "Invalid scheme for websocket URL".to_string(),
            )),
        }
    }

    async fn upgrade_to_tls(
        stream: ProxyStream,
        domain: &str,
    ) -> Result<Box<tokio_rustls::client::TlsStream<ProxyStream>>, AdapterError> {
        let server_name = ServerName::try_from(domain.to_owned())
            .map_err(|_| AdapterError::ParseError("invalid dnsname".to_string()))?;

        let tls_stream = TLS_CONNECTOR
            .connect(server_name, stream)
            .await
            .map_err(|e| AdapterError::WebsocketError(e.to_string()))?;

        Ok(Box::new(tls_stream))
    }

    async fn handshake_tcp(
        stream: ProxyStream,
        domain: &str,
        parsed: &Url,
    ) -> Result<Self, AdapterError> {
        let req = Self::build_ws_request(domain, parsed)?;
        let exec = TokioExecutor::new();
        let (ws, _http_resp) = fastwebsockets::handshake::client(&exec, req, stream)
            .await
            .map_err(|e| AdapterError::WebsocketError(e.to_string()))?;
        Ok(Self(ws))
    }

    async fn handshake_tls(
        tls: Box<tokio_rustls::client::TlsStream<ProxyStream>>,
        domain: &str,
        parsed: &Url,
    ) -> Result<Self, AdapterError> {
        let req = Self::build_ws_request(domain, parsed)?;
        let exec = TokioExecutor::new();
        let (ws, _http_resp) = fastwebsockets::handshake::client(&exec, req, tls)
            .await
            .map_err(|e| AdapterError::WebsocketError(e.to_string()))?;
        Ok(Self(ws))
    }

    fn build_ws_request(domain: &str, parsed: &Url) -> Result<Request<Empty<Bytes>>, AdapterError> {
        let mut path_and_query = parsed.path().to_string();
        if let Some(q) = parsed.query() {
            path_and_query.push('?');
            path_and_query.push_str(q);
        }
        if path_and_query.is_empty() {
            path_and_query.push('/');
        }

        let host_header = match parsed.port() {
            Some(explicit_port) => {
                let default_port = parsed.port_or_known_default().unwrap_or(explicit_port);
                if explicit_port != default_port {
                    format!("{domain}:{explicit_port}")
                } else {
                    domain.to_string()
                }
            }
            None => domain.to_string(),
        };

        Request::builder()
            .method("GET")
            .uri(path_and_query)
            .header("Host", host_header)
            .header(UPGRADE, "websocket")
            .header(CONNECTION, "upgrade")
            .header(
                "Sec-WebSocket-Key",
                fastwebsockets::handshake::generate_key(),
            )
            .header("Sec-WebSocket-Version", "13")
            .body(Empty::<Bytes>::new())
            .map_err(|e| AdapterError::WebsocketError(e.to_string()))
    }
}

/// Exponential backoff for WebSocket reconnection attempts.
///
/// Delay doubles on each failure, resets to the initial 500ms on success.
/// Capped at 30s with ±25% multiplicative jitter to spread reconnections
/// across streams when multiple disconnect at once.
struct ReconnectBackoff {
    current: Duration,
}

impl ReconnectBackoff {
    const INITIAL: Duration = Duration::from_millis(500);
    const MAX: Duration = Duration::from_secs(30);
    const JITTER: f32 = 0.25;

    fn new() -> Self {
        Self {
            current: Self::INITIAL,
        }
    }

    /// Returns the delay before the next reconnect attempt, with ±jitter applied.
    fn delay(&self) -> Duration {
        let factor = 1.0 + (rand::random::<f32>() * 2.0 - 1.0) * Self::JITTER;
        let secs = self.current.as_secs_f32() * factor;
        Duration::from_secs_f32(secs.max(0.0)).min(Self::MAX)
    }

    /// Doubles the delay (capped) after a failed attempt.
    fn record_failure(&mut self) {
        self.current = (self.current.mul_f32(2.0)).min(Self::MAX);
    }

    /// Resets the delay to the initial value after genuine success
    /// (real market-data events were produced by the connection).
    fn record_success(&mut self) {
        self.current = Self::INITIAL;
    }
}

pub(super) struct TradeBuffer {
    buffer_map: FxHashMap<Ticker, Vec<Trade>>,
    ticker_info_map: FxHashMap<Ticker, (TickerInfo, QtyNormalization)>,
}

impl TradeBuffer {
    pub(super) fn new(ticker_info_map: FxHashMap<Ticker, (TickerInfo, QtyNormalization)>) -> Self {
        Self {
            buffer_map: FxHashMap::default(),
            ticker_info_map,
        }
    }

    pub(super) fn ticker_info(&self, ticker: &Ticker) -> Option<&(TickerInfo, QtyNormalization)> {
        self.ticker_info_map.get(ticker)
    }

    pub(super) fn push(&mut self, ticker: Ticker, trade: Trade) {
        self.buffer_map.entry(ticker).or_default().push(trade);
    }

    /// Drain all buffered trades, clearing internal buffers.
    ///
    /// Each ticker's trades are collapsed into a single [`Event::TradesReceived`]
    /// keyed by the most recent trade's time rounded down to the nearest
    /// [`ADAPTER_TICK_INTERVAL`] bucket.
    pub(super) fn flush(&mut self) -> Vec<Event> {
        let interval_ms = ADAPTER_TICK_INTERVAL.as_millis() as u64;
        let mut events = Vec::new();

        for (ticker, trades_buffer) in self.buffer_map.iter_mut() {
            if trades_buffer.is_empty() {
                continue;
            }

            let bucket_update_t = trades_buffer
                .iter()
                .map(|t| t.time.as_u64())
                .max()
                .map(|t| UnixMs::new((t / interval_ms) * interval_ms));

            if let Some((ticker_info, _)) = self.ticker_info_map.get(ticker)
                && let Some(update_t) = bucket_update_t
            {
                events.push(Event::TradesReceived(
                    StreamKind::Trades {
                        ticker_info: *ticker_info,
                    },
                    update_t,
                    std::mem::take(trades_buffer).into_boxed_slice(),
                ));
            }
        }

        events
    }
}
