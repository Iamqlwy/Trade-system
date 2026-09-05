export interface ScriptParamDef {
  name: string
  label: string
  type: 'string' | 'int' | 'float' | 'bool' | 'choice'
  default: string | number | boolean
  description?: string
  min?: number
  max?: number
  choices?: { value: string; label: string }[]
}

export interface ScriptMetadata {
  name: string
  description: string
  version: string
  has_stock_param: boolean
  parameters: ScriptParamDef[]
}

export interface MonitorInfo {
  monitor_id: string
  monitor_name: string
  description: string
  stock_codes: string[]
  strategy_ids: string[]
  interval: string
  trigger_mode: string
  enabled: boolean
  cooldown_seconds: number
  script_metadata: ScriptMetadata
  params: Record<string, unknown>
  last_run: string | null
  last_result: MonitorLastResult | null
  error_message: string
}

export interface MonitorLastResult {
  stock_code: string
  triggered: boolean
  message: string
  time: string
}

export interface MonitorDetail extends MonitorInfo {
  script_content: string
}

export interface MonitorAlert {
  monitor_id: string
  monitor_name: string
  stock_code: string
  stock_name?: string
  triggered: boolean
  message: string
  data: Record<string, unknown> | null
  timestamp: string
}

export interface MonitorRunResult {
  monitor_id: string
  results: {
    stock_codes: string[]
    result: { stock_code?: string; triggered: boolean; message: string; data?: Record<string, unknown> }[] | null
    error: string | null
  }[]
}

export interface MonitorUpdateRequest {
  monitor_name?: string
  description?: string
  stock_codes?: string[]
  strategy_ids?: string[]
  interval?: string
  trigger_mode?: string
  enabled?: boolean
  cooldown_seconds?: number
  params?: Record<string, unknown>
}

export interface StrategyOption {
  strategy_id: string
  name: string
  position_count: number
  position_codes: string[]
}

export interface StockOption {
  ts_code: string
  symbol: string
  name: string
  cnspell: string
  industry: string
}
