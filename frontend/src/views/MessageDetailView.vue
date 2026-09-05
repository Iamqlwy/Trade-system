<template>
  <div class="message-detail-page">
    <div class="page-header">
      <el-button :icon="ArrowLeft" @click="$router.push('/messages')" size="small">返回收件箱</el-button>
    </div>

    <el-card shadow="never" v-loading="loading">
      <template v-if="detail">
        <div class="msg-detail-header">
          <h3 class="msg-detail-title">{{ detail.title }}</h3>
          <div class="msg-detail-meta">
            <span class="msg-sender">发件人：{{ detail.sender_name }}</span>
            <span class="msg-time">{{ formatTime(detail.created_at) }}</span>
            <span v-if="detail.read_at" class="msg-read-at">已读于 {{ formatTime(detail.read_at) }}</span>
          </div>
        </div>
        <el-divider />
        <div class="msg-detail-content">{{ detail.content }}</div>
        <el-divider />
        <div class="msg-actions">
          <el-button
            :type="detail.is_read ? 'default' : 'primary'"
            size="small"
            @click="toggleRead"
          >
            {{ detail.is_read ? '标为未读' : '标为已读' }}
          </el-button>
          <el-popconfirm
            title="删除这条消息？"
            confirm-button-text="删除"
            @confirm="handleDelete"
          >
            <template #reference>
              <el-button type="danger" size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </div>
      </template>
      <el-empty v-else description="消息不存在" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { showApiError } from '@/utils/notify'
import { ArrowLeft } from '@element-plus/icons-vue'
import * as messageApi from '@/api/messages'
import { useMessageStore } from '@/stores/messages'
import type { MessageDetail } from '@/types/message'

const route = useRoute()
const router = useRouter()
const messageStore = useMessageStore()

const detail = ref<MessageDetail | null>(null)
const loading = ref(false)

async function loadDetail() {
  const id = Number(route.params.id)
  if (!id) return
  loading.value = true
  try {
    const res = await messageApi.getMessageDetail(id)
    detail.value = res.data
  } catch (err) {
    showApiError(err, '消息不存在或无权访问')
    router.push('/messages')
  } finally {
    loading.value = false
  }
}

async function toggleRead() {
  if (!detail.value) return
  const newState = !detail.value.is_read
  try {
    await messageApi.markRead(detail.value.id, newState)
    detail.value.is_read = newState
    if (newState && !detail.value.read_at) {
      detail.value.read_at = new Date().toISOString()
    } else if (!newState) {
      detail.value.read_at = null
    }
    messageStore.fetchUnreadCount()
    ElMessage.success(newState ? '已标为已读' : '已标为未读')
  } catch (err) {
    showApiError(err, '操作失败')
  }
}

async function handleDelete() {
  if (!detail.value) return
  try {
    await messageApi.deleteMessage(detail.value.id)
    if (!detail.value.is_read) {
      messageStore.decrementUnread(1)
    }
    ElMessage.success('已删除')
    router.push('/messages')
  } catch (err) {
    showApiError(err, '删除失败')
  }
}

function formatTime(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) +
    ' ' + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

onMounted(() => {
  loadDetail()
})
</script>

<style scoped>
.message-detail-page {
  width: 100%;
  max-width: 800px;
}

.msg-detail-header {
  margin-bottom: 8px;
}

.msg-detail-title {
  font-family: var(--font-display);
  font-weight: 600;
  font-size: 18px;
  margin: 0 0 12px;
  color: var(--text-primary);
}

.msg-detail-meta {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  font-size: 13px;
  color: var(--text-secondary);
}

.msg-sender {
  color: var(--text-primary);
  font-weight: 500;
}

.msg-time, .msg-read-at {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 12px;
}

.msg-detail-content {
  font-size: 14px;
  line-height: 1.8;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
  min-height: 120px;
}

.msg-actions {
  display: flex;
  gap: 10px;
}
</style>
