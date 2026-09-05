<template>
  <div class="settings-page">
    <div class="page-header">
      <div>
        <h2>系统设置</h2>
        <p class="page-desc">管理用户、权限、消息与反馈</p>
      </div>
    </div>

    <el-tabs v-model="activeTab" type="border-card">
      <!-- Tab 1: 用户管理 -->
      <el-tab-pane label="用户管理" name="users">
        <div class="tab-toolbar">
          <el-button type="primary" size="small" @click="showAddUser = true">添加用户</el-button>
        </div>
        <el-table :data="users" stripe size="small" border style="width: 100%">
          <el-table-column prop="username" label="用户名" min-width="120" fixed />
          <el-table-column prop="role" label="角色" width="96">
            <template #default="{ row }">
              <span class="role-tag" :class="row.role === 'admin' ? 'role-admin' : 'role-viewer'">
                {{ row.role === 'admin' ? '管理员' : row.role === 'trader' ? '交易员' : '查看者' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="Agent" width="80" align="center">
            <template #default="{ row }">
              <el-switch
                :model-value="row.role === 'admin' ? true : row.can_use_agent"
                :disabled="row.role === 'admin'"
                size="small"
                @change="(val: boolean) => onPermToggle(row, 'can_use_agent', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="实盘" width="80" align="center">
            <template #default="{ row }">
              <el-switch
                :model-value="row.role === 'admin' ? true : row.can_create_real"
                :disabled="row.role === 'admin'"
                size="small"
                @change="(val: boolean) => onPermToggle(row, 'can_create_real', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="策略上限" width="110" align="center">
            <template #default="{ row }">
              <el-input-number
                v-if="row.role !== 'admin'"
                :model-value="row.max_strategies"
                :min="-1"
                :max="9999"
                size="small"
                controls-position="right"
                style="width: 90px"
                @change="(val: number | undefined) => onPermToggle(row, 'max_strategies', val ?? 0)"
              />
              <span v-else class="perm-hint">∞</span>
            </template>
          </el-table-column>
          <el-table-column label="定时任务" width="90" align="center">
            <template #default="{ row }">
              <el-switch
                :model-value="row.role === 'admin' ? true : row.can_use_cron"
                :disabled="row.role === 'admin'"
                size="small"
                @change="(val: boolean) => onPermToggle(row, 'can_use_cron', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="监控" width="80" align="center">
            <template #default="{ row }">
              <el-switch
                :model-value="row.role === 'admin' ? true : row.can_use_monitor"
                :disabled="row.role === 'admin'"
                size="small"
                @change="(val: boolean) => onPermToggle(row, 'can_use_monitor', val)"
              />
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Tab 2: 用户组 -->
      <el-tab-pane label="用户组" name="groups">
        <GroupManager />
      </el-tab-pane>

      <!-- Tab 3: 策略权限 -->
      <el-tab-pane label="策略权限" name="permissions">
        <div class="tab-toolbar">
          <el-button type="primary" size="small" @click="showGrant = true">授权</el-button>
        </div>
        <el-table :data="permissions" stripe size="small" border style="width: 100%">
          <el-table-column prop="username" label="用户" min-width="110" />
          <el-table-column prop="strategy_name" label="策略" min-width="140" show-overflow-tooltip />
          <el-table-column label="可交易" width="80" align="center">
            <template #default="{ row }">
              <span class="perm-tag" :class="row.can_trade ? 'perm-yes' : 'perm-no'">
                {{ row.can_trade ? '是' : '否' }}
              </span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Tab 4: 工具权限 -->
      <el-tab-pane label="工具权限" name="tools">
        <div class="tab-hint">关闭后对应用户在 AI 助手中无法使用该工具</div>
        <el-table :data="toolPermRows" stripe size="small" border>
          <el-table-column prop="username" label="用户" width="110" fixed />
          <el-table-column
            v-for="tool in toolColumns"
            :key="tool.key"
            :label="tool.label"
            width="88"
            align="center"
          >
            <template #default="{ row }">
              <el-switch
                :model-value="row.tools[tool.key]"
                size="small"
                @change="(val: boolean) => onToolToggle(row, tool.key, val)"
              />
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Tab 5: 消息管理 -->
      <el-tab-pane label="消息管理" name="messages">
        <div class="tab-toolbar">
          <el-button type="primary" size="small" @click="showSendMsg = true">
            <el-icon style="margin-right: 4px"><EditPen /></el-icon>
            发送消息
          </el-button>
        </div>
        <el-table :data="sentMessages" stripe size="small" border>
          <el-table-column prop="title" label="标题" min-width="240" show-overflow-tooltip />
          <el-table-column label="收件人数" width="90" align="center">
            <template #default="{ row }">{{ row.recipient_count }}</template>
          </el-table-column>
          <el-table-column label="已读数" width="90" align="center">
            <template #default="{ row }">
              <span :style="{ color: row.read_count > 0 ? 'var(--color-success)' : 'var(--text-muted)' }">
                {{ row.read_count }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="发送时间" width="130" align="center">
            <template #default="{ row }">
              <span class="time-cell">{{ formatFbTime(row.created_at) }}</span>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="sentMessages.length === 0" description="暂无已发送消息" :image-size="60" />
      </el-tab-pane>

      <!-- Tab 6: 反馈管理 -->
      <el-tab-pane label="反馈管理" name="feedback">
        <div class="tab-toolbar">
          <div style="display: flex; align-items: center; gap: 10px">
            <span v-if="fbCounts.pending > 0" class="fb-pending-badge">{{ fbCounts.pending }} 待处理</span>
          </div>
          <div style="display: flex; align-items: center; gap: 8px">
            <el-select v-model="fbFilter" size="small" style="width: 120px" @change="loadFeedback">
              <el-option label="全部" value="" />
              <el-option label="待处理" value="pending" />
              <el-option label="处理中" value="in_progress" />
              <el-option label="已解决" value="resolved" />
              <el-option label="已关闭" value="closed" />
            </el-select>
          </div>
        </div>
        <el-table :data="feedbackList" stripe size="small" border v-loading="fbLoading">
          <el-table-column label="时间" width="110" align="center">
            <template #default="{ row }">
              <span class="time-cell">{{ formatFbTime(row.created_at) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="username" label="用户" width="100" />
          <el-table-column label="类型" width="80" align="center">
            <template #default="{ row }">
              <span :class="['fb-type-tag-mini', row.type]">{{ fbTypeLabel(row.type) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <span :class="['fb-status-tag-mini', row.status]">{{ fbStatusLabel(row.status) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" align="center">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="openReplyDialog(row)">
                {{ row.admin_reply ? '查看' : '回复' }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- Dialogs -->

    <!-- Add User Dialog -->
    <el-dialog v-model="showAddUser" title="添加用户" width="420px">
      <el-form :model="newUser" label-width="80px">
        <el-form-item label="用户名">
          <el-input v-model="newUser.username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="newUser.password" type="password" show-password />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="newUser.role">
            <el-option value="viewer" label="查看者" />
            <el-option value="admin" label="管理员" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddUser = false">取消</el-button>
        <el-button type="primary" @click="addUser">确定</el-button>
      </template>
    </el-dialog>

    <!-- Grant Permission Dialog -->
    <el-dialog v-model="showGrant" title="策略授权" width="420px">
      <el-form :model="grantForm" label-width="80px">
        <el-form-item label="用户">
          <el-select v-model="grantForm.username">
            <el-option v-for="u in users" :key="u.username" :label="u.username" :value="u.username" />
          </el-select>
        </el-form-item>
        <el-form-item label="策略">
          <el-select v-model="grantForm.strategyId">
            <el-option v-for="s in strategies" :key="s.strategy_id" :label="s.name" :value="s.strategy_id" />
          </el-select>
        </el-form-item>
        <el-form-item label="可交易">
          <el-switch v-model="grantForm.canTrade" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showGrant = false">取消</el-button>
        <el-button type="primary" @click="grantPermission">确定</el-button>
      </template>
    </el-dialog>

    <!-- Send Message Dialog -->
    <el-dialog v-model="showSendMsg" title="发送站内信" width="560px">
      <el-form :model="sendMsgForm" label-width="80px">
        <el-form-item label="标题">
          <el-input v-model="sendMsgForm.title" maxlength="200" placeholder="消息标题" />
        </el-form-item>
        <el-form-item label="正文">
          <el-input
            v-model="sendMsgForm.content"
            type="textarea"
            :rows="6"
            maxlength="10000"
            show-word-limit
            placeholder="消息正文..."
          />
        </el-form-item>
        <el-form-item label="收件人">
          <el-radio-group v-model="sendTargetType" style="margin-right: 10px">
            <el-radio value="all">全部用户</el-radio>
            <el-radio value="specific">指定用户</el-radio>
          </el-radio-group>
          <el-select
            v-if="sendTargetType === 'specific'"
            v-model="sendMsgForm.recipient_ids"
            multiple
            filterable
            placeholder="选择收件人"
            style="width: 100%; margin-top: 8px"
          >
            <el-option
              v-for="u in nonAdminUsers"
              :key="u.id"
              :label="u.username"
              :value="u.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showSendMsg = false">取消</el-button>
        <el-button type="primary" @click="doSendMessage" :loading="sendingMsg">发送</el-button>
      </template>
    </el-dialog>

    <!-- Feedback Reply Dialog -->
    <el-dialog v-model="fbReplyVisible" title="反馈详情" width="560px">
      <div v-if="fbCurrent" class="fb-detail-view">
        <div class="fb-detail-meta">
          <span :class="['fb-type-tag-mini', fbCurrent.type]">{{ fbTypeLabel(fbCurrent.type) }}</span>
          <span :class="['fb-status-tag-mini', fbCurrent.status]">{{ fbStatusLabel(fbCurrent.status) }}</span>
          <span class="fb-detail-user">{{ fbCurrent.username }}</span>
          <span class="fb-detail-time">{{ formatFbTime(fbCurrent.created_at) }}</span>
        </div>
        <div class="fb-detail-title">{{ fbCurrent.title }}</div>
        <div class="fb-detail-content">{{ fbCurrent.content }}</div>
        <div v-if="fbCurrent.admin_reply" class="fb-detail-reply">
          <div class="fb-detail-reply-label">管理员回复</div>
          <div class="fb-detail-reply-content">{{ fbCurrent.admin_reply }}</div>
        </div>
      </div>
      <el-divider />
      <el-form label-width="80px">
        <el-form-item label="更新状态">
          <el-select v-model="fbReplyForm.status" style="width: 100%">
            <el-option label="待处理" value="pending" />
            <el-option label="处理中" value="in_progress" />
            <el-option label="已解决" value="resolved" />
            <el-option label="已关闭" value="closed" />
          </el-select>
        </el-form-item>
        <el-form-item label="回复内容">
          <el-input
            v-model="fbReplyForm.admin_reply"
            type="textarea"
            :rows="4"
            placeholder="回复用户反馈..."
            maxlength="2000"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="fbReplyVisible = false">取消</el-button>
        <el-button type="primary" @click="submitReply" :loading="fbReplying">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { showApiError } from '@/utils/notify'
import { EditPen } from '@element-plus/icons-vue'
import { useStrategiesStore } from '@/stores/strategies'
import api from '@/api'
import * as feedbackApi from '@/api/feedback'
import * as messageApi from '@/api/messages'
import GroupManager from '@/components/settings/GroupManager.vue'
import type { AdminFeedbackItem, FeedbackCounts } from '@/types/feedback'
import type { SentMessageItem } from '@/types/message'

const strategiesStore = useStrategiesStore()
const strategies = computed(() => strategiesStore.strategies)

const activeTab = ref('users')

// ── 用户管理 ──
interface UserInfoWithPerms {
  id: number
  username: string
  role: string
  can_use_agent: boolean
  can_create_real: boolean
  max_strategies: number
  can_use_cron: boolean
  can_use_monitor: boolean
}

const users = ref<UserInfoWithPerms[]>([])
const showAddUser = ref(false)
const newUser = reactive({ username: '', password: '', role: 'viewer' })

// 非 admin 用户列表
const nonAdminUsers = computed(() => users.value.filter(u => u.role !== 'admin'))

// ── 策略权限 ──
const permissions = ref<{ username: string; strategy_name: string; can_trade: boolean }[]>([])
const showGrant = ref(false)
const grantForm = reactive({ username: '', strategyId: '', canTrade: true })

// ── 工具权限 ──
interface ToolPermUser {
  user_id: number
  username: string
  tools: Record<string, boolean>
}

const toolPermData = ref<ToolPermUser[]>([])
const toolColumns = ref<{ key: string; label: string }[]>([])
const toolPermRows = computed(() => toolPermData.value)

// ── 发送消息 ──
const showSendMsg = ref(false)
const sendingMsg = ref(false)
const sendTargetType = ref<'all' | 'specific'>('all')
const sendMsgForm = reactive({
  title: '',
  content: '',
  recipient_ids: [] as number[],
})
const sentMessages = ref<SentMessageItem[]>([])

// ── 反馈管理 ──
const feedbackList = ref<AdminFeedbackItem[]>([])
const fbLoading = ref(false)
const fbFilter = ref('')
const fbCounts = reactive<FeedbackCounts>({ total: 0, pending: 0, in_progress: 0, resolved: 0, closed: 0 })
const fbReplyVisible = ref(false)
const fbReplying = ref(false)
const fbCurrent = ref<AdminFeedbackItem | null>(null)
const fbReplyForm = reactive({ status: '', admin_reply: '' })

// ── 数据加载 ──

async function loadUsers() {
  try {
    const res = await api.get('/settings/users')
    users.value = res.data
  } catch { /* ignore */ }
}

async function loadPermissions() {
  try {
    const res = await api.get('/settings/permissions')
    permissions.value = res.data
  } catch { /* ignore */ }
}

async function loadToolPermissions() {
  try {
    const res = await api.get('/settings/tool-permissions')
    toolPermData.value = res.data
  } catch { /* ignore */ }
}

async function loadToolColumns() {
  try {
    const res = await api.get('/settings/tools')
    toolColumns.value = res.data
  } catch { /* ignore */ }
}

async function loadSentMessages() {
  try {
    const res = await messageApi.getSentMessages({ page: 1, page_size: 50 })
    sentMessages.value = res.data.items || []
  } catch { /* ignore */ }
}

// ── 操作 ──

async function addUser() {
  try {
    await api.post('/settings/users', newUser)
    ElMessage.success('用户添加成功')
    showAddUser.value = false
    newUser.username = ''
    newUser.password = ''
    newUser.role = 'viewer'
    loadUsers()
    loadToolPermissions()
  } catch (err) {
    showApiError(err, '添加失败')
  }
}

async function grantPermission() {
  try {
    await api.post('/settings/permissions', grantForm)
    ElMessage.success('授权成功')
    showGrant.value = false
    loadPermissions()
  } catch (err) {
    showApiError(err, '授权失败')
  }
}

async function onToolToggle(row: ToolPermUser, toolKey: string, enabled: boolean) {
  try {
    await api.post('/settings/tool-permissions', {
      username: row.username,
      toolKey,
      enabled,
    })
    row.tools[toolKey] = enabled
    ElMessage.success(`已${enabled ? '启用' : '禁用'} ${row.username} 的 ${toolKey}`)
  } catch (err) {
    showApiError(err, '设置失败')
  }
}

type PermKey = 'can_use_agent' | 'can_create_real' | 'max_strategies' | 'can_use_cron' | 'can_use_monitor'

async function onPermToggle(row: UserInfoWithPerms, key: PermKey, value: boolean | number) {
  if (row.role === 'admin') return
  try {
    await api.put(`/settings/users/${row.username}/permissions`, { [key]: value })
    ;(row as any)[key] = value
    ElMessage.success(`已更新 ${row.username} 的权限`)
  } catch (err) {
    showApiError(err, '权限更新失败')
  }
}

async function doSendMessage() {
  if (!sendMsgForm.title.trim()) {
    ElMessage.warning('请输入消息标题')
    return
  }
  if (!sendMsgForm.content.trim()) {
    ElMessage.warning('请输入消息正文')
    return
  }
  sendingMsg.value = true
  try {
    await messageApi.sendMessage({
      title: sendMsgForm.title.trim(),
      content: sendMsgForm.content.trim(),
      recipient_ids: sendTargetType.value === 'all' ? [] : sendMsgForm.recipient_ids,
    })
    ElMessage.success('消息已发送')
    showSendMsg.value = false
    sendMsgForm.title = ''
    sendMsgForm.content = ''
    sendMsgForm.recipient_ids = []
    sendTargetType.value = 'all'
    loadSentMessages()
  } catch (err: any) {
    showApiError(err, '发送失败')
  } finally {
    sendingMsg.value = false
  }
}

// ── 反馈操作 ──

function fbTypeLabel(type: string): string {
  const map: Record<string, string> = { bug: 'Bug', feature: '功能建议', question: '使用问题', other: '其他' }
  return map[type] || type
}

function fbStatusLabel(status: string): string {
  const map: Record<string, string> = { pending: '待处理', in_progress: '处理中', resolved: '已解决', closed: '已关闭' }
  return map[status] || status
}

function formatFbTime(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) + ' ' +
    d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

async function loadFeedback() {
  fbLoading.value = true
  try {
    const res = await feedbackApi.listAllFeedback(fbFilter.value || undefined)
    feedbackList.value = res.data
  } catch { /* ignore */ }
  finally { fbLoading.value = false }
}

async function loadFeedbackCounts() {
  try {
    const res = await feedbackApi.getFeedbackCounts()
    Object.assign(fbCounts, res.data)
  } catch { /* ignore */ }
}

function openReplyDialog(row: AdminFeedbackItem) {
  fbCurrent.value = row
  fbReplyForm.status = row.status
  fbReplyForm.admin_reply = row.admin_reply || ''
  fbReplyVisible.value = true
}

async function submitReply() {
  if (!fbCurrent.value) return
  fbReplying.value = true
  try {
    await feedbackApi.replyFeedback(fbCurrent.value.id, {
      status: fbReplyForm.status,
      admin_reply: fbReplyForm.admin_reply || undefined,
    })
    ElMessage.success('反馈已更新')
    fbReplyVisible.value = false
    loadFeedback()
    loadFeedbackCounts()
  } catch (err: any) {
    showApiError(err, '更新失败')
  } finally { fbReplying.value = false }
}

onMounted(() => {
  strategiesStore.fetchStrategies()
  loadUsers()
  loadPermissions()
  loadToolPermissions()
  loadToolColumns()
  loadFeedback()
  loadFeedbackCounts()
  loadSentMessages()
})
</script>

<style scoped>
.settings-page {
  width: 100%;
}

.page-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 4px;
}

/* ── Tabs ── */
:deep(.el-tabs--border-card) {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg, 8px);
  box-shadow: none;
}

:deep(.el-tabs--border-card > .el-tabs__header) {
  background: rgba(0, 0, 0, 0.02);
  border-bottom: 1px solid var(--border-subtle);
}

:deep(.el-tabs--border-card > .el-tabs__content) {
  padding: 20px;
}

:deep(.el-tab-pane) {
  min-height: 200px;
}

/* ── Tab Toolbar ── */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 10px;
}

.tab-hint {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 12px;
}

/* ── Tags ── */
.role-tag {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 4px;
}

.role-admin {
  color: var(--color-up);
  background: var(--color-up-bg);
}

.role-viewer {
  color: var(--text-secondary);
  background: #f3f4f6;
}

.perm-tag {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 4px;
}

.perm-yes {
  color: var(--color-success);
  background: rgba(22, 163, 74, 0.08);
}

.perm-no {
  color: var(--text-muted);
  background: #f3f4f6;
}

.perm-hint {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

.time-cell {
  font-size: 12px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}

/* ── Feedback ── */
.fb-pending-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  color: #f59e0b;
  background: rgba(245, 158, 11, 0.1);
}

.fb-type-tag-mini {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 3px;
}

.fb-type-tag-mini.bug { color: #dc2626; background: rgba(220, 38, 38, 0.08); }
.fb-type-tag-mini.feature { color: #2563eb; background: rgba(37, 99, 235, 0.08); }
.fb-type-tag-mini.question { color: #7c3aed; background: rgba(124, 58, 237, 0.08); }
.fb-type-tag-mini.other { color: var(--text-secondary); background: rgba(0, 0, 0, 0.04); }

.fb-status-tag-mini {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 3px;
}

.fb-status-tag-mini.pending { color: #f59e0b; background: rgba(245, 158, 11, 0.08); }
.fb-status-tag-mini.in_progress { color: #3b82f6; background: rgba(59, 130, 246, 0.08); }
.fb-status-tag-mini.resolved { color: #16a34a; background: rgba(22, 163, 74, 0.08); }
.fb-status-tag-mini.closed { color: var(--text-muted); background: rgba(0, 0, 0, 0.04); }

.fb-detail-view {
  padding: 0 4px;
}

.fb-detail-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.fb-detail-user {
  font-size: 13px;
  color: var(--text-secondary);
  margin-left: auto;
}

.fb-detail-time {
  font-size: 12px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.fb-detail-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.fb-detail-content {
  font-size: 13.5px;
  line-height: 1.7;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

.fb-detail-reply {
  margin-top: 12px;
}

.fb-detail-reply-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-accent);
  margin-bottom: 4px;
}

.fb-detail-reply-content {
  font-size: 13.5px;
  line-height: 1.7;
  color: var(--text-primary);
  white-space: pre-wrap;
  background: rgba(176, 141, 71, 0.04);
  border: 1px solid rgba(176, 141, 71, 0.12);
  border-radius: var(--radius-md);
  padding: 10px 12px;
}
</style>
