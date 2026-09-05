// ── 净值曲线 ──────────────
export interface EquityDataPoint {
  date: string
  equity_ratio: number
  return_pct: number
}

export interface RiskMetrics {
  total_return: number
  annual_return: number
  max_drawdown: number
  sharpe_ratio: number
  volatility: number
  win_rate: number
}

export interface EquityResponse {
  equity: { dates: string[]; values: number[] }
  return_curve: { dates: string[]; values: number[] }
  drawdown: { dates: string[]; values: number[] }
  metrics: RiskMetrics
  table: EquityDataPoint[]
}

// ── 策略对比 ──────────────
export interface CompareSeries {
  name: string
  dates: string[]
  equity: number[]
  return_pct: number[]
  drawdown: number[]
}

export interface CompareRiskRow {
  策略: string
  总收益率: string
  年化收益: string
  最大回撤: string
  夏普比率: string
  波动率: string
  胜率: string
}

export interface CompareResponse {
  series: CompareSeries[]
  risk_table: CompareRiskRow[]
}

// ── 做T分析 ──────────────
export interface DayTTrendPoint {
  date: string
  profit: number
  cumulative: number
}

export interface DayTStockPerf {
  stock_code: string
  name: string
  profit: number
}

export interface DayTSummary {
  total_profit: number
  total_volume: number
  trade_days: number
  stock_count: number
  avg_daily: number
}

export interface DayTResponse {
  trend: DayTTrendPoint[]
  perf: DayTStockPerf[]
  summary: DayTSummary
  table: Record<string, unknown>[]
}

// ── 清算分析 ──────────────
export interface SettlementRow {
  stock_code: string
  name: string
  realized_profit: number
  is_closed: boolean
  first_buy_time: string
  close_time: string
}

export interface SettlementSummary {
  total_profit: number
  closed_count: number
  open_count: number
  win_count: number
  loss_count: number
  win_rate: number
}

export interface SettlementResponse {
  data: { code: string; name: string; profit: number }[]
  summary: SettlementSummary
  table: SettlementRow[]
}

// ── 交易统计 ──────────────
export interface StatisticsSummary {
  总交易: number
  买入: number
  卖出: number
  日均笔数: string
  平均金额: string
}

export interface StockStat {
  代码: string
  名称: string
  总盈亏: string
  盈利次数: number
  亏损次数: number
  胜率: string
  交易次数: number
  total_profit_raw: number
}

export interface StatisticsResponse {
  summary: StatisticsSummary
  stock_stats: StockStat[]
}

// ── 持仓监控 ──────────────
export interface PositionMonitorRow {
  策略: string
  代码: string
  股票: string
  持仓: number
  可用: number
  冻结: number
  成本价: string
  市价: string
  市值: string
  浮动盈亏: string
  盈亏比: string
  pnl_raw: number
}

export interface PositionsResponse {
  pie: { name: string; value: number }[]
  bar: { name: string; pnl: number }[]
  summary: { total_mv: number; total_cv: number; total_pnl: number; count: number }
  table: PositionMonitorRow[]
}
