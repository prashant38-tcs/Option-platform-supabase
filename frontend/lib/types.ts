export type Underlying = "NIFTY50" | "NIFTYBANK" | "FINNIFTY" | "SENSEX";

export const UNDERLYING_LABELS: Record<Underlying, string> = {
  NIFTY50: "NIFTY 50", NIFTYBANK: "BANK NIFTY", FINNIFTY: "FIN NIFTY", SENSEX: "SENSEX",
};

export type TradingMode = "ADVISORY" | "PAPER" | "LIVE";
export type RiskCategory = "DEFINED_RISK" | "UNDEFINED_RISK";
export type OrderStatus =
  | "PENDING_RISK_CHECK" | "REJECTED_BY_RISK" | "ADVISORY_ONLY" | "SIMULATED_OPEN"
  | "SIMULATED_CLOSED" | "SENT_TO_BROKER" | "ACKNOWLEDGED" | "FILLED"
  | "PARTIALLY_FILLED" | "CANCELLED" | "BROKER_REJECTED" | "ERRORED";
export type MarketRegime = "BULLISH" | "BEARISH" | "NEUTRAL_RANGE_BOUND" | "HIGH_VOLATILITY" | "LOW_VOLATILITY";
export type LogLevel = "info" | "warning" | "error" | "decision";

export interface UnderlyingScheduleStatus {
  underlying: Underlying;
  is_running: boolean;
  is_market_open: boolean;
  trading_mode: TradingMode;
  total_cycles_run: number;
  total_errors: number;
  last_cycle_at: string | null;
  last_cycle_status: string | null;
  next_cycle_at: string | null;
  next_market_open_at: string | null;
}

export interface SchedulerStatus {
  is_scheduler_running: boolean;
  interval_seconds: number;
  market_hours_only: boolean;
  underlyings: UnderlyingScheduleStatus[];
}

export interface CycleSummary {
  cycle_id: string;
  underlying: Underlying;
  trading_mode: TradingMode;
  started_at: string;
  completed_at: string | null;
  cycle_status: "running" | "completed" | "halted" | "errored";
  halt_or_error_reason: string | null;
  num_candidate_signals: number;
  num_approved_signals: number;
  num_orders_created: number;
  daily_pnl_at_completion: number | null;
}

export interface FyersSessionStatus {
  has_valid_session: boolean;
  hint: string;
}

export type WSMessage =
  | { type: "connected"; underlying: string; scheduler_status: UnderlyingScheduleStatus | null }
  | { type: "cycle_started"; cycle_id: string; trading_mode: TradingMode }
  | { type: "log"; data: AgentLogEntry }
  | { type: "option_chain"; data: OptionChainPayload }
  | { type: "sentiment"; data: SentimentPayload }
  | { type: "signals"; data: SignalPayload[] }
  | { type: "orders"; data: OrderPayload[] }
  | { type: "cycle_finished"; cycle_id: string; cycle_status: string }
  | { type: "cycle_summary"; data: CycleSummary }
  | { type: "cycle_error"; message: string };

export interface AgentLogEntry {
  timestamp: string;
  agent_name: string;
  message: string;
  level: LogLevel;
  llm_provider_used: string | null;
}

export interface OptionChainRow {
  strike: number;
  call: { ltp: number; oi: number; iv: number; delta: number; volume: number } | null;
  put: { ltp: number; oi: number; iv: number; delta: number; volume: number } | null;
}

export interface OptionChainPayload {
  spot: number;
  india_vix: number | null;
  atm_strike: number | null;
  expiry: string;
  num_calls: number;
  num_puts: number;
  put_call_ratio_oi: number | null;
  rows: OptionChainRow[];
}

export interface SentimentPayload {
  sentiment_score: number;
  market_regime: MarketRegime;
  rationale: string;
  llm_provider_used: string;
}

export interface SignalPayload {
  signal_id: string;
  strategy_type: string;
  risk_category: RiskCategory;
  net_premium: number;
  max_loss_estimate: number | null;
  max_profit_estimate: number | null;
  confidence_score: number | null;
  performance_note: string | null;
  rationale: string;
}

export interface OrderPayload {
  order_id: string;
  status: OrderStatus;
  symbol: string;
  quantity: number;
  error_message: string | null;
}
