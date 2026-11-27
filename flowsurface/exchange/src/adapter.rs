mod client;
mod http;
mod hub;
mod limiter;
pub mod proxy;
mod ws;

use super::Timeframe;
pub use super::error::{AdapterError, FetchError};
use crate::{
    Kline, Price, PushFrequency, TickMultiplier, TickerInfo, Trade, UnixMs, depth::Depth, unit::Qty,
};

use enum_map::{Enum, EnumMap};
use rustc_hash::{FxHashMap, FxHashSet};
use serde::{Deserialize, Serialize};
use std::{str::FromStr, sync::Arc};

pub use client::{AdapterHandles, MAX_KLINE_STREAMS_PER_STREAM, MAX_TRADE_TICKERS_PER_STREAM};
pub use proxy::Proxy;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Deserialize, Serialize)]
pub enum MarketKind {
    Spot,
    LinearPerps,
    InversePerps,
}

impl MarketKind {
    pub const ALL: [MarketKind; 3] = [
        MarketKind::Spot,
        MarketKind::LinearPerps,
        MarketKind::InversePerps,
    ];

    pub fn qty_in_quote_value(&self, qty: Qty, price: Price, size_in_quote_ccy: bool) -> f64 {
        let qty = qty.to_f64();

        match self {
            MarketKind::InversePerps => qty,
            _ => {
                if size_in_quote_ccy {
                    qty
                } else {
                    price.to_f64() * qty
                }
            }
        }
    }
}

impl std::fmt::Display for MarketKind {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "{}",
            match self {
                MarketKind::Spot => "Spot",
                MarketKind::LinearPerps => "Linear",
                MarketKind::InversePerps => "Inverse",
            }
        )
    }
}

impl FromStr for MarketKind {
    type Err = String;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        if s.eq_ignore_ascii_case("spot") {
            Ok(Self::Spot)
        } else if s.eq_ignore_ascii_case("linear") {
            Ok(Self::LinearPerps)
        } else if s.eq_ignore_ascii_case("inverse") {
            Ok(Self::InversePerps)
        } else {
            Err(format!("Invalid market kind: {}", s))
        }
    }
}

#[derive(Debug, Copy, Clone, PartialEq, Eq, Hash, Deserialize, Serialize)]
pub enum StreamKind {
    Kline {
        ticker_info: TickerInfo,
        timeframe: Timeframe,
    },
    Depth {
        ticker_info: TickerInfo,
        #[serde(default = "default_depth_aggr")]
        depth_aggr: StreamTicksize,
        push_freq: PushFrequency,
    },
    Trades {
        ticker_info: TickerInfo,
    },
}

impl StreamKind {
    pub fn ticker_info(&self) -> TickerInfo {
        match self {
            StreamKind::Kline { ticker_info, .. }
            | StreamKind::Depth { ticker_info, .. }
            | StreamKind::Trades { ticker_info, .. } => *ticker_info,
        }
    }

    pub fn as_depth_stream(&self) -> Option<(TickerInfo, StreamTicksize, PushFrequency)> {
        match self {
            StreamKind::Depth {
                ticker_info,
                depth_aggr,
                push_freq,
            } => Some((*ticker_info, *depth_aggr, *push_freq)),
            _ => None,
        }
    }

    pub fn as_trade_stream(&self) -> Option<TickerInfo> {
        match self {
            StreamKind::Trades { ticker_info } => Some(*ticker_info),
            _ => None,
        }
    }

    pub fn as_kline_stream(&self) -> Option<(TickerInfo, Timeframe)> {
        match self {
            StreamKind::Kline {
                ticker_info,
                timeframe,
            } => Some((*ticker_info, *timeframe)),
            _ => None,
        }
    }
}

#[derive(Debug, Default)]
pub struct UniqueStreams {
    streams: EnumMap<Exchange, Option<FxHashMap<TickerInfo, FxHashSet<StreamKind>>>>,
    specs: EnumMap<Exchange, Option<StreamSpecs>>,
}

