import { ref, onUnmounted } from 'vue'
import { useWebSocket } from './useWebSocket'
import { ElNotification } from 'element-plus'
import { notify } from './useNotification'
import type { MonitorAlert } from '@/types/monitor'

export function useMonitorAlerts() {
  const alerts = ref<MonitorAlert[]>([])

  const { connected, connect, disconnect } = useWebSocket('/ws/monitor', {
    onMessage: (data) => {
      const alert = data as MonitorAlert
      if (alert.triggered) {
        alerts.value.unshift(alert)
        // 最多保留 200 条
        if (alerts.value.length > 200) {
          alerts.value = alerts.value.slice(0, 200)
        }
        // 兜底空文本，防止通知无内容或一闪而过
        const monitorLabel = alert.monitor_name || alert.monitor_id || '未知监控'
        const messageText = alert.message?.trim() || `${monitorLabel} 触发告警`
        const titleText = `监控告警 - ${monitorLabel}`

        // 应用内 toast
        ElNotification({
          title: titleText,
          message: messageText,
          type: 'warning',
          duration: 8000,
        })
        // OS 桌面通知
        const stockLabel = alert.stock_name
          ? `${alert.stock_name} (${alert.stock_code})`
          : alert.stock_code
        notify({
          title: titleText,
          body: `${stockLabel ? stockLabel + ': ' : ''}${messageText}`,
          tag: `monitor-${alert.monitor_id}-${alert.stock_code}`,
          navigateTo: '/monitors',
        })
      }
    },
  })

  function clearAlerts() {
    alerts.value = []
  }

  onUnmounted(() => {
    disconnect()
  })

  return { alerts, connected, connect, disconnect, clearAlerts }
}
