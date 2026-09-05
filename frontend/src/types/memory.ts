export interface UserProfile {
  trading_style: string | null
  risk_level: string | null
  focus_sectors: string[]
  focus_stocks: string[]
  capital_range: string | null
  indicators: string[]
  extra: Record<string, unknown>
  updated_at: string | null
}

export interface UserMemory {
  id: number
  category: 'preference' | 'observation' | 'lesson' | 'context'
  content: string
  source: 'auto' | 'manual'
  confidence: number
  created_at: string | null
  updated_at: string | null
}

export interface ProfileUpdatePayload {
  trading_style?: string | null
  risk_level?: string | null
  focus_sectors?: string[]
  focus_stocks?: string[]
  capital_range?: string | null
  indicators?: string[]
}

export const TRADING_STYLE_OPTIONS = [
  { label: '短线', value: 'short_term' },
  { label: '波段', value: 'swing' },
  { label: '长线', value: 'long_term' },
]

export const RISK_LEVEL_OPTIONS = [
  { label: '保守', value: 'conservative' },
  { label: '稳健', value: 'moderate' },
  { label: '激进', value: 'aggressive' },
]

export const CATEGORY_OPTIONS = [
  { label: '偏好', value: 'preference', color: '#e6a23c' },
  { label: '观察', value: 'observation', color: '#409eff' },
  { label: '经验', value: 'lesson', color: '#67c23a' },
  { label: '上下文', value: 'context', color: '#909399' },
]

export type CategoryMeta = (typeof CATEGORY_OPTIONS)[number]

export function getCategoryMeta(category: string) {
  return CATEGORY_OPTIONS.find(c => c.value === category) || { label: '观察', value: 'observation', color: '#409eff' }
}