impl UniqueStreams {
    pub fn from<'a>(streams: impl Iterator<Item = &'a StreamKind>) -> Self {
        let mut unique_streams = UniqueStreams::default();
        for stream in streams {
            unique_streams.add(*stream);
        }
        unique_streams
    }

    pub fn add(&mut self, stream: StreamKind) {
        let (exchange, ticker_info) = match stream {
            StreamKind::Kline { ticker_info, .. }
            | StreamKind::Depth { ticker_info, .. }
            | StreamKind::Trades { ticker_info, .. } => (ticker_info.exchange(), ticker_info),
        };

        self.streams[exchange]
            .get_or_insert_with(FxHashMap::default)
            .entry(ticker_info)
            .or_default()
            .insert(stream);

        self.update_specs_for_exchange(exchange);
    }

    pub fn extend<'a>(&mut self, streams: impl IntoIterator<Item = &'a StreamKind>) {
        for stream in streams {
            self.add(*stream);
        }
    }

    fn update_specs_for_exchange(&mut self, exchange: Exchange) {
        let depth_streams = self.depth_streams(Some(exchange));
        let trade_streams = self.trade_streams(Some(exchange));
        let kline_streams = self.kline_streams(Some(exchange));

        self.specs[exchange] = Some(StreamSpecs {
            depth: depth_streams,
            trade: trade_streams,
            kline: kline_streams,
        });
    }

    /// Collects stream specs in a stable total order.
    ///
    /// `Subscription::run_with` hashes the chunked `StreamConfig` to identify a
    /// stream, so the order must depend only on the set of streams.
    fn streams<T, F>(&self, exchange_filter: Option<Exchange>, stream_extractor: F) -> Vec<T>
    where
        F: Fn(Exchange, &StreamKind) -> Option<T>,
        T: Ord,
    {
        let f = &stream_extractor;

        let per_exchange = |exchange| {
            self.streams[exchange]
                .as_ref()
                .into_iter()
                .flat_map(|ticker_map| ticker_map.values().flatten())
                .filter_map(move |stream| f(exchange, stream))
        };

        let mut specs: Vec<T> = match exchange_filter {
            Some(exchange) => per_exchange(exchange).collect(),
            None => Exchange::ALL.into_iter().flat_map(per_exchange).collect(),
        };

        // Specs are unique, so the unstable sort is deterministic.
        specs.sort_unstable();
        specs
    }

    pub fn depth_streams(
        &self,
        exchange_filter: Option<Exchange>,
    ) -> Vec<(TickerInfo, StreamTicksize, PushFrequency)> {
        self.streams(exchange_filter, |_, stream| stream.as_depth_stream())
    }

    pub fn kline_streams(&self, exchange_filter: Option<Exchange>) -> Vec<(TickerInfo, Timeframe)> {
        self.streams(exchange_filter, |_, stream| stream.as_kline_stream())
    }

    pub fn trade_streams(&self, exchange_filter: Option<Exchange>) -> Vec<TickerInfo> {
        self.streams(exchange_filter, |_, stream| stream.as_trade_stream())
    }

    pub fn combined_used(&self) -> impl Iterator<Item = (Exchange, &StreamSpecs)> {
        self.specs
            .iter()
            .filter_map(|(exchange, specs)| specs.as_ref().map(|stream| (exchange, stream)))
    }

    pub fn combined(&self) -> &EnumMap<Exchange, Option<StreamSpecs>> {
        &self.specs
    }
}

#[derive(
    Debug, Default, Clone, Copy, PartialEq, Eq, Hash, Deserialize, Serialize, PartialOrd, Ord,
)]
pub enum StreamTicksize {
    ServerSide(TickMultiplier),
    #[default]
    Client,
}

fn default_depth_aggr() -> StreamTicksize {
    StreamTicksize::Client
}

#[derive(Debug, Clone, Default)]
pub struct StreamSpecs {
    pub depth: Vec<(TickerInfo, StreamTicksize, PushFrequency)>,
    pub trade: Vec<TickerInfo>,
    pub kline: Vec<(TickerInfo, Timeframe)>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Deserialize, Serialize)]
pub enum Venue {
    Binance,
}

impl Venue {
    pub const ALL: [Venue; 1] = [Venue::Binance];
}

impl std::fmt::Display for Venue {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "{}",
            match self {
                Venue::Binance => "Binance",
            }
        )
    }
}

impl FromStr for Venue {
    type Err = String;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        if s.eq_ignore_ascii_case("binance") {
            Ok(Self::Binance)
        } else {
            Err(format!("Invalid venue: {}", s))
        }
    }
}

#[derive(
    Debug, Clone, Copy, PartialEq, Eq, Hash, Deserialize, Serialize, Enum, Ord, PartialOrd,
)]
pub enum Exchange {
    BinanceLinear,
    BinanceInverse,
    BinanceSpot,
}

impl std::fmt::Display for Exchange {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{} {}", self.venue(), self.market_type())
    }
}

impl FromStr for Exchange {
    type Err = String;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        let mut parts = s.split_whitespace();
        let Some(venue_part) = parts.next() else {
            return Err(format!("Invalid exchange: {}", s));
        };
        let Some(market_part) = parts.next() else {
            return Err(format!("Invalid exchange: {}", s));
        };

        if parts.next().is_some() {
            return Err(format!("Invalid exchange: {}", s));
        }

