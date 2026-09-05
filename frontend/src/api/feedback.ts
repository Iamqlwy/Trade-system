import api from './index'
import type { Feedback, FeedbackDetail, FeedbackSubmit, AdminFeedbackItem, FeedbackCounts } from '@/types/feedback'

/** 提交反馈 */
export function submitFeedback(data: FeedbackSubmit) {
  return api.post<{ id: number; status: string }>('/feedback', data)
}

/** 列出当前用户的反馈 */
export function listMyFeedback() {
  return api.get<Feedback[]>('/feedback')
}

/** 查看反馈详情 */
export function getFeedback(id: number) {
  return api.get<FeedbackDetail>(`/feedback/${id}`)
}

/** 管理员：列出全部反馈 */
export function listAllFeedback(status?: string) {
  return api.get<AdminFeedbackItem[]>('/settings/feedback', { params: { status } })
}

/** 管理员：各状态数量 */
export function getFeedbackCounts() {
  return api.get<FeedbackCounts>('/settings/feedback/count')
}

/** 管理员：回复/更新反馈 */
export function replyFeedback(id: number, data: { status?: string; admin_reply?: string }) {
  return api.put(`/settings/feedback/${id}`, data)
}
