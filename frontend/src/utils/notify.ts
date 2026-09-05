/**
 * 统一通知工具
 *
 * 解决三个问题：
 * 1. 错误通知一闪而过 —— 错误/警告使用更长 duration
 * 2. 通知没有文字 —— 提供 fallback 兜底
 * 3. 静默失败 —— 提供 showApiError 统一提取后端错误信息
 */
import { ElMessage, ElNotification } from 'element-plus'

/** 从 axios 错误中提取后端返回的 detail 信息 */
export function extractErrorMessage(err: unknown, fallback = '操作失败'): string {
  const detail =
    (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
    (err as { message?: string })?.message ||
    ''
  return detail.trim() || fallback
}

/**
 * 显示 API 错误通知
 * 自动从 axios 错误中提取 detail，duration 更长、可关闭
 */
export function showApiError(err: unknown, fallback = '操作失败'): void {
  const msg = extractErrorMessage(err, fallback)
  ElMessage.error({
    message: msg,
    duration: 5000,
    showClose: true,
  })
}

/** 显示错误通知（较长停留时间） */
export function showError(msg: string): void {
  ElMessage.error({
    message: msg,
    duration: 5000,
    showClose: true,
  })
}

/** 显示警告通知（较长停留时间） */
export function showWarning(msg: string): void {
  ElMessage.warning({
    message: msg,
    duration: 4000,
    showClose: true,
  })
}

/** 显示成功通知 */
export function showSuccess(msg: string): void {
  ElMessage.success(msg)
}

/** 显示信息通知 */
export function showInfo(msg: string): void {
  ElMessage.info(msg)
}

/**
 * 显示通知弹窗（用于系统级通知，如监控告警）
 * 当 title/message 为空时提供兜底
 */
export function showNotificationAlert(
  title: string,
  message: string,
  type: 'success' | 'warning' | 'error' | 'info' = 'info',
): void {
  const safeTitle = title?.trim() || '系统通知'
  const safeMessage = message?.trim() || title?.trim() || '收到一条新通知'

  ElNotification({
    title: safeTitle,
    message: safeMessage,
    type,
    duration: type === 'error' || type === 'warning' ? 8000 : 5000,
  })
}
