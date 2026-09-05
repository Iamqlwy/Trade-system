import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { MessageSummary } from '@/types/message'
import * as messageApi from '@/api/messages'

export const useMessageStore = defineStore('messages', () => {
  const unreadCount = ref(0)

  async function fetchUnreadCount() {
    try {
      const res = await messageApi.getUnreadCount()
      unreadCount.value = res.data.count
    } catch { /* ignore */ }
  }

  function setUnreadCount(count: number) {
    unreadCount.value = count
  }

  function decrementUnread(by = 1) {
    unreadCount.value = Math.max(0, unreadCount.value - by)
  }

  return {
    unreadCount,
    fetchUnreadCount,
    setUnreadCount,
    decrementUnread,
  }
})
