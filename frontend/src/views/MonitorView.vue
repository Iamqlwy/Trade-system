<template>
  <div class="monitor-page">
    <!-- 无权限提示 -->
    <div v-if="!authStore.canUseMonitor" class="no-permission-wrapper">
      <el-empty description="您没有监控任务权限，请联系管理员开通">
        <template #image>
          <el-icon :size="80" color="#909399"><Lock /></el-icon>
        </template>
      </el-empty>
    </div>
    <template v-else>
    <!-- Hero Header -->
    <div class="monitor-hero">
      <div class="hero-text">
        <h1 class="hero-title">监控中心</h1>
        <p class="hero-subtitle">自定义监控脚本管理 · 自选股 · 实时触发告警</p>
      </div>
      <div class="hero-actions">
        <div class="ws-indicator" :class="{ connected: wsConnected }">
          <span class="ws-dot" />
          <span class="ws-label">{{ wsConnected ? '实时推送' : '未连接' }}</span>
        </div>
        <el-button class="hero-agent-btn" @click="goToAgent">
          <el-icon><ChatDotRound /></el-icon>
          AI 助手
        </el-button>
        <el-button :icon="Refresh" circle class="hero-refresh" @click="refreshAll" />
      </div>
    </div>

    <!-- Tabs -->
    <el-tabs v-model="activeTab" class="monitor-tabs">
      <el-tab-pane label="监控列表" name="monitors">

    <!-- Stats -->
    <div class="stat-grid stagger-children">
      <StatCard
        label="监控总数"
        :value="monitors.length"
        :icon="Monitor"
        icon-color="#b08d47"
        suffix="个脚本"
      />
      <StatCard
        label="运行中"
        :value="activeCount"
        :icon="VideoPlay"
        icon-color="#16a34a"
        suffix="个活跃"
      />
      <StatCard
        label="今日触发"
        :value="todayAlertCount"
        :icon="WarningFilled"
        icon-color="#dc2626"
        suffix="次告警"
      />
      <StatCard
        label="已暂停"
        :value="monitors.length - activeCount"
        :icon="VideoPause"
        icon-color="#d97706"
        suffix="个停止"
      />
    </div>

    <!-- Monitor List -->
    <div class="section-header">
      <div>
        <h2>监控列表</h2>
        <span class="section-hint">在 AI 助手中描述监控条件即可自动创建脚本</span>
      </div>
    </div>

    <div v-if="loading" class="loading-state">
      <el-skeleton :rows="3" animated />
    </div>

    <div v-else-if="monitors.length === 0" class="empty-state">
      <div class="empty-icon">
        <el-icon :size="48"><Bell /></el-icon>
      </div>
      <p class="empty-title">暂无监控脚本</p>
      <p class="empty-desc">前往 AI 助手，用自然语言描述你的监控需求</p>
      <el-button type="primary" @click="goToAgent">
        <el-icon><ChatDotRound /></el-icon>
        前往 AI 助手
      </el-button>
    </div>

    <div v-else class="monitor-grid stagger-children">
      <div
        v-for="m in monitors"
        :key="m.monitor_id"
        class="monitor-card"
        :class="{ 'is-disabled': !m.enabled, 'has-error': !!m.error_message }"
      >
        <!-- Card Header -->
        <div class="mc-header">
          <div class="mc-header-left">
            <div class="mc-status-dot" :class="getStatusClass(m)" />
            <h3 class="mc-name">{{ m.monitor_name || m.monitor_id }}</h3>
          </div>
          <div class="mc-header-right">
            <el-tag size="small" :type="m.trigger_mode === 'periodic' ? '' : 'warning'" effect="plain" round>
              {{ m.interval }}
            </el-tag>
          </div>
        </div>

        <!-- Description -->
        <p class="mc-desc">{{ m.description }}</p>

        <!-- Script Params (display as chips) -->
        <div v-if="m.script_metadata?.parameters?.length" class="mc-params">
          <span
            v-for="pdef in m.script_metadata.parameters"
            :key="pdef.name"
            class="param-chip"
          >
            {{ pdef.label || pdef.name }}: {{ m.params?.[pdef.name] ?? pdef.default }}
          </span>
        </div>

        <!-- Stock Sources -->
        <div v-if="m.script_metadata?.has_stock_param === true" class="mc-stocks">
          <span v-for="code in m.stock_codes" :key="code" class="stock-chip">{{ code }}</span>
          <span v-for="sid in (m.strategy_ids || [])" :key="'str-'+sid" class="stock-chip strategy-chip">{{ sid }}</span>
        </div>

        <!-- Last Result -->
        <div class="mc-result" v-if="m.last_result || m.error_message">
          <template v-if="m.error_message">
            <el-icon color="var(--color-danger)" :size="14"><CircleCloseFilled /></el-icon>
            <span class="mc-error">{{ m.error_message }}</span>
          </template>
          <template v-else-if="m.last_result">
            <el-icon :color="m.last_result.triggered ? 'var(--color-up)' : 'var(--color-down)'" :size="14">
              <component :is="m.last_result.triggered ? WarningFilled : CircleCheckFilled" />
            </el-icon>
            <span :class="m.last_result.triggered ? 'mc-triggered' : 'mc-normal'">
              <span class="mc-time">{{ m.last_result.time }}</span>
              {{ m.last_result.message }}
            </span>
          </template>
        </div>

        <!-- Card Footer -->
        <div class="mc-footer">
          <div class="mc-footer-left">
            <span class="mc-id">{{ m.monitor_id }}</span>
          </div>
          <div class="mc-footer-right">
            <el-tooltip :content="m.enabled ? '暂停' : '启用'" placement="top">
              <button class="mc-btn" :class="m.enabled ? 'btn-warn' : 'btn-ok'" @click.stop="handleToggle(m)">
                <el-icon :size="15"><component :is="m.enabled ? VideoPause : VideoPlay" /></el-icon>
              </button>
            </el-tooltip>
            <el-tooltip content="手动执行" placement="top">
              <button class="mc-btn btn-primary" @click.stop="handleRun(m)" :disabled="running[m.monitor_id]">
                <el-icon :size="15"><CaretRight /></el-icon>
              </button>
            </el-tooltip>
            <el-tooltip content="查看脚本" placement="top">
              <button class="mc-btn" @click.stop="openScript(m)">
                <el-icon :size="15"><Document /></el-icon>
              </button>
            </el-tooltip>
            <el-tooltip content="编辑" placement="top">
              <button class="mc-btn" @click.stop="openEdit(m)">
                <el-icon :size="15"><Edit /></el-icon>
              </button>
            </el-tooltip>
            <el-tooltip content="删除" placement="top">
              <button class="mc-btn btn-danger" @click.stop="handleDelete(m)">
                <el-icon :size="15"><Delete /></el-icon>
              </button>
            </el-tooltip>
          </div>
        </div>
      </div>
    </div>

    <!-- Trigger Logs -->
    <div class="section-header" style="margin-top: 32px">
      <div>
        <h2>触发记录</h2>
        <span class="section-hint">今日监控告警历史</span>
      </div>
      <div class="section-actions">
        <el-date-picker
          v-model="logDate"
          type="date"
          placeholder="选择日期"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          size="small"
          style="width: 140px"
          @change="loadLogs"
        />
      </div>
    </div>

    <el-card shadow="never" class="logs-card">
      <el-table :data="logs" v-loading="logsLoading" stripe size="small" max-height="360"
        border style="width: 100%"
        empty-text="暂无记录"
        :row-class-name="({ row }) => row.triggered ? '' : 'log-row-error'"
        :header-cell-style="{ background: 'var(--color-bg)', fontWeight: 600, fontSize: '12px', color: 'var(--text-secondary)' }"
      >
        <el-table-column label="时间" width="84">
          <template #default="{ row }">
            <span class="log-time">{{ formatTime(row.timestamp) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="64" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.triggered" size="small" type="danger" effect="light" round>触发</el-tag>
            <el-tag v-else size="small" type="warning" effect="light" round>错误</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="monitor_name" label="监控" min-width="130" show-overflow-tooltip />
        <el-table-column prop="stock_code" label="股票" width="100">
          <template #default="{ row }">
            <span v-if="row.stock_code" class="stock-chip sm">{{ row.stock_code }}</span>
            <span v-else class="log-dash">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="stock_name" label="名称" width="90" show-overflow-tooltip />
        <el-table-column prop="message" label="消息" min-width="280" show-overflow-tooltip>
          <template #default="{ row }">
            <span :class="row.triggered ? 'log-msg' : 'log-msg-error'">{{ row.message }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Live Alerts -->
    <div v-if="liveAlerts.length > 0" class="live-section">
      <div class="section-header">
        <div>
          <h2>实时告警</h2>
          <span class="section-hint">{{ liveAlerts.length }} 条新告警</span>
        </div>
        <el-button size="small" text @click="clearAlerts">清空</el-button>
      </div>
      <div class="live-list stagger-children">
        <div v-for="(alert, i) in liveAlerts.slice(0, 15)" :key="i" class="live-item">
          <div class="live-pulse" />
          <span class="live-time">{{ formatTime(alert.timestamp) }}</span>
          <span class="live-stock">{{ alert.stock_code }}</span>
          <span class="live-msg">{{ alert.message }}</span>
        </div>
      </div>
    </div>

      </el-tab-pane>
      <el-tab-pane label="自选股" name="watchlist">
        <WatchlistPanel ref="watchlistPanelRef" />
      </el-tab-pane>
    </el-tabs>

    <!-- Script Drawer -->
    <el-drawer v-model="drawerVisible" :title="drawerTitle" size="520px" direction="rtl">
      <div class="script-drawer-content">
        <div class="script-meta" v-if="drawerMeta">
          <span class="stock-chip sm" v-for="code in drawerMeta.stock_codes" :key="code">{{ code }}</span>
          <el-tag size="small" effect="plain" round>{{ drawerMeta.interval }}</el-tag>
          <el-tag size="small" :type="drawerMeta.enabled ? 'success' : 'danger'" effect="light">
            {{ drawerMeta.enabled ? '运行中' : '已停止' }}
          </el-tag>
        </div>
        <pre class="script-code"><code>{{ scriptContent }}</code></pre>
      </div>
    </el-drawer>

    <!-- Edit Dialog -->
    <el-dialog v-model="editVisible" title="编辑监控" width="600px" :close-on-click-modal="false" destroy-on-close>
      <el-form :model="editForm" label-width="100px" label-position="left" class="edit-form">
        <el-form-item label="名称">
          <el-input v-model="editForm.monitor_name" placeholder="监控名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editForm.description" type="textarea" :rows="2" placeholder="监控条件描述" />
        </el-form-item>

        <!-- 动态脚本参数 -->
        <template v-if="editForm.script_metadata?.parameters?.length">
          <el-divider content-position="left">脚本参数</el-divider>

          <el-form-item
            v-for="pdef in editForm.script_metadata.parameters"
            :key="pdef.name"
            :label="pdef.label || pdef.name"
          >
            <el-input
              v-if="pdef.type === 'string'"
              v-model="(editForm.params as any)[pdef.name]"
              :placeholder="pdef.description"
              style="width: 100%"
            />
            <el-input-number
              v-else-if="pdef.type === 'int'"
              v-model="(editForm.params as any)[pdef.name]"
              :min="pdef.min ?? 0"
              :max="pdef.max ?? 999999"
              controls-position="right"
              style="width: 160px"
            />
            <el-input-number
              v-else-if="pdef.type === 'float'"
              v-model="(editForm.params as any)[pdef.name]"
              :min="pdef.min ?? 0"
              :max="pdef.max ?? 999999"
              :step="0.01"
              controls-position="right"
              style="width: 160px"
            />
            <el-switch
              v-else-if="pdef.type === 'bool'"
              v-model="(editForm.params as any)[pdef.name]"
              active-text="是"
              inactive-text="否"
            />
            <el-select
              v-else-if="pdef.type === 'choice'"
              v-model="(editForm.params as any)[pdef.name]"
              style="width: 100%"
            >
              <el-option
                v-for="c in pdef.choices"
                :key="c.value"
                :label="c.label"
                :value="c.value"
              />
            </el-select>
            <span v-if="pdef.description" class="edit-hint" style="margin-left: 8px">
              {{ pdef.description }}
            </span>
          </el-form-item>
        </template>

        <!-- 股票选择：仅 has_stock_param=true 时显示 -->
        <template v-if="editForm.script_metadata?.has_stock_param === true">
        <el-divider content-position="left">股票来源</el-divider>

        <el-form-item label="股票">
          <el-select
            v-model="editForm.stock_codes"
            multiple
            filterable
            remote
            reserve-keyword
            :remote-method="onStockSearch"
            :loading="stockSearchLoading"
            placeholder="输入中文名、代码或拼音搜索"
            style="width: 100%"
          >
            <el-option
              v-for="s in stockSearchResults"
              :key="s.ts_code"
              :label="`${s.name} ${s.ts_code} (${s.industry})`"
              :value="s.ts_code"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="从自选股添加">
          <div style="display: flex; align-items: center; gap: 8px; width: 100%">
            <el-select
              v-model="selectedWatchlistGroupId"
              placeholder="选择自选股分组"
              style="flex: 1"
              :loading="watchlistLoading"
            >
              <el-option
                v-for="g in watchlistGroups"
                :key="g.id"
                :label="`${g.name} (${g.stocks.length}只)`"
                :value="g.id"
              />
            </el-select>
            <el-button
              type="primary"
              plain
              :disabled="!selectedWatchlistGroupId"
              :loading="watchlistAdding"
              @click="addFromWatchlist"
            >
              批量添加
            </el-button>
          </div>
        </el-form-item>
        <el-form-item label="策略持仓">
          <el-select
            v-model="editForm.strategy_ids"
            multiple
            placeholder="选择策略（动态获取持仓股票）"
            style="width: 100%"
          >
            <el-option
              v-for="s in strategyOptions"
              :key="s.strategy_id"
              :label="`${s.name} (${s.position_count}只持仓)`"
              :value="s.strategy_id"
            />
          </el-select>
        </el-form-item>
        </template>

        <el-divider content-position="left">调度配置</el-divider>

        <el-form-item label="执行间隔">
          <el-select v-model="editForm.interval" style="width: 100%">
            <el-option label="10 秒" value="10s" />
            <el-option label="30 秒" value="30s" />
            <el-option label="1 分钟" value="1m" />
            <el-option label="5 分钟" value="5m" />
            <el-option label="10 分钟" value="10m" />
            <el-option label="15 分钟" value="15m" />
            <el-option label="30 分钟" value="30m" />
            <el-option label="1 小时" value="1h" />
          </el-select>
        </el-form-item>
        <el-form-item label="防重复触发">
          <div style="display: flex; align-items: center; gap: 8px">
            <el-input-number v-model="editForm.cooldown_seconds" :min="0" :step="60" :max="86400" controls-position="right" style="width: 160px" />
            <span class="edit-hint">秒（同股票触发后冷却）</span>
          </div>
        </el-form-item>
        <el-form-item label="触发模式">
          <el-radio-group v-model="editForm.trigger_mode">
            <el-radio value="periodic">周期执行</el-radio>
            <el-radio value="manual">仅手动</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="editForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" @click="submitEdit" :loading="editSaving">保存</el-button>
      </template>
    </el-dialog>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import {
  Refresh, VideoPause, VideoPlay, CaretRight, Bell, ChatDotRound,
  WarningFilled, Monitor, Document, CircleCheckFilled, CircleCloseFilled,
  Edit, Delete, Lock,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { showApiError } from '@/utils/notify'
import StatCard from '@/components/common/StatCard.vue'
import WatchlistPanel from '@/components/monitor/WatchlistPanel.vue'
import * as monitorApi from '@/api/monitor'
import { getWatchlistGroups } from '@/api/watchlist'
import { useMonitorAlerts } from '@/composables/useMonitorAlerts'
import { useAuthStore } from '@/stores/auth'
import type { MonitorInfo, MonitorAlert, ScriptMetadata } from '@/types/monitor'
import type { WatchlistGroup } from '@/types/watchlist'

const router = useRouter()
const authStore = useAuthStore()
const { alerts: liveAlerts, connected: wsConnected, connect: connectWs, clearAlerts } = useMonitorAlerts()

const monitors = ref<MonitorInfo[]>([])
const loading = ref(false)
const activeTab = ref('monitors')
const watchlistPanelRef = ref<InstanceType<typeof WatchlistPanel> | null>(null)
const logs = ref<MonitorAlert[]>([])
const logsLoading = ref(false)
const logDate = ref(new Date().toISOString().slice(0, 10))
const running = reactive<Record<string, boolean>>({})

// Drawer state
const drawerVisible = ref(false)
const drawerTitle = ref('')
const drawerMeta = ref<MonitorInfo | null>(null)
const scriptContent = ref('')

// Edit dialog state
const editVisible = ref(false)
const editSaving = ref(false)
const editMonitorId = ref('')
const editForm = reactive<{
  monitor_name: string
  description: string
  stock_codes: string[]
  strategy_ids: string[]
  interval: string
  trigger_mode: string
  enabled: boolean
  cooldown_seconds: number
  script_metadata: ScriptMetadata | null
  params: Record<string, unknown>
}>({
  monitor_name: '',
  description: '',
  stock_codes: [],
  strategy_ids: [],
  interval: '30s',
  trigger_mode: 'periodic',
  enabled: true,
  cooldown_seconds: 300,
  script_metadata: null,
  params: {},
})

// 股票搜索
const stockSearchResults = ref<{ ts_code: string; symbol: string; name: string; cnspell: string; industry: string }[]>([])
const stockSearchLoading = ref(false)

let stockSearchTimer: ReturnType<typeof setTimeout> | null = null
async function onStockSearch(query: string) {
  if (stockSearchTimer) clearTimeout(stockSearchTimer)
  if (!query) {
    stockSearchResults.value = []
    return
  }
  stockSearchTimer = setTimeout(async () => {
    stockSearchLoading.value = true
    try {
      const res = await monitorApi.searchStocks(query, 30)
      stockSearchResults.value = res.data
    } catch {
      stockSearchResults.value = []
    } finally {
      stockSearchLoading.value = false
    }
  }, 250)
}

// 策略选项
const strategyOptions = ref<{ strategy_id: string; name: string; position_count: number; position_codes: string[] }[]>([])

// 自选股
const watchlistGroups = ref<WatchlistGroup[]>([])
const watchlistLoading = ref(false)
const watchlistAdding = ref(false)
const selectedWatchlistGroupId = ref<number | null>(null)

async function loadWatchlistGroups() {
  watchlistLoading.value = true
  try {
    const { data } = await getWatchlistGroups()
    watchlistGroups.value = data
  } catch {
    watchlistGroups.value = []
  } finally {
    watchlistLoading.value = false
  }
}

function addFromWatchlist() {
  if (!selectedWatchlistGroupId.value) return
  const group = watchlistGroups.value.find(g => g.id === selectedWatchlistGroupId.value)
  if (!group || group.stocks.length === 0) {
    ElMessage.warning('该分组中没有股票')
    return
  }
  const existingSet = new Set(editForm.stock_codes)
  let addedCount = 0
  for (const stock of group.stocks) {
    if (!existingSet.has(stock.ts_code)) {
      editForm.stock_codes.push(stock.ts_code)
      existingSet.add(stock.ts_code)
      addedCount++
    }
  }
  ElMessage.success(`已从「${group.name}」添加 ${addedCount} 只股票${addedCount < group.stocks.length ? `，跳过 ${group.stocks.length - addedCount} 只重复` : ''}`)
}

const activeCount = computed(() => monitors.value.filter(m => m.enabled).length)
const todayAlertCount = computed(() => logs.value.length)

function goToAgent() {
  const msg = '使用 stock-monitor 创建一个监控器，'
  console.log('[MonitorView][goToAgent] router.push → /agent?initialMessage=%s', msg)
  router.push({ path: '/agent', query: { initialMessage: msg } })
}

async function loadMonitors() {
  loading.value = true
  try {
    const res = await monitorApi.listMonitors()
    monitors.value = res.data
  } catch (err) {
    showApiError(err, '加载监控列表失败')
  } finally {
    loading.value = false
  }
}

async function loadLogs() {
  logsLoading.value = true
  try {
    const res = await monitorApi.getMonitorLogs({ date: logDate.value, limit: 200 })
    logs.value = res.data
    // 批量解析股票名称
    resolveStockNames(logs.value)
  } catch (err) {
    showApiError(err, '加载触发记录失败')
  } finally {
    logsLoading.value = false
  }
}

const nameCache = new Map<string, string>()

async function resolveStockNames(items: MonitorAlert[]) {
  const codes = [...new Set(items.map(i => i.stock_code).filter(Boolean))]
  if (!codes.length) return

  // 先用缓存填充
  for (const item of items) {
    if (item.stock_code && nameCache.has(item.stock_code)) {
      item.stock_name = nameCache.get(item.stock_code)
    }
  }

  // 查未缓存的
  const uncached = codes.filter(c => !nameCache.has(c))
  if (!uncached.length) return

  try {
    const results = await Promise.all(uncached.map(code => monitorApi.searchStocks(code, 1)))
    for (const res of results) {
      const match = res.data[0]
      if (match) {
        nameCache.set(match.ts_code, match.name)
      }
    }
    // 回填名称
    for (const item of items) {
      if (item.stock_code && nameCache.has(item.stock_code)) {
        item.stock_name = nameCache.get(item.stock_code)
      }
    }
  } catch {
    // 不影响主流程
  }
}

function refreshAll() {
  loadMonitors()
  loadLogs()
}

async function handleToggle(row: MonitorInfo) {
  try {
    const res = await monitorApi.toggleMonitor(row.monitor_id)
    row.enabled = res.data.enabled
    ElMessage.success(res.data.enabled ? '已启用' : '已暂停')
  } catch (err) {
    showApiError(err, '操作失败')
  }
}

async function handleRun(row: MonitorInfo) {
  running[row.monitor_id] = true
  try {
    const res = await monitorApi.runMonitor(row.monitor_id)
    const triggered = res.data.results.some(r =>
      r.result && Array.isArray(r.result) ? r.result.some(item => item.triggered) : false
    )
    ElMessage[triggered ? 'warning' : 'success'](
      triggered ? '执行完成，有告警触发' : '执行完成，未触发',
    )
    await loadMonitors()
  } catch (err) {
    showApiError(err, '执行失败')
  } finally {
    running[row.monitor_id] = false
  }
}

async function openScript(m: MonitorInfo) {
  drawerTitle.value = m.monitor_name || m.monitor_id
  drawerMeta.value = m
  scriptContent.value = '加载中...'
  drawerVisible.value = true
  try {
    const res = await monitorApi.getMonitor(m.monitor_id)
    scriptContent.value = res.data.script_content || '// 脚本为空'
  } catch {
    scriptContent.value = '// 加载失败'
  }
}

async function openEdit(m: MonitorInfo) {
  editMonitorId.value = m.monitor_id
  editForm.monitor_name = m.monitor_name
  editForm.description = m.description
  editForm.stock_codes = [...m.stock_codes]
  editForm.strategy_ids = [...(m.strategy_ids || [])]
  editForm.interval = m.interval
  editForm.trigger_mode = m.trigger_mode
  editForm.enabled = m.enabled
  editForm.cooldown_seconds = m.cooldown_seconds ?? 300
  editForm.script_metadata = m.script_metadata || null

  // 初始化参数值：优先用已保存值，否则用 metadata 默认值
  const defaultParams: Record<string, unknown> = {}
  if (m.script_metadata?.parameters) {
    for (const pdef of m.script_metadata.parameters) {
      defaultParams[pdef.name] = m.params?.[pdef.name] ?? pdef.default
    }
  }
  editForm.params = { ...defaultParams }
  editVisible.value = true

  // 预加载已选股票信息 + 策略列表 + 自选股分组
  stockSearchLoading.value = true
  try {
    const [searchRes, stratRes] = await Promise.all([
      Promise.all(m.stock_codes.map(code => monitorApi.searchStocks(code, 1))),
      monitorApi.getStrategiesForMonitor(),
    ])
    // 合并搜索结果用于显示已选项
    stockSearchResults.value = searchRes.flatMap(r => r.data)
    strategyOptions.value = stratRes.data
  } catch {
    // 不阻塞编辑
  } finally {
    stockSearchLoading.value = false
  }

  // 加载自选股分组
  selectedWatchlistGroupId.value = null
  loadWatchlistGroups()
}

async function submitEdit() {
  editSaving.value = true
  try {
    const updateData: Record<string, unknown> = {
      monitor_name: editForm.monitor_name,
      description: editForm.description,
      stock_codes: editForm.stock_codes,
      strategy_ids: editForm.strategy_ids,
      interval: editForm.interval,
      trigger_mode: editForm.trigger_mode,
      enabled: editForm.enabled,
      cooldown_seconds: editForm.cooldown_seconds,
    }
    // 仅当有参数时提交 params
    if (editForm.script_metadata?.parameters?.length) {
      updateData.params = { ...editForm.params }
    }
    await monitorApi.updateMonitor(editMonitorId.value, updateData as any)
    ElMessage.success('已保存')
    editVisible.value = false
    await loadMonitors()
  } catch (e: any) {
    showApiError(e, '保存失败')
  } finally {
    editSaving.value = false
  }
}

async function handleDelete(m: MonitorInfo) {
  try {
    await ElMessageBox.confirm(
      `确定要删除监控「${m.monitor_name || m.monitor_id}」吗？\n脚本文件和配置将永久删除，无法恢复。`,
      '删除确认',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return // cancelled
  }

  try {
    await monitorApi.deleteMonitor(m.monitor_id)
    ElMessage.success('已删除')
    await loadMonitors()
  } catch (e: any) {
    showApiError(e, '删除失败')
  }
}

function getStatusClass(m: MonitorInfo): string {
  if (m.error_message) return 'status-error'
  if (!m.enabled) return 'status-paused'
  if (m.last_result?.triggered) return 'status-triggered'
  return 'status-active'
}

function formatTime(ts: string): string {
  if (!ts) return ''
  return ts.replace('T', ' ').substring(11, 19) || ts.substring(0, 19)
}

onMounted(() => {
  loadMonitors()
  loadLogs()
  connectWs()
})

onUnmounted(() => {
  if (stockSearchTimer) {
    clearTimeout(stockSearchTimer)
    stockSearchTimer = null
  }
})
</script>

<style scoped>
.monitor-page {
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
}

.no-permission-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 400px;
}

/* ── Hero ── */
.monitor-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 28px;
}

.hero-title {
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
  margin: 0 0 4px;
}

.hero-subtitle {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.hero-agent-btn {
  background: var(--color-accent) !important;
  border-color: var(--color-accent) !important;
  color: #fff !important;
  font-weight: 500;
}
.hero-agent-btn:hover,
.hero-agent-btn:focus {
  background: var(--color-accent-light) !important;
  border-color: var(--color-accent-light) !important;
  color: #fff !important;
}

.hero-refresh {
  border-color: var(--border-default) !important;
}

/* WS indicator */
.ws-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 20px;
  background: rgba(156, 163, 175, 0.1);
  font-size: 12px;
  color: var(--text-muted);
}

.ws-indicator.connected {
  background: rgba(22, 163, 74, 0.08);
  color: var(--color-success);
}

.ws-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
}

.ws-indicator.connected .ws-dot {
  background: var(--color-success);
  animation: pulse-dot 2s infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* ── Tabs ── */
.monitor-tabs {
  margin-bottom: 20px;
}

.monitor-tabs :deep(.el-tabs__header) {
  margin-bottom: 16px;
}

.monitor-tabs :deep(.el-tabs__nav-wrap::after) {
  background-color: var(--border-subtle);
}

.monitor-tabs :deep(.el-tabs__item) {
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 500;
}

.monitor-tabs :deep(.el-tabs__item.is-active) {
  color: var(--color-accent-light, #c9a55a);
}

.monitor-tabs :deep(.el-tabs__active-bar) {
  background-color: var(--color-accent-light, #c9a55a);
}

/* ── Stats ── */
.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-bottom: 28px;
}

@media (max-width: 900px) {
  .stat-grid { grid-template-columns: repeat(2, 1fr); }
}

/* ── Section Header ── */
.section-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: 16px;
}

.section-header h2 {
  font-family: var(--font-display);
  font-size: 17px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.section-hint {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}

.section-actions {
  display: flex;
  gap: 8px;
}

/* ── Empty State ── */
.empty-state {
  text-align: center;
  padding: 60px 20px;
  background: var(--color-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
}

.empty-icon {
  color: var(--border-strong);
  margin-bottom: 16px;
}

.empty-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 6px;
}

.empty-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0 0 20px;
}

.loading-state {
  padding: 24px;
  background: var(--color-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
}

/* ── Monitor Cards ── */
.monitor-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 14px;
}

@media (max-width: 768px) {
  .monitor-grid { grid-template-columns: 1fr; }
}

.monitor-card {
  background: var(--color-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: all 0.25s var(--ease-out);
  position: relative;
}

.monitor-card:hover {
  border-color: var(--border-default);
  box-shadow: var(--shadow-sm);
  transform: translateY(-1px);
}

.monitor-card.is-disabled {
  opacity: 0.6;
}

.monitor-card.has-error {
  border-color: rgba(220, 38, 38, 0.2);
}

/* Card Header */
.mc-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.mc-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.mc-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.mc-status-dot.status-active {
  background: var(--color-success);
  box-shadow: 0 0 6px rgba(22, 163, 74, 0.4);
}

.mc-status-dot.status-paused {
  background: var(--text-muted);
}

.mc-status-dot.status-error {
  background: var(--color-danger);
  box-shadow: 0 0 6px rgba(220, 38, 38, 0.4);
}

.mc-status-dot.status-triggered {
  background: var(--color-up);
  box-shadow: 0 0 6px rgba(220, 38, 38, 0.3);
}

.mc-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Description */
.mc-desc {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* Stock chips */
.mc-stocks {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.stock-chip {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--color-accent-subtle);
  color: var(--color-accent);
  letter-spacing: 0.02em;
}

.stock-chip.strategy-chip {
  background: rgba(22, 163, 74, 0.08);
  color: var(--color-success);
}

.stock-chip.sm {
  font-size: 10px;
  padding: 1px 6px;
}

/* Param chips */
.mc-params {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.param-chip {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(59, 130, 246, 0.08);
  color: #3b82f6;
  letter-spacing: 0.02em;
}

/* Last result */
.mc-result {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 12px;
  padding: 8px 10px;
  background: var(--color-bg);
  border-radius: var(--radius-sm);
  line-height: 1.5;
}

.mc-result > .el-icon {
  flex-shrink: 0;
  margin-top: 2px;
}

.mc-error {
  color: var(--color-danger);
}

.mc-triggered {
  color: var(--color-up);
  font-weight: 500;
}

.mc-normal {
  color: var(--text-secondary);
}

.mc-time {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
  margin-right: 4px;
}

/* Card Footer */
.mc-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 10px;
  border-top: 1px solid var(--border-subtle);
  margin-top: auto;
}

.mc-id {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
}

.mc-footer-right {
  display: flex;
  gap: 4px;
}

.mc-btn {
  width: 30px;
  height: 30px;
  border: none;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  background: transparent;
  color: var(--text-secondary);
  transition: all 0.15s;
}

.mc-btn:hover {
  background: var(--color-bg);
  color: var(--text-primary);
}

.mc-btn.btn-ok:hover { color: var(--color-success); background: rgba(22, 163, 74, 0.08); }
.mc-btn.btn-warn:hover { color: var(--color-warning); background: rgba(217, 119, 6, 0.08); }
.mc-btn.btn-primary:hover { color: var(--color-accent); background: var(--color-accent-subtle); }
.mc-btn.btn-danger:hover { color: var(--color-danger); background: rgba(220, 38, 38, 0.08); }
.mc-btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── Logs ── */
.logs-card {
  border-radius: var(--radius-md);
}

.log-time {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
}

.log-msg {
  font-size: 12px;
  color: var(--color-up);
  font-weight: 500;
}

.log-msg-error {
  font-size: 12px;
  color: var(--color-warning);
  font-weight: 500;
}

.log-dash {
  color: var(--text-muted);
  font-size: 12px;
}

.log-row-error {
  background-color: rgba(217, 119, 6, 0.04) !important;
}

/* ── Live Alerts ── */
.live-section {
  margin-top: 28px;
}

.live-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.live-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: var(--color-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  font-size: 13px;
  animation: slideIn 0.3s var(--ease-out);
}

@keyframes slideIn {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}

.live-pulse {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-up);
  flex-shrink: 0;
  animation: pulse-dot 1.5s infinite;
}

.live-time {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
  min-width: 60px;
}

.live-stock {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  min-width: 75px;
}

.live-msg {
  color: var(--color-up);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Script Drawer ── */
.script-drawer-content {
  padding: 0 4px;
}

.script-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.script-code {
  background: #1a1b26;
  color: #a9b1d6;
  padding: 20px;
  border-radius: var(--radius-md);
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.7;
  overflow-x: auto;
  margin: 0;
}

/* ── Edit Dialog ── */
.edit-form {
  padding: 4px 0;
}

.edit-hint {
  font-size: 12px;
  color: var(--text-muted);
}

.edit-form :deep(.el-divider__text) {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}
</style>
