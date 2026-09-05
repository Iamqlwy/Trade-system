<template>
  <div class="api-tokens-page">
    <!-- Header -->
    <div class="page-header">
      <div>
        <h1 class="page-title">API Token 管理</h1>
        <p class="page-desc">创建和管理 API Token，用于外部脚本/程序接入平台进行交易操作。</p>
      </div>
      <el-button type="primary" @click="showCreateDialog = true">
        <el-icon><Plus /></el-icon>
        创建 Token
      </el-button>
    </div>

    <!-- Token List -->
    <div v-loading="loading" class="token-list">
      <div v-if="tokens.length === 0 && !loading" class="empty-state">
        <el-empty description="暂无 API Token，点击上方按钮创建">
          <el-button type="primary" @click="showCreateDialog = true">创建第一个 Token</el-button>
        </el-empty>
      </div>

      <div v-for="token in tokens" :key="token.id" class="token-card" :class="{ inactive: !token.is_active }">
        <div class="token-main">
          <div class="token-info">
            <div class="token-name">
              <el-icon :size="16"><Key /></el-icon>
              <span>{{ token.name || '未命名 Token' }}</span>
              <el-tag v-if="!token.is_active" size="small" type="danger">已禁用</el-tag>
              <el-tag v-else size="small" type="success">启用中</el-tag>
            </div>
            <div class="token-meta">
              <span class="meta-item">
                <el-icon :size="12"><Calendar /></el-icon>
                创建于 {{ formatDate(token.created_at) }}
              </span>
              <span class="meta-item" v-if="token.last_used_at">
                <el-icon :size="12"><Clock /></el-icon>
                最后使用 {{ formatDate(token.last_used_at) }}
              </span>
              <span class="meta-item" v-if="token.expires_at">
                <el-icon :size="12"><Timer /></el-icon>
                过期时间 {{ formatDate(token.expires_at) }}
              </span>
              <span class="meta-item" v-else>
                <el-icon :size="12"><Timer /></el-icon>
                永不过期
              </span>
            </div>
          </div>

          <div class="token-actions">
            <el-button size="small" @click="openEditDialog(token)">编辑</el-button>
            <el-popconfirm
              title="确定要删除此 Token 吗？删除后无法恢复。"
              confirm-button-text="删除"
              cancel-button-text="取消"
              @confirm="handleDelete(token.id)"
            >
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>

        <div class="token-details">
          <div class="detail-row">
            <span class="detail-label">策略范围</span>
            <span class="detail-value">
              <el-tag size="small" :type="scopeTagType(token.scope_type)">
                {{ scopeLabel(token.scope_type) }}
              </el-tag>
              <span v-if="token.scope_type === 'listed'" class="scope-list">
                {{ token.scope_strategies.join(', ') }}
              </span>
            </span>
          </div>
          <div class="detail-row">
            <span class="detail-label">操作权限</span>
            <span class="detail-value">
              <el-tag v-for="p in token.permissions" :key="p" size="small" class="perm-tag">
                {{ permLabel(p) }}
              </el-tag>
            </span>
          </div>
          <div class="detail-row">
            <span class="detail-label">限速</span>
            <span class="detail-value">{{ token.rate_limit === 0 ? '不限' : `${token.rate_limit} 次/分钟` }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Create Dialog -->
    <el-dialog
      v-model="showCreateDialog"
      title="创建 API Token"
      width="560px"
      :close-on-click-modal="false"
      @closed="resetCreateForm"
    >
      <el-form :model="createForm" label-width="100px">
        <el-form-item label="名称">
          <el-input v-model="createForm.name" placeholder="例如: 我的Python脚本" maxlength="100" />
        </el-form-item>

        <el-form-item label="策略范围">
          <el-select v-model="createForm.scope_type" style="width: 100%">
            <el-option value="all" label="全部可访问策略" />
            <el-option value="owned" label="仅我创建的策略" />
            <el-option value="listed" label="指定策略" />
          </el-select>
        </el-form-item>

        <el-form-item v-if="createForm.scope_type === 'listed'" label="策略列表">
          <el-select
            v-model="createForm.scope_strategies"
            multiple
            filterable
            placeholder="选择策略"
            style="width: 100%"
          >
            <el-option
              v-for="s in myStrategies"
              :key="s.strategy_id"
              :label="`${s.name} (${s.strategy_id})`"
              :value="s.strategy_id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="操作权限">
          <el-checkbox-group v-model="createForm.permissions">
            <el-checkbox value="read">查看（策略/持仓/订单）</el-checkbox>
            <el-checkbox value="trade">交易（下单/撤单）</el-checkbox>
            <el-checkbox value="modify">管理（修改/删除策略）</el-checkbox>
          </el-checkbox-group>
        </el-form-item>

        <el-form-item label="有效期">
          <el-select v-model="createForm.expires_days" style="width: 100%">
            <el-option :value="null" label="永不过期" />
            <el-option :value="30" label="30 天" />
            <el-option :value="90" label="90 天" />
            <el-option :value="180" label="180 天" />
            <el-option :value="365" label="1 年" />
          </el-select>
        </el-form-item>

        <el-form-item label="限速">
          <el-input-number v-model="createForm.rate_limit" :min="0" :max="1000" :step="10" />
          <span class="form-hint">次/分钟，0 = 不限</span>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- Token Created Success Dialog -->
    <el-dialog
      v-model="showTokenResult"
      title="Token 创建成功"
      width="520px"
      :close-on-click-modal="false"
    >
      <el-alert type="warning" :closable="false" show-icon style="margin-bottom: 16px">
        <template #title>
          请立即复制并妥善保存此 Token，关闭后将无法再次查看！
        </template>
      </el-alert>

      <div class="token-result-box">
        <code class="token-value">{{ createdToken }}</code>
        <el-button size="small" @click="copyToken">
          <el-icon><DocumentCopy /></el-icon>
          复制
        </el-button>
      </div>

      <template #footer>
        <el-button type="primary" @click="showTokenResult = false">我已保存，关闭</el-button>
      </template>
    </el-dialog>

    <!-- Edit Dialog -->
    <el-dialog
      v-model="showEditDialog"
      title="编辑 API Token"
      width="560px"
      :close-on-click-modal="false"
    >
      <el-form v-if="editForm" :model="editForm" label-width="100px">
        <el-form-item label="名称">
          <el-input v-model="editForm.name" placeholder="Token 名称" maxlength="100" />
        </el-form-item>

        <el-form-item label="策略范围">
          <el-select v-model="editForm.scope_type" style="width: 100%">
            <el-option value="all" label="全部可访问策略" />
            <el-option value="owned" label="仅我创建的策略" />
            <el-option value="listed" label="指定策略" />
          </el-select>
        </el-form-item>

        <el-form-item v-if="editForm.scope_type === 'listed'" label="策略列表">
          <el-select
            v-model="editForm.scope_strategies"
            multiple
            filterable
            placeholder="选择策略"
            style="width: 100%"
          >
            <el-option
              v-for="s in myStrategies"
              :key="s.strategy_id"
              :label="`${s.name} (${s.strategy_id})`"
              :value="s.strategy_id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="操作权限">
          <el-checkbox-group v-model="editForm.permissions">
            <el-checkbox value="read">查看</el-checkbox>
            <el-checkbox value="trade">交易</el-checkbox>
            <el-checkbox value="modify">管理</el-checkbox>
          </el-checkbox-group>
        </el-form-item>

        <el-form-item label="限速">
          <el-input-number v-model="editForm.rate_limit" :min="0" :max="1000" :step="10" />
          <span class="form-hint">次/分钟，0 = 不限</span>
        </el-form-item>

        <el-form-item label="状态">
          <el-switch v-model="editForm.is_active" active-text="启用" inactive-text="禁用" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="updating" @click="handleUpdate">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { showApiError } from '@/utils/notify'
import { Plus, Key, Calendar, Clock, Timer, DocumentCopy } from '@element-plus/icons-vue'
import {
  listApiTokens,
  createApiToken,
  updateApiToken,
  deleteApiToken,
  type ApiToken,
  type CreateApiTokenRequest,
  type UpdateApiTokenRequest,
} from '@/api/apiTokens'
import { listStrategies } from '@/api/strategies'

// ── State ──
const loading = ref(false)
const creating = ref(false)
const updating = ref(false)
const tokens = ref<ApiToken[]>([])
const myStrategies = ref<{ strategy_id: string; name: string }[]>([])

const showCreateDialog = ref(false)
const showTokenResult = ref(false)
const showEditDialog = ref(false)
const createdToken = ref('')

const createForm = ref<CreateApiTokenRequest>({
  name: '',
  scope_type: 'all',
  scope_strategies: [],
  permissions: ['read', 'trade'],
  expires_days: null,
  rate_limit: 60,
})

const editForm = ref<(UpdateApiTokenRequest & { id: number; is_active: boolean }) | null>(null)

// ── Load ──
async function loadTokens() {
  loading.value = true
  try {
    const res = await listApiTokens()
    tokens.value = res.data
  } catch {
    ElMessage.error('加载 Token 列表失败')
  } finally {
    loading.value = false
  }
}

async function loadStrategies() {
  try {
    const res = await listStrategies()
    myStrategies.value = res.data.map((s: any) => ({
      strategy_id: s.strategy_id,
      name: s.name,
    }))
  } catch {
    // ignore
  }
}

onMounted(() => {
  loadTokens()
  loadStrategies()
})

// ── Create ──
async function handleCreate() {
  if (!createForm.value.permissions?.length) {
    ElMessage.warning('至少需要一个操作权限')
    return
  }
  if (createForm.value.scope_type === 'listed' && !createForm.value.scope_strategies?.length) {
    ElMessage.warning('指定策略模式下需要至少选择一个策略')
    return
  }

  creating.value = true
  try {
    const res = await createApiToken(createForm.value)
    createdToken.value = res.data.token
    showCreateDialog.value = false
    showTokenResult.value = true
    await loadTokens()
  } catch (err: any) {
    showApiError(err, '创建失败')
  } finally {
    creating.value = false
  }
}

function resetCreateForm() {
  createForm.value = {
    name: '',
    scope_type: 'all',
    scope_strategies: [],
    permissions: ['read', 'trade'],
    expires_days: null,
    rate_limit: 60,
  }
}

// ── Edit ──
function openEditDialog(token: ApiToken) {
  editForm.value = {
    id: token.id,
    name: token.name,
    scope_type: token.scope_type,
    scope_strategies: [...token.scope_strategies],
    permissions: [...token.permissions],
    rate_limit: token.rate_limit,
    is_active: token.is_active,
  }
  showEditDialog.value = true
}

async function handleUpdate() {
  if (!editForm.value) return
  if (!editForm.value.permissions?.length) {
    ElMessage.warning('至少需要一个操作权限')
    return
  }

  updating.value = true
  try {
    const { id, ...data } = editForm.value
    await updateApiToken(id, data)
    ElMessage.success('更新成功')
    showEditDialog.value = false
    await loadTokens()
  } catch (err: any) {
    showApiError(err, '更新失败')
  } finally {
    updating.value = false
  }
}

// ── Delete ──
async function handleDelete(id: number) {
  try {
    await deleteApiToken(id)
    ElMessage.success('Token 已删除')
    await loadTokens()
  } catch (err: any) {
    showApiError(err, '删除失败')
  }
}

// ── Copy ──
function copyToken() {
  navigator.clipboard.writeText(createdToken.value).then(() => {
    ElMessage.success('已复制到剪贴板')
  }).catch(() => {
    ElMessage.warning('复制失败，请手动选择复制')
  })
}

// ── Helpers ──
function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return d.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function scopeLabel(type: string): string {
  const map: Record<string, string> = { all: '全部策略', listed: '指定策略', owned: '仅我的策略' }
  return map[type] || type
}

function scopeTagType(type: string): '' | 'success' | 'warning' {
  const map: Record<string, '' | 'success' | 'warning'> = { all: '', listed: 'warning', owned: 'success' }
  return map[type] || ''
}

function permLabel(p: string): string {
  const map: Record<string, string> = { read: '查看', trade: '交易', modify: '管理' }
  return map[p] || p
}
</script>

<style scoped>
.api-tokens-page {
  padding: 24px;
  max-width: 960px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.page-title {
  font-size: 22px;
  font-weight: 600;
  margin: 0 0 4px;
}

.page-desc {
  color: rgba(255, 255, 255, 0.5);
  font-size: 13px;
  margin: 0;
}

.empty-state {
  padding: 60px 0;
}

/* Token Cards */
.token-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.token-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  padding: 16px 20px;
  transition: border-color 0.2s;
}

.token-card:hover {
  border-color: rgba(201, 165, 90, 0.3);
}

.token-card.inactive {
  opacity: 0.55;
}

.token-main {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.token-info {
  flex: 1;
}

.token-name {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 500;
  margin-bottom: 6px;
}

.token-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.4);
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.token-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.token-details {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.detail-row {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
}

.detail-label {
  color: rgba(255, 255, 255, 0.4);
  min-width: 70px;
  flex-shrink: 0;
}

.detail-value {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.perm-tag {
  margin-right: 2px;
}

.scope-list {
  color: rgba(255, 255, 255, 0.5);
  font-size: 12px;
  margin-left: 4px;
}

/* Token Result */
.token-result-box {
  display: flex;
  align-items: center;
  gap: 12px;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(201, 165, 90, 0.3);
  border-radius: 8px;
  padding: 12px 16px;
}

.token-value {
  flex: 1;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 14px;
  color: #c9a55a;
  word-break: break-all;
  line-height: 1.5;
}

.form-hint {
  margin-left: 8px;
  color: rgba(255, 255, 255, 0.4);
  font-size: 12px;
}
</style>
