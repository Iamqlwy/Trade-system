export interface MessageSummary {
  id: number
  title: string
  content: string
  sender_name: string
  is_read: boolean
  created_at: string
}

export interface MessageDetail extends MessageSummary {
  content: string
  read_at: string | null
}

export interface SentMessageItem {
  id: number
  title: string
  content: string
  recipient_count: number
  read_count: number
  created_at: string
}

export interface MessageListResponse {
  items: MessageSummary[]
  total: number
  page: number
  page_size: number
}

export interface SentMessageListResponse {
  items: SentMessageItem[]
  total: number
  page: number
  page_size: number
}

export interface UnreadCountResponse {
  count: number
}

export interface SendMessageRequest {
  title: string
  content: string
  recipient_ids: number[]
}

export interface BatchDeleteRequest {
  ids: number[]
}
