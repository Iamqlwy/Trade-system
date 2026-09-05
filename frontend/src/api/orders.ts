import api from './index'
import type { OrderRequest, OrderResponse, PlaceOrderResponse, CancelOrderResponse } from '@/types/order'

export function listOrders(strategyId: string, status?: number) {
  const params = status !== undefined ? { status } : {}
  return api.get<OrderResponse[]>(`/strategies/${strategyId}/orders`, { params })
}

export function placeOrder(strategyId: string, data: OrderRequest) {
  return api.post<PlaceOrderResponse>(`/strategies/${strategyId}/orders`, data)
}

export function cancelOrder(strategyId: string, orderId: string) {
  return api.delete<CancelOrderResponse>(`/strategies/${strategyId}/orders/${orderId}`)
}
