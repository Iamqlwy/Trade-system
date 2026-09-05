<template>
  <div class="messages-page">
    <div class="page-header">
      <div>
        <h2>消息中心</h2>
        <p class="page-desc">查看管理员发送的系统消息</p>
      </div>
    </div>

    <div class="messages-card">
      <!-- Toolbar -->
      <div class="toolbar">
        <el-radio-group v-model="filterStatus" size="small" @change="onFilterChange">
          <el-radio-button value="all">全部</el-radio-button>
          <el-radio-button value="unread">未读</el-radio-button>
          <el-radio-button value="read">已读</el-radio-button>
        </el-radio-group>
        <div class="toolbar-right">
          <el-button
            size="small"
            :disabled="selectedIds.length === 0"
            @click="batchDelete"
          >
            批量删除
          </el-button>
          <el-button size="small" :icon="RefreshRight" @click="loadMessages" :loading="loading">
            刷新
          </el-button>
        </div>
      </div>

      <!-- Message List -->
      <el-table
        :data="messages"
        stripe
        size="small"
        style="width: 100%"
        v-loading="loading"
        @selection-change="onSelectionChange"
        @row-click="openDetail"
        highlight-current-row
        :row-class-name="rowClass"
      >
        <el-table-column type="selection" width="42" />
        <el-table-column label="标题" min-width="320">
          <template #default="{ row }">
            <div class="msg-cell">
              <div class="msg-title-row">
                <span v-if="!row.is_read" class="unread-dot" />
                <span class="msg-title">{{ row.title }}</span>
              </div>
              <div class="msg-preview" v-if="row.content">
                {{ row.content.substring(0, 100) }}{{ row.content.length > 100 ? '...' : '' }}
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="sender_name" label="发件人" width="120" align="center" />
        <el-table-column label="时间" width="170" align="center">
          <template #default="{ row }">
            <span class="msg-time">{{ formatTime(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-popconfirm
              title="删除这条消息？"
              confirm-button-text="删除"
              @confirm.stop="handleDelete(row.id)"
            >
              <template #reference>
                <el-button type="danger" link size="small" @click.stop>删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <!-- Pagination -->
      <div class="pagination-row" v-if="total > 0">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          size="small"
          @change="loadMessages"
        />
      </div>

      <el-empty v-if="messages.length === 0 && !loading" description="暂无消息" :image-size="80" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { showApiError } from '@/utils/notify'
import { RefreshRight } from '@element-plus/icons-vue'
import * as messageApi from '@/api/messages'
import { useMessageStore } from '@/stores/messages'
import type { MessageSummary } from '@/types/message'

const router = useRouter()
const messageStore = useMessageStore()

const messages = ref<MessageSummary[]>([])
const loading = ref(false)
const filterStatus = ref('all')
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)
const selectedIds = ref<number[]>([])

function onSelectionChange(rows: MessageSummary[]) {
  selectedIds.value = rows.map(r => r.id)
}

function rowClass({ row }: { row: MessageSummary }) {
  return row.is_read ? '' : 'row-unread'
}

async function loadMessages() {
  loading.value = true
  try {
    const res = await messageApi.getMessages({
      page: currentPage.value,
      page_size: pageSize.value,
      status: filterStatus.value !== 'all' ? filterStatus.value : undefined,
    })
    messages.value = res.data.items || []
    total.value = res.data.total || 0
  } catch (err) {
    showApiError(err, '加载消息失败')
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  currentPage.value = 1
  loadMessages()
}

function openDetail(row: MessageSummary) {
  router.push(`/messages/${row.id}`)
}

async function handleDelete(id: number) {
  try {
    await messageApi.deleteMessage(id)
    const msg = messages.value.find(m => m.id === id)
    if (msg && !msg.is_read) {
      messageStore.decrementUnread(1)
    }
    messages.value = messages.value.filter(m => m.id !== id)
    total.value = Math.max(0, total.value - 1)
    ElMessage.success('已删除')
  } catch (err) {
    showApiError(err, '删除失败')
  }
}

async function batchDelete() {
  try {
    await messageApi.batchDeleteMessages({ ids: selectedIds.value })
    const deletedUnread = messages.value.filter(
      m => selectedIds.value.includes(m.id) && !m.is_read
    ).length
    messageStore.decrementUnread(deletedUnread)
    messages.value = messages.value.filter(m => !selectedIds.value.includes(m.id))
    total.value = Math.max(0, total.value - selectedIds.value.length)
    selectedIds.value = []
    ElMessage.success('批量删除完成')
  } catch (err) {
    showApiError(err, '批量删除失败')
  }
}

function formatTime(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) +
    ' ' + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

onMounted(() => {
  loadMessages()
})
</script>

<style scoped>
.messages-page {
  width: 100%;
}

.page-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 4px;
}

.messages-card {
  background: var(--color-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg, 8px);
  padding: 20px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 10px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.msg-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.msg-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.unread-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-accent);
  flex-shrink: 0;
}

.msg-title {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.msg-preview {
  font-size: 12px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.msg-time {
  font-size: 12px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.pagination-row {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}

:deep(.row-unread) {
  font-weight: 600;
}
</style>
