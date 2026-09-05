export interface OrderRequest {
  stock_code: string
  order_type: number // 23=买入, 24=卖出
  price: number
  order_volume: number
  price_type: number // 5=最新价, 11=限价
  order_remark?: string
}

export interface OrderResponse {
  order_id: string
  strategy_id: string
  stock_code: string
  stock_name: string
  order_type: number
  price_type: number
  price: string
  order_volume: number
  traded_volume: number
  traded_price: string
  commission: string
  status: number
  status_msg: string
  created_at: string
  order_remark: string
}

export interface PlaceOrderResponse {
  success: boolean
  order_id: string
  message: string
  available_cash: string
  frozen_cash: string
}

export interface CancelOrderResponse {
  success: boolean
  order_id: string
  unfilled_volume: number
  message: string
}
