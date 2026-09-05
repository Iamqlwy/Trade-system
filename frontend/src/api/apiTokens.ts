import api from './index'

export interface ApiToken {
  id: number
  name: string
  scope_type: 'all' | 'owned' | 'listed'
  scope_strategies: string[]
  permissions: ('read' | 'trade' | 'modify')[]
  expires_at: string | null
  last_used_at: string | null
  is_active: boolean
  rate_limit: number
  require_confirm: boolean
  created_at: string
}

export interface ApiTokenCreated extends ApiToken {
  token: string  // 仅创建时返回
}

export interface CreateApiTokenRequest {
  name?: string
  scope_type?: 'all' | 'owned' | 'listed'
  scope_strategies?: string[]
  permissions?: ('read' | 'trade' | 'modify')[]
  expires_days?: number | null
  rate_limit?: number
  require_confirm?: boolean
}

export interface UpdateApiTokenRequest {
  name?: string
  scope_type?: 'all' | 'owned' | 'listed'
  scope_strategies?: string[]
  permissions?: ('read' | 'trade' | 'modify')[]
  rate_limit?: number
  is_active?: boolean
  require_confirm?: boolean
}

export function listApiTokens() {
  return api.get<ApiToken[]>('/api-tokens')
}

export function createApiToken(data: CreateApiTokenRequest) {
  return api.post<ApiTokenCreated>('/api-tokens', data)
}

export function updateApiToken(id: number, data: UpdateApiTokenRequest) {
  return api.put<ApiToken>(`/api-tokens/${id}`, data)
}

export function deleteApiToken(id: number) {
  return api.delete(`/api-tokens/${id}`)
}
