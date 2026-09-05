export interface TickData {
  stock_code: string
  last_price: string
  open: string
  high: string
  low: string
  amount: string
  volume: number
  ask_price: string[]
  bid_price: string[]
  ask_volume: number[]
  bid_volume: number[]
  timestamp: number
}

export type TickMap = Record<string, TickData>

export interface WsEvent {
  type: 'trade' | 'order_status'
  stock_code?: string
  volume?: number
  price?: string
  order_id?: string
  status?: string
  message?: string
}
