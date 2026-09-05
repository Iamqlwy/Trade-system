<template>
  <el-container class="app-layout">
    <AppSidebar />
    <el-container class="main-container">
      <AppHeader />
      <el-main class="main-content">
        <router-view v-slot="{ Component }">
          <transition name="page-slide" mode="out-in">
            <keep-alive :include="['AgentView', 'KnowledgeSearchView']">
              <component :is="Component" />
            </keep-alive>
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>

  <!-- 下单确认弹窗（全局） -->
  <OrderConfirmDialog
    v-if="currentConfirm"
    :item="currentConfirm"
    :visible="!!currentConfirm"
    @close="handleConfirmClose"
    @approved="handleConfirmApproved"
    @rejected="handleConfirmRejected"
  />
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, computed, watch } from 'vue'
import AppSidebar from './AppSidebar.vue'
import AppHeader from './AppHeader.vue'
import OrderConfirmDialog from '@/components/common/OrderConfirmDialog.vue'
import { useTickStream } from '@/composables/useTickStream'
import { useNotifications } from '@/composables/useNotifications'
import { useMessageStore } from '@/stores/messages'
import { useAuthStore } from '@/stores/auth'

// Global WebSocket tick stream connection
const { connect } = useTickStream()
connect()

// 通知系统（下单确认）
const { pendingConfirmations, removeConfirmation } = useNotifications()
const currentConfirm = computed(() => pendingConfirmations.value[0] || null)

function handleConfirmClose() {
  if (currentConfirm.value) {
    removeConfirmation(currentConfirm.value.confirmation_id)
  }
}

function handleConfirmApproved(orderId: string) {
  if (currentConfirm.value) {
    removeConfirmation(currentConfirm.value.confirmation_id)
  }
}

function handleConfirmRejected() {
  if (currentConfirm.value) {
    removeConfirmation(currentConfirm.value.confirmation_id)
  }
}

// Poll unread message count every 30 seconds
const messageStore = useMessageStore()
const authStore = useAuthStore()
let pollTimer: ReturnType<typeof setInterval> | null = null

function startPolling() {
  stopPolling()
  if (!authStore.isAuthenticated) return
  messageStore.fetchUnreadCount()
  pollTimer = setInterval(() => {
    // 每次 tick 检查认证状态，登出后停止轮询
    if (!authStore.isAuthenticated) {
      stopPolling()
      return
    }
    messageStore.fetchUnreadCount()
  }, 30000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

onMounted(() => {
  startPolling()
})

// 登出时立即停止轮询
watch(() => authStore.token, (token) => {
  if (!token) stopPolling()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.app-layout {
  height: 100dvh;
  overflow: hidden;
}

.main-container {
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.main-content {
  background: var(--color-bg);
  overflow-y: auto;
  padding: 24px 28px;
}

@media (max-width: 768px) {
  .main-content {
    padding: 16px;
  }
}

/* ── Page Transition ── */
.page-slide-enter-active {
  transition: opacity 0.3s cubic-bezier(0.16, 1, 0.3, 1),
    transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.page-slide-leave-active {
  transition: opacity 0.15s ease-in, transform 0.15s ease-in;
}

.page-slide-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.page-slide-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
