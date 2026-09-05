import api from './index'

export interface OrderConfirmation {
  id: string
  api_token_name: string
  strategy_id: string
  stock_code: string
  order_type: number
  price_type: number
  price: string
  order_volume: number
  order_remark: string
  status: string
  result_order_id: string
  reject_reason: string
  created_at: string
  expires_at: string
}

export interface ApproveResult {
  success: boolean
  order_id: string
  message: string
}

export function listPendingConfirmations(status?: string) {
  const params = status ? { status } : {}
  return api.get<OrderConfirmation[]>('/order-confirmations', { params })
}

export function approveConfirmation(id: string) {
  return api.post<ApproveResult>(`/order-confirmations/${id}/approve`)
}

export function rejectConfirmation(id: string, reason?: string) {
  return api.post<ApproveResult>(`/order-confirmations/${id}/reject`, {
    reject_reason: reason || '',
  })
}
