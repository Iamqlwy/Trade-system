export interface UserGroup {
  id: number
  name: string
  description: string
  member_count: number
  created_at: string
}

export interface GroupMember {
  user_id: number
  username: string
  role: string
}

export interface GroupPermissions {
  can_use_agent: boolean
  can_create_real: boolean
  max_strategies: number
  can_use_cron: boolean
  can_use_monitor: boolean
}

export interface GroupStrategyPermission {
  strategy_id: string
  strategy_name: string
  can_trade: boolean
}

export interface GroupToolPermission {
  tool_key: string
  enabled: boolean
}

export interface GroupDetail {
  id: number
  name: string
  description: string
  members: GroupMember[]
  permissions: GroupPermissions | null
  strategy_permissions: GroupStrategyPermission[]
  tool_permissions: GroupToolPermission[]
}
