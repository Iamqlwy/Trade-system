export interface CronJob {
  id: string
  user_id: number
  name: string
  schedule: string
  schedule_type: 'cron' | 'interval' | 'oneshot'
  prompt: string
  enabled: boolean
  last_run_at: string | null
  next_run_at: string | null
  created_at: string
  updated_at: string
}

export interface CronJobRun {
  id: string
  job_id: string
  user_id: number
  status: 'running' | 'completed' | 'failed'
  started_at: string
  completed_at: string | null
  output_summary: string
  output_file: string
  context_file: string
  error_message: string
}

export interface CronCreateRequest {
  name: string
  schedule: string
  prompt: string
}

export interface CronUpdateRequest {
  name?: string
  schedule?: string
  prompt?: string
  enabled?: boolean
}

export interface CronEvent {
  type: 'cron_event'
  event: string
  data: Record<string, unknown>
}

// 上下文消息类型（与 AgentView 兼容）
export interface ContextMessage {
  role: string
  content?: string
  tool_calls?: Array<{
    id: string
    type: string
    function: { name: string; arguments: string }
  }>
  tool_call_id?: string
  name?: string
  compact_range?: boolean
}
