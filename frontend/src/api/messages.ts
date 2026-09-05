import api from './index'
import type {
  MessageListResponse,
  MessageDetail,
  SentMessageListResponse,
  UnreadCountResponse,
  SendMessageRequest,
  BatchDeleteRequest,
} from '@/types/message'

export function getMessages(params: {
  page?: number
  page_size?: number
  status?: string
}) {
  return api.get<MessageListResponse>('/messages/', { params })
}

export function getUnreadCount() {
  return api.get<UnreadCountResponse>('/messages/unread-count')
}

export function getSentMessages(params: { page?: number; page_size?: number }) {
  return api.get<SentMessageListResponse>('/messages/sent', { params })
}

export function getMessageDetail(id: number) {
  return api.get<MessageDetail>(`/messages/${id}`)
}

export function markRead(id: number, is_read: boolean) {
  return api.put(`/messages/${id}/read`, { is_read })
}

export function deleteMessage(id: number) {
  return api.delete(`/messages/${id}`)
}

export function batchDeleteMessages(data: BatchDeleteRequest) {
  return api.post('/messages/batch-delete', data)
}

export function sendMessage(data: SendMessageRequest) {
  return api.post('/messages/', data)
}
