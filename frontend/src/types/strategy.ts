export interface StrategySummary {
  strategy_id: string
  name: string
  description: string
  detail: string
  trade_mode: number // 0=模拟, 1=实盘
  initial_cash: string
  available_cash: string
  frozen_cash: string
  position_count: number
  order_count_today: number
  trade_count_today: number
}

export interface CreateStrategyRequest {
  name: string
  description?: string
  detail?: string
  trade_mode?: number
  initial_cash?: string
}

export interface UpdateStrategyRequest {
  name?: string
  description?: string
  detail?: string
}
