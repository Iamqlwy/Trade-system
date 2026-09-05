import api from './index'
import type { CronJob, CronJobRun, CronCreateRequest, CronUpdateRequest, ContextMessage } from '@/types/cron'

export const cronApi = {
  listJobs() {
    return api.get<{ jobs: CronJob[] }>('/cron/jobs')
  },
  createJob(data: CronCreateRequest) {
    return api.post<{ ok: boolean; job: CronJob }>('/cron/jobs', data)
  },
  updateJob(jobId: string, data: CronUpdateRequest) {
    return api.put<{ ok: boolean; job: CronJob }>(`/cron/jobs/${jobId}`, data)
  },
  deleteJob(jobId: string) {
    return api.delete<{ ok: boolean }>(`/cron/jobs/${jobId}`)
  },
  triggerJob(jobId: string) {
    return api.post<{ ok: boolean; result: Record<string, unknown> }>(`/cron/jobs/${jobId}/run`)
  },
  listRuns(jobId: string) {
    return api.get<{ runs: CronJobRun[] }>(`/cron/jobs/${jobId}/runs`)
  },
  getRunOutput(runId: string) {
    return api.get<{ output: string }>(`/cron/runs/${runId}/output`)
  },
  getRunContext(runId: string) {
    return api.get<{ messages: ContextMessage[] }>(`/cron/runs/${runId}/context`)
  },
  /** 从 cron 运行上下文创建 Agent 会话（用于继续对话） */
  createSessionFromRun(runId: string) {
    return api.post<{ session_id: string; title: string }>(`/cron/runs/${runId}/session`)
  },
}
