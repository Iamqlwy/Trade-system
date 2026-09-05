import api from './index'

export interface OnlineUser {
  user_id: number
  username: string
  role: string
  connected_since: string
}

export interface AdminStats {
  total_users: number
  total_strategies: number
  sim_strategies: number
  live_strategies: number
  total_orders: number
  total_orders_today: number
  total_trades: number
  total_trades_today: number
  pending_feedback_count: number
  total_monitors: number
  total_cron_jobs: number
  unique_online_count: number
  online_users: OnlineUser[]
  total_assets: number
  total_market_value: number
}

export interface OnlineUsersResponse {
  unique_online_count: number
  online_users: OnlineUser[]
}

// 趋势数据接口（按天统计）
export interface MonitorAlertTrend {
  date: string
  count: number
}

export interface CronJobTrend {
  date: string
  total: number
  success: number
  failed: number
}

export interface OrderTrend {
  date: string
  sim: number
  live: number
}

export interface TradeTrend {
  date: string
  sim_count: number
  live_count: number
  sim_amount: number
  live_amount: number
}

export interface AssetTrend {
  date: string
  sim_total: number
  live_total: number
  sim_market: number
  live_market: number
}

export interface AgentSessionTrend {
  date: string
  new_sessions: number
  user_messages: number
  context_chars: number
}

export interface UserRegistrationTrend {
  date: string
  new_users: number
}

export interface StrategyCreationTrend {
  date: string
  sim: number
  live: number
}

export interface FeedbackTrend {
  date: string
  total: number
  pending: number
  resolved: number
}

export interface TrendsResponse {
  // 监控维度
  monitor_alerts: MonitorAlertTrend[]
  cron_jobs: CronJobTrend[]

  // 交易维度（拆分模拟/实盘）
  orders: OrderTrend[]
  trades: TradeTrend[]
  assets: AssetTrend[]

  // Agent 维度
  agent_sessions: AgentSessionTrend[]

  // 用户 & 策略维度
  user_registrations: UserRegistrationTrend[]
  strategy_creations: StrategyCreationTrend[]

  // 反馈维度
  feedbacks: FeedbackTrend[]
}

export function getStats() {
  return api.get<AdminStats>('/admin/stats')
}

export function getOnlineUsers() {
  return api.get<OnlineUsersResponse>('/admin/online-users')
}

export function getTrends(startDate: string, endDate: string) {
  return api.get<TrendsResponse>('/admin/trends', {
    params: { start_date: startDate, end_date: endDate },
  })
}
