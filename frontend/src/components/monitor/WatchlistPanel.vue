<template>
  <div class="watchlist-panel">
    <div class="watchlist-layout">
      <!-- 左侧：分组列表 -->
      <div class="groups-panel">
        <div class="panel-header">
          <h3>分组</h3>
          <el-button type="primary" :icon="Plus" size="small" circle @click="showCreateGroup" />
        </div>

        <div v-if="groupsLoading" class="panel-loading">
          <el-skeleton :rows="3" animated />
        </div>

        <div v-else class="groups-list">
          <div
            v-for="g in groups"
            :key="g.id"
            class="group-item"
            :class="{ active: selectedGroupId === g.id }"
            @click="selectGroup(g.id)"
          >
            <div class="group-info">
              <template v-if="editingGroupId === g.id">
                <el-input
                  v-model="editingGroupName"
                  size="small"
                  @keyup.enter="confirmRename(g.id)"
                  @blur="confirmRename(g.id)"
                  @click.stop
                />
              </template>
              <template v-else>
                <span class="group-name">{{ g.name }}</span>
                <span class="group-count">{{ g.stocks.length }} 只</span>
              </template>
            </div>
            <div v-if="editingGroupId !== g.id" class="group-actions" @click.stop>
              <el-button link :icon="Edit" size="small" @click="startRename(g)" />
              <el-popconfirm title="确定删除此分组？" @confirm="handleDeleteGroup(g.id)">
                <template #reference>
                  <el-button link :icon="Delete" size="small" type="danger" />
                </template>
              </el-popconfirm>
            </div>
          </div>

          <!-- 新建分组输入框 -->
          <div v-if="creatingGroup" class="group-item creating">
            <el-input
              v-model="newGroupName"
              size="small"
              placeholder="输入分组名称"
              @keyup.enter="confirmCreateGroup"
              @blur="cancelCreateGroup"
            />
          </div>

          <div v-if="!groupsLoading && groups.length === 0 && !creatingGroup" class="groups-empty">
            <p>暂无分组</p>
            <el-button type="primary" link @click="showCreateGroup">创建第一个分组</el-button>
          </div>
        </div>
      </div>

      <!-- 右侧：股票列表 -->
      <div class="stocks-panel">
        <template v-if="selectedGroup">
          <div class="panel-header">
            <h3>{{ selectedGroup.name }}</h3>
            <span class="stock-total">共 {{ selectedGroup.stocks.length }} 只</span>
          </div>

          <!-- 搜索添加区域 -->
          <div class="add-stock-area">
            <el-select
              v-model="selectedSearchStocks"
              multiple
              filterable
              remote
              reserve-keyword
              :remote-method="onStockSearch"
              :loading="stockSearchLoading"
              placeholder="搜索股票并添加到自选"
              class="stock-search-select"
            >
              <el-option
                v-for="s in stockSearchResults"
                :key="s.ts_code"
                :label="`${s.symbol} - ${s.name}`"
                :value="s.ts_code"
              >
                <div class="stock-option">
                  <span class="stock-code">{{ s.symbol }}</span>
                  <span class="stock-name">{{ s.name }}</span>
                  <span class="stock-industry">{{ s.industry }}</span>
                </div>
              </el-option>
            </el-select>
            <el-button
              type="primary"
              :disabled="selectedSearchStocks.length === 0"
              :loading="addStockLoading"
              @click="handleAddStocks"
            >
              添加
            </el-button>
          </div>

          <!-- 股票表格 -->
          <div v-if="selectedGroup.stocks.length === 0" class="stocks-empty">
            <el-empty description="暂无自选股票，请通过上方搜索添加" :image-size="80" />
          </div>

          <el-table
            v-else
            :data="selectedGroup.stocks"
            stripe
            size="small"
            class="stocks-table"
          >
            <el-table-column prop="symbol" label="代码" width="100" />
            <el-table-column prop="name" label="名称" width="120" />
            <el-table-column prop="ts_code" label="TS代码" />
            <el-table-column label="操作" width="80" fixed="right">
              <template #default="{ row }">
                <el-popconfirm title="确定移除此股票？" @confirm="handleRemoveStock(row.id)">
                  <template #reference>
                    <el-button link type="danger" size="small" :icon="Delete" />
                  </template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </template>

        <template v-else>
          <div class="no-group-selected">
            <el-empty description="请选择左侧分组查看股票" :image-size="80" />
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Edit, Delete } from '@element-plus/icons-vue'
import type { WatchlistGroup } from '@/types/watchlist'
import type { StockOption } from '@/types/monitor'
import {
  getWatchlistGroups,
  createGroup,
  renameGroup,
  deleteGroup,
  batchAddStocks,
  removeStock,
} from '@/api/watchlist'
import { searchStocks } from '@/api/monitor'

