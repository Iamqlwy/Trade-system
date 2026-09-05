<template>
  <div class="message-bell" @click="goToInbox">
    <el-badge :value="messageStore.unreadCount" :hidden="messageStore.unreadCount === 0" :max="99">
      <el-icon :size="20">
        <Message />
      </el-icon>
    </el-badge>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { Message } from '@element-plus/icons-vue'
import { useMessageStore } from '@/stores/messages'

const router = useRouter()
const messageStore = useMessageStore()

function goToInbox() {
  router.push('/messages')
}
</script>

<style scoped>
.message-bell {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
  color: var(--text-secondary);
}

.message-bell:hover {
  background: rgba(0, 0, 0, 0.04);
  color: var(--text-primary);
}

:global(html[data-theme="dark"]) .message-bell:hover {
  background: rgba(255, 255, 255, 0.06);
}
</style>
