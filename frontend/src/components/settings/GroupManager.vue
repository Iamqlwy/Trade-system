<template>
  <el-card shadow="never" class="group-manager-card">
    <template #header>
      <div class="card-header-row">
        <span class="card-title">用户组管理</span>
        <el-button type="primary" size="small" @click="showCreate = true">新建组</el-button>
      </div>
    </template>

    <el-table :data="groups" stripe size="small" border style="width: 100%" v-loading="loading">
      <el-table-column prop="name" label="组名" min-width="140" />
      <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
      <el-table-column label="成员数" width="80" align="center">
        <template #default="{ row }">
          <el-tag size="small" type="info">{{ row.member_count }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="120" align="center">
        <template #default="{ row }">
          <span class="time-cell">{{ formatTime(row.created_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="80" align="center">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="openDetail(row)">管理</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 创建组弹窗 -->
    <el-dialog v-model="showCreate" title="新建用户组" width="420px">
      <el-form :model="createForm" label-width="80px">
        <el-form-item label="组名">
          <el-input v-model="createForm.name" maxlength="100" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" :rows="2" maxlength="500" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="doCreate">确定</el-button>
      </template>
    </el-dialog>

    <!-- 组详情弹窗 -->
    <el-dialog v-model="showDetail" :title="`管理：${detail?.name || ''}`" width="700px">
      <template v-if="detail">
        <el-tabs v-model="detailTab">
          <!-- 基本信息 -->
          <el-tab-pane label="基本信息" name="info">
            <el-form label-width="80px">
              <el-form-item label="组名">
                <el-input v-model="editName" maxlength="100" />
              </el-form-item>
              <el-form-item label="描述">
                <el-input v-model="editDesc" type="textarea" :rows="2" maxlength="500" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" size="small" @click="doUpdate">保存</el-button>
                <el-button type="danger" size="small" plain @click="doDelete">删除组</el-button>
              </el-form-item>
            </el-form>
          </el-tab-pane>

          <!-- 成员管理 -->
          <el-tab-pane label="成员管理" name="members">
            <div class="tab-toolbar">
              <el-button type="primary" size="small" @click="showAddMembers = true">添加成员</el-button>
            </div>
            <el-table :data="detail.members" size="small" border>
              <el-table-column prop="username" label="用户名" />
              <el-table-column prop="role" label="角色" width="80" align="center">
                <template #default="{ row }">
                  <span class="role-tag" :class="row.role === 'admin' ? 'role-admin' : 'role-viewer'">
                    {{ row.role === 'admin' ? '管理员' : row.role === 'trader' ? '交易员' : '查看者' }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="80" align="center">
                <template #default="{ row }">
                  <el-button type="danger" link size="small" @click="removeMember(row.user_id)">移除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <!-- 功能权限 -->
          <el-tab-pane label="功能权限" name="perms">
            <el-form label-width="120px" v-if="detail.permissions">
              <el-form-item label="Agent">
                <el-switch v-model="detail.permissions.can_use_agent" />
              </el-form-item>
              <el-form-item label="实盘交易">
                <el-switch v-model="detail.permissions.can_create_real" />
              </el-form-item>
              <el-form-item label="策略上限">
                <el-input-number v-model="detail.permissions.max_strategies" :min="-1" :max="9999" size="small" />
              </el-form-item>
              <el-form-item label="定时任务">
                <el-switch v-model="detail.permissions.can_use_cron" />
              </el-form-item>
              <el-form-item label="监控">
                <el-switch v-model="detail.permissions.can_use_monitor" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" size="small" @click="savePermissions">保存权限</el-button>
              </el-form-item>
            </el-form>
          </el-tab-pane>

          <!-- 策略权限 -->
          <el-tab-pane label="策略权限" name="sp">
            <div class="tab-toolbar">
              <el-button type="primary" size="small" @click="showAddSp = true">添加策略</el-button>
            </div>
            <el-table :data="detail.strategy_permissions" size="small" border>
              <el-table-column prop="strategy_name" label="策略名" />
              <el-table-column label="可交易" width="80" align="center">
                <template #default="{ row }">
                  <span class="perm-tag" :class="row.can_trade ? 'perm-yes' : 'perm-no'">
                    {{ row.can_trade ? '是' : '否' }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="80" align="center">
                <template #default="{ row }">
                  <el-button
                    type="danger" link size="small"
                    @click="removeSp(row.strategy_id)"
                  >移除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <!-- 工具权限 -->
          <el-tab-pane label="工具权限" name="tp">
            <el-table :data="toolItems" size="small" border>
              <el-table-column label="工具" width="120">
                <template #default="{ row }">
                  {{ toolLabels[row.tool_key] || row.tool_key }}
                </template>
              </el-table-column>
              <el-table-column label="启用" width="80" align="center">
                <template #default="{ row }">
                  <el-switch
                    :model-value="row.enabled"
                    size="small"
                    @change="(val: boolean) => toggleTool(row.tool_key, val)"
                  />
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </template>
    </el-dialog>

    <!-- 添加成员弹窗 -->
    <el-dialog v-model="showAddMembers" title="添加成员" width="400px">
      <el-select
        v-model="selectedUserIds"
        multiple
        filterable
        placeholder="选择用户"
        style="width: 100%"
      >
        <el-option
          v-for="u in availableUsers"
          :key="u.id"
          :label="`${u.username} (${u.role === 'admin' ? '管理员' : u.role === 'trader' ? '交易员' : '查看者'})`"
          :value="u.id"
        />
      </el-select>
      <template #footer>
        <el-button @click="showAddMembers = false">取消</el-button>
        <el-button type="primary" @click="doAddMembers" :disabled="selectedUserIds.length === 0">添加</el-button>
      </template>
    </el-dialog>

    <!-- 添加策略权限弹窗 -->
    <el-dialog v-model="showAddSp" title="添加策略权限" width="400px">
      <el-select v-model="addSpId" filterable placeholder="选择策略" style="width: 100%">
        <el-option
          v-for="s in strategies"
          :key="s.strategy_id"
          :label="s.name"
          :value="s.strategy_id"
        />
      </el-select>
      <div style="margin-top: 12px">
        <el-checkbox v-model="addSpTrade">允许交易</el-checkbox>
      </div>
      <template #footer>
        <el-button @click="showAddSp = false">取消</el-button>
        <el-button type="primary" @click="doAddSp" :disabled="!addSpId">添加</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { showApiError } from '@/utils/notify'
import { useStrategiesStore } from '@/stores/strategies'
import api from '@/api'
import * as groupApi from '@/api/groups'
import type { UserGroup, GroupDetail } from '@/types/group'

const strategiesStore = useStrategiesStore()
const strategies = computed(() => strategiesStore.strategies)

// 工具标签
const toolLabels: Record<string, string> = {
  shell: 'Shell',
  file_read: '文件读',
  file_write: '文件写',
  file_search: '文件搜索',
  web_search: 'Web搜索',
  web_fetch: 'Web抓取',
  cronjob: '定时任务',
  agent: '子Agent',
  strategy_view: '策略持仓',
}

// 组列表
const groups = ref<UserGroup[]>([])
const loading = ref(false)
const showCreate = ref(false)
const createForm = reactive({ name: '', description: '' })

// 组详情
const showDetail = ref(false)
const detail = ref<GroupDetail | null>(null)
const detailTab = ref('info')
const editName = ref('')
const editDesc = ref('')

// 成员管理
const showAddMembers = ref(false)
const selectedUserIds = ref<number[]>([])
const availableUsers = ref<{ id: number; username: string; role: string }[]>([])

// 策略权限
const showAddSp = ref(false)
const addSpId = ref('')
const addSpTrade = ref(false)

// 工具权限
const toolItems = computed(() => {
  if (!detail.value) return []
  const permMap: Record<string, boolean> = {}
  for (const p of detail.value.tool_permissions) {
    permMap[p.tool_key] = p.enabled
  }
  return Object.keys(toolLabels).map(key => ({
    tool_key: key,
    enabled: permMap[key] ?? true,
  }))
})

async function loadGroups() {
  loading.value = true
  try {
    const res = await groupApi.getGroups()
    groups.value = res.data
  } catch { /* ignore */ }
  finally { loading.value = false }
}

async function doCreate() {
  try {
    await groupApi.createGroup({ name: createForm.name, description: createForm.description })
    ElMessage.success('组已创建')
    showCreate.value = false
    createForm.name = ''
    createForm.description = ''
    loadGroups()
  } catch (err) {
    showApiError(err, '创建失败')
  }
}

async function openDetail(row: UserGroup) {
  try {
    const res = await groupApi.getGroupDetail(row.id)
    detail.value = res.data
    editName.value = res.data.name
    editDesc.value = res.data.description
    detailTab.value = 'info'
    showDetail.value = true
  } catch (err) {
    showApiError(err, '获取组详情失败')
  }
}

async function doUpdate() {
  if (!detail.value) return
  try {
    await groupApi.updateGroup(detail.value.id, {
      name: editName.value,
      description: editDesc.value,
    })
    detail.value.name = editName.value
    detail.value.description = editDesc.value
    ElMessage.success('已更新')
    loadGroups()
  } catch (err) {
    showApiError(err, '更新失败')
  }
}

async function doDelete() {
  if (!detail.value) return
  try {
    await ElMessageBox.confirm('确认删除该用户组？此操作不可恢复。', '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await groupApi.deleteGroup(detail.value.id)
    ElMessage.success('组已删除')
    showDetail.value = false
    detail.value = null
    loadGroups()
  } catch { /* cancelled */ }
}

async function loadAvailableUsers() {
  try {
    const res = await api.get('/settings/users')
    availableUsers.value = res.data
  } catch { /* ignore */ }
}

async function doAddMembers() {
  if (!detail.value) return
  try {
    await groupApi.addGroupMembers(detail.value.id, selectedUserIds.value)
    ElMessage.success('成员已添加')
    // 刷新详情
    const res = await groupApi.getGroupDetail(detail.value.id)
    detail.value = res.data
    showAddMembers.value = false
    selectedUserIds.value = []
    loadGroups()
  } catch (err) {
    showApiError(err, '添加失败')
  }
}

async function removeMember(userId: number) {
  if (!detail.value) return
  try {
    await groupApi.removeGroupMember(detail.value.id, userId)
    detail.value.members = detail.value.members.filter(m => m.user_id !== userId)
    ElMessage.success('成员已移除')
    loadGroups()
  } catch (err) {
    showApiError(err, '移除失败')
  }
}

async function savePermissions() {
  if (!detail.value || !detail.value.permissions) return
  try {
    await groupApi.setGroupPermissions(detail.value.id, detail.value.permissions)
    ElMessage.success('权限已保存')
  } catch (err) {
    showApiError(err, '保存失败')
  }
}

async function doAddSp() {
  if (!detail.value) return
  try {
    await groupApi.setGroupStrategyPermission(detail.value.id, {
      strategy_id: addSpId.value,
      can_trade: addSpTrade.value,
    })
    const res = await groupApi.getGroupDetail(detail.value.id)
    detail.value = res.data
    showAddSp.value = false
    addSpId.value = ''
    addSpTrade.value = false
    ElMessage.success('策略权限已添加')
  } catch (err) {
    showApiError(err, '添加失败')
  }
}

async function removeSp(strategyId: string) {
  if (!detail.value) return
  try {
    await groupApi.deleteGroupStrategyPermission(detail.value.id, strategyId)
    detail.value.strategy_permissions = detail.value.strategy_permissions.filter(
      s => s.strategy_id !== strategyId
    )
    ElMessage.success('策略权限已移除')
  } catch (err) {
    showApiError(err, '移除失败')
  }
}

async function toggleTool(toolKey: string, enabled: boolean) {
  if (!detail.value) return
  try {
    await groupApi.setGroupToolPermission(detail.value.id, { tool_key: toolKey, enabled })
    // 更新本地
    const idx = detail.value.tool_permissions.findIndex(p => p.tool_key === toolKey)
    const permission = detail.value.tool_permissions[idx]
    if (permission) {
      permission.enabled = enabled
    } else {
      detail.value.tool_permissions.push({ tool_key: toolKey, enabled })
    }
    ElMessage.success(`${enabled ? '已启用' : '已禁用'} ${toolLabels[toolKey] || toolKey}`)
  } catch (err) {
    showApiError(err, '操作失败')
  }
}

function formatTime(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}

onMounted(() => {
  strategiesStore.fetchStrategies()
  loadGroups()
  loadAvailableUsers()
})
</script>

<style scoped>
.group-manager-card {
  margin-top: 20px;
}

.card-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-family: var(--font-display);
  font-weight: 600;
  font-size: 15px;
}

.tab-toolbar {
  margin-bottom: 10px;
}

.time-cell {
  font-size: 12px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

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
</style>