// ── 分组数据 ──
const groups = ref<WatchlistGroup[]>([])
const groupsLoading = ref(false)
const selectedGroupId = ref<number | null>(null)

const selectedGroup = computed(() =>
  groups.value.find(g => g.id === selectedGroupId.value) ?? null
)

async function loadGroups() {
  groupsLoading.value = true
  try {
    const { data } = await getWatchlistGroups()
    groups.value = data
    if (selectedGroupId.value && !groups.value.find(g => g.id === selectedGroupId.value)) {
      selectedGroupId.value = groups.value.length > 0 ? groups.value[0].id : null
    } else if (!selectedGroupId.value && groups.value.length > 0) {
      selectedGroupId.value = groups.value[0].id
    }
  } catch {
    ElMessage.error('加载自选股分组失败')
  } finally {
    groupsLoading.value = false
  }
}

function selectGroup(id: number) {
  selectedGroupId.value = id
}

// ── 创建分组 ──
const creatingGroup = ref(false)
const newGroupName = ref('')

function showCreateGroup() {
  creatingGroup.value = true
  newGroupName.value = ''
}

async function confirmCreateGroup() {
  const name = newGroupName.value.trim()
  if (!name) {
    cancelCreateGroup()
    return
  }
  try {
    const { data } = await createGroup(name)
    groups.value.push({ ...data, stocks: [] })
    selectedGroupId.value = data.id
    creatingGroup.value = false
    newGroupName.value = ''
    ElMessage.success('分组创建成功')
  } catch {
    ElMessage.error('创建分组失败')
  }
}

function cancelCreateGroup() {
  creatingGroup.value = false
  newGroupName.value = ''
}

// ── 重命名分组 ──
const editingGroupId = ref<number | null>(null)
const editingGroupName = ref('')

function startRename(g: WatchlistGroup) {
  editingGroupId.value = g.id
  editingGroupName.value = g.name
}

async function confirmRename(id: number) {
  const name = editingGroupName.value.trim()
  if (!name) {
    editingGroupId.value = null
    return
  }
  try {
    await renameGroup(id, name)
    const g = groups.value.find(g => g.id === id)
    if (g) g.name = name
    editingGroupId.value = null
    ElMessage.success('重命名成功')
  } catch {
    ElMessage.error('重命名失败')
  }
}

// ── 删除分组 ──
async function handleDeleteGroup(id: number) {
  try {
    await deleteGroup(id)
    groups.value = groups.value.filter(g => g.id !== id)
    if (selectedGroupId.value === id) {
      selectedGroupId.value = groups.value.length > 0 ? groups.value[0].id : null
    }
    ElMessage.success('分组已删除')
  } catch {
    ElMessage.error('删除分组失败')
  }
}

// ── 股票搜索 ──
const stockSearchResults = ref<StockOption[]>([])
const stockSearchLoading = ref(false)
const selectedSearchStocks = ref<string[]>([])

async function onStockSearch(query: string) {
  if (!query.trim()) {
    stockSearchResults.value = []
    return
  }
  stockSearchLoading.value = true
  try {
    const { data } = await searchStocks(query, 20)
    stockSearchResults.value = data
  } catch {
    stockSearchResults.value = []
  } finally {
    stockSearchLoading.value = false
  }
}

// ── 添加/移除股票 ──
const addStockLoading = ref(false)

