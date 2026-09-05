export interface LoginRequest {
  username: string
  password: string
}

export interface UserInfo {
  id: number
  username: string
  role: string
  can_use_agent: boolean
  can_create_real: boolean
  max_strategies: number
  can_use_cron: boolean
  can_use_monitor: boolean
}

export interface LoginResponse {
  token: string
  user: UserInfo
}

// ── 个人中心 ──────────────────────────────────

export interface UserProfile {
  id: number
  username: string
  nickname?: string
  avatar_url?: string
  email?: string
  phone?: string
  bio?: string
  investment_style?: string
  risk_level?: string
  role: string
  created_at?: string
  updated_at?: string
}

export interface UserProfileUpdate {
  nickname?: string
  avatar_url?: string
  email?: string
  phone?: string
  bio?: string
  investment_style?: string
  risk_level?: string
}

export interface PasswordChangeRequest {
  old_password: string
  new_password: string
}

export interface BestItem {
  name: string
  value: number
}

export interface InvestmentStats {
  best_strategy: BestItem | null
  worst_stock: BestItem | null
  best_stock: BestItem | null
  total_trades: number
  total_strategies: number
  total_realized_pnl: number
  account_age_days: number
}