        let venue = Venue::from_str(venue_part).map_err(|_| format!("Invalid exchange: {}", s))?;
        let market =
            MarketKind::from_str(market_part).map_err(|_| format!("Invalid exchange: {}", s))?;

        Self::from_venue_and_market(venue, market).ok_or_else(|| format!("Invalid exchange: {}", s))
    }
}

impl Exchange {
    pub const ALL: [Exchange; 3] = [
        Exchange::BinanceLinear,
        Exchange::BinanceInverse,
        Exchange::BinanceSpot,
    ];

    pub fn from_venue_and_market(venue: Venue, market: MarketKind) -> Option<Self> {
        Self::ALL
            .into_iter()
            .find(|exchange| exchange.venue() == venue && exchange.market_type() == market)
    }

    pub fn market_type(&self) -> MarketKind {
        match self {
            Exchange::BinanceLinear => MarketKind::LinearPerps,
            Exchange::BinanceInverse => MarketKind::InversePerps,
            Exchange::BinanceSpot => MarketKind::Spot,
        }
    }

    pub fn venue(&self) -> Venue {
        match self {
            Exchange::BinanceLinear | Exchange::BinanceInverse | Exchange::BinanceSpot => {
                Venue::Binance
            }
        }
    }

    pub fn is_depth_client_aggr(&self) -> bool {
        true
    }

    pub fn is_custom_push_freq(&self) -> bool {
        false
    }

    pub fn supports_heatmap_timeframe(&self, _tf: Timeframe) -> bool {
        true
    }

    pub fn supports_kline_timeframe(&self, tf: Timeframe) -> bool {
        Timeframe::KLINE.contains(&tf)
    }

    pub fn is_perps(&self) -> bool {
        matches!(self, Exchange::BinanceLinear | Exchange::BinanceInverse)
    }

    pub fn stream_ticksize(
        &self,
        multiplier: Option<TickMultiplier>,
        server_fallback: TickMultiplier,
    ) -> StreamTicksize {
        if self.is_depth_client_aggr() {
            StreamTicksize::Client
        } else {
            StreamTicksize::ServerSide(multiplier.unwrap_or(server_fallback))
        }
    }

    pub fn allowed_tick_multipliers(
        &self,
        _min_ticksize: Option<super::unit::MinTicksize>,
    ) -> Vec<TickMultiplier> {
        TickMultiplier::ALL.to_vec()
    }

    pub fn is_symbol_supported(&self, symbol: &str, log: bool) -> bool {
        let valid_symbol = symbol
            .chars()
            .all(|c| c.is_alphanumeric() || c == '_' || c == '-');

        if valid_symbol {
            return true;
        } else if log {
            log::warn!("Unsupported ticker: '{}': {:?}", self, symbol,);
        }
        false
    }
}

#[derive(Debug, Clone)]
pub enum Event {
    Connected(Arc<[StreamKind]>),
    Disconnected(Arc<[StreamKind]>, String),
    DepthReceived(StreamKind, UnixMs, Arc<Depth>),
    TradesReceived(StreamKind, UnixMs, Box<[Trade]>),
    KlineReceived(StreamKind, Kline),
}

#[derive(Debug, Clone, Hash)]
pub struct StreamConfig<I> {
    pub id: I,
    pub exchange: Exchange,
    pub tick_mltp: Option<TickMultiplier>,
    pub push_freq: PushFrequency,
}

impl<I> StreamConfig<I> {
    pub fn new(
        id: I,
        exchange: Exchange,
        tick_mltp: Option<TickMultiplier>,
        push_freq: PushFrequency,
    ) -> Self {
        Self {
            id,
            exchange,
            tick_mltp,
            push_freq,
        }
    }
}

#[derive(Debug, Clone)]
pub struct KlinePage {
    pub data: Vec<Kline>,
    pub next_from: UnixMs,
}

impl KlinePage {
    pub(crate) fn new(mut data: Vec<Kline>, from: UnixMs, next_from: UnixMs) -> Self {
        data.retain(|kline| kline.time >= from && kline.time < next_from);
        data.sort_unstable_by_key(|kline| kline.time);
        data.dedup_by_key(|kline| kline.time);
        Self { data, next_from }
    }
}

fn kline_page_end(
    from: UnixMs,
    to: UnixMs,
    timeframe: Timeframe,
    max_bars: u64,
) -> Result<UnixMs, AdapterError> {
    if from >= to || max_bars == 0 {
        return Err(AdapterError::InvalidRequest(
            "Invalid kline page range".to_string(),
        ));
    }

    Ok(from
        .saturating_add(timeframe.to_milliseconds().max(1).saturating_mul(max_bars))
        .min(to))
}