async function handleAddStocks() {
  if (!selectedGroupId.value || selectedSearchStocks.value.length === 0) return
  addStockLoading.value = true
  try {
    const stocks = selectedSearchStocks.value.map(ts_code => {
      const found = stockSearchResults.value.find(s => s.ts_code === ts_code)
      return {
        ts_code: found?.ts_code ?? ts_code,
        symbol: found?.symbol ?? '',
        name: found?.name ?? '',
      }
    })

    const { data } = await batchAddStocks(selectedGroupId.value, stocks)
    let msg = `已添加 ${data.added} 只股票`
    if (data.skipped > 0) msg += `，跳过 ${data.skipped} 只重复`
    if (data.invalid && data.invalid.length > 0) msg += `，${data.invalid.length} 只代码无效`
    ElMessage.success(msg)

    await loadGroups()
    selectedSearchStocks.value = []
    stockSearchResults.value = []
  } catch {
    ElMessage.error('添加股票失败')
  } finally {
    addStockLoading.value = false
  }
}

async function handleRemoveStock(stockId: number) {
  try {
    await removeStock(stockId)
    const g = selectedGroup.value
    if (g) {
      g.stocks = g.stocks.filter(s => s.id !== stockId)
    }
    ElMessage.success('已移除')
  } catch {
    ElMessage.error('移除失败')
  }
}

// ── 初始化 ──
onMounted(() => {
  loadGroups()
})

// 暴露 refresh 方法供父组件调用
defineExpose({ refresh: loadGroups })
</script>

<style scoped>
.watchlist-panel {
  padding: 0;
}

/* ── 两栏布局 ── */
.watchlist-layout {
  display: flex;
  gap: 16px;
  min-height: 450px;
}

@media (max-width: 768px) {
  .watchlist-layout {
    flex-direction: column;
  }
}

/* ── 左侧分组面板 ── */
.groups-panel {
  width: 240px;
  flex-shrink: 0;
  background: var(--color-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

@media (max-width: 768px) {
  .groups-panel {
    width: 100%;
  }
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border-subtle);
}

.panel-header h3 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.stock-total {
  font-size: 12px;
  color: var(--text-muted);
  margin-left: 8px;
}

.panel-loading {
  padding: 16px;
}

.groups-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.group-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.15s;
  margin-bottom: 2px;
}

.group-item:hover {
  background: var(--color-hover);
}

.group-item.active {
  background: var(--color-accent-bg, rgba(201, 165, 90, 0.08));
  border: 1px solid var(--color-accent-border, rgba(201, 165, 90, 0.2));
}

.group-item.creating {
  cursor: default;
}

.group-info {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.group-name {
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.group-count {
  font-size: 11px;
  color: var(--text-muted);
  flex-shrink: 0;
}

.group-actions {
  display: flex;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.15s;
}

.group-item:hover .group-actions {
  opacity: 1;
}

.groups-empty {
  text-align: center;
  padding: 24px 16px;
  color: var(--text-muted);
  font-size: 13px;
}

/* ── 右侧股票面板 ── */
.stocks-panel {
  flex: 1;
  background: var(--color-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 0 0 16px;
}

.add-stock-area {
  display: flex;
  gap: 10px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-subtle);
  align-items: flex-start;
}

.stock-search-select {
  flex: 1;
}

.stock-option {
  display: flex;
  align-items: center;
  gap: 10px;
}

.stock-code {
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary);
  min-width: 60px;
}

.stock-name {
  font-size: 13px;
  color: var(--text-secondary);
  flex: 1;
}

.stock-industry {
  font-size: 11px;
  color: var(--text-muted);
  background: var(--color-hover);
  padding: 1px 6px;
  border-radius: 3px;
}

.stocks-empty,
.no-group-selected {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}

.stocks-table {
  margin-top: 8px;
}

:deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: var(--color-hover);
  --el-table-border-color: var(--border-subtle);
  --el-table-text-color: var(--text-primary);
  --el-table-header-text-color: var(--text-secondary);
}

:deep(.el-table .el-table__row:hover > td) {
  background: var(--color-hover) !important;
}
</style>
