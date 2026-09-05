<template>
  <div class="admin-dashboard">
    <!-- 顶部标题 + 日期选择 -->
    <div class="admin-header">
      <div class="header-left">
        <h1 class="hero-title">管理面板</h1>
        <p class="hero-subtitle">系统统计与历史趋势分析</p>
      </div>
      <div class="header-right">
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          :shortcuts="dateShortcuts"
          @change="loadTrends"
        />
        <el-button :icon="Refresh" circle class="hero-refresh" @click="refreshAll" :loading="loading" />
      </div>
    </div>

    <!-- Tab 分区 -->
    <el-tabs v-model="activeTab" class="admin-tabs">
      <!-- 概览 Tab -->
      <el-tab-pane label="概览" name="overview">
        <div class="tab-content">
          <div class="stat-grid stagger-children">
            <StatCard label="用户总数" :value="stats.total_users" :icon="User" icon-color="#3b82f6" suffix="注册用户" />
            <StatCard
              label="策略总数"
              :value="stats.total_strategies"
              :icon="Briefcase"
              icon-color="#b08d47"
              :suffix="`模拟 ${stats.sim_strategies} / 实盘 ${stats.live_strategies}`"
            />
            <StatCard
              label="订单总数"
              :value="stats.total_orders"
              :icon="Document"
              icon-color="#16a34a"
              :suffix="`今日 ${stats.total_orders_today}`"
            />
            <StatCard
              label="待处理反馈"
              :value="stats.pending_feedback_count"
              :icon="ChatLineSquare"
              :icon-color="stats.pending_feedback_count > 0 ? '#dc2626' : '#6b7280'"
              :value-color="stats.pending_feedback_count > 0 ? '#dc2626' : 'var(--text-primary)'"
              suffix="条未回复"
            />
            <StatCard
              label="在线用户"
              :value="stats.unique_online_count"
              :icon="Connection"
              :icon-color="stats.unique_online_count > 0 ? '#0891b2' : '#6b7280'"
              :value-color="stats.unique_online_count > 0 ? '#0891b2' : 'var(--text-primary)'"
              suffix="当前在线"
            />
          </div>

          <el-card shadow="never" class="chart-card-el">
            <template #header>
              <div class="chart-header">
                <span>在线用户</span>
                <el-tag type="success" size="small">{{ stats.unique_online_count }} 人在线</el-tag>
              </div>
            </template>
            <el-table :data="stats.online_users" size="small" style="width: 100%" v-loading="loading">
              <el-table-column prop="user_id" label="ID" width="60" />
              <el-table-column prop="username" label="用户名" min-width="100" />
              <el-table-column label="角色" width="90">
                <template #default="{ row }">
                  <el-tag :type="row.role === 'admin' ? 'danger' : row.role === 'trader' ? 'warning' : 'info'" size="small">
                    {{ row.role }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="连接时间" min-width="160">
                <template #default="{ row }">
                  <span class="time-cell">{{ formatTime(row.connected_since) }}</span>
                </template>
              </el-table-column>
            </el-table>
            <div v-if="!stats.online_users.length" class="empty-hint">
              <span>当前无在线用户</span>
            </div>
          </el-card>

          <div class="chart-row">
            <el-card shadow="never" class="chart-card-el">
              <template #header>
                <div class="chart-header">
                  <span>用户注册趋势</span>
                  <el-tag type="info" size="small">按日统计</el-tag>
                </div>
              </template>
              <ChartWrapper :option="userRegistrationsChart" :height="280" />
            </el-card>

            <el-card shadow="never" class="chart-card-el">
              <template #header>
                <div class="chart-header">
                  <span>策略创建趋势</span>
                  <el-tag type="info" size="small">模拟/实盘</el-tag>
                </div>
              </template>
              <ChartWrapper :option="strategyCreationsChart" :height="280" />
            </el-card>
          </div>
        </div>
      </el-tab-pane>

      <!-- 交易 Tab -->
      <el-tab-pane label="交易" name="trading">
        <div class="tab-content">
          <div class="stat-grid stagger-children">
            <StatCard
              label="订单总数"
              :value="stats.total_orders"
              :icon="Document"
              icon-color="#2563eb"
              :suffix="`今日 ${stats.total_orders_today}`"
            />
            <StatCard
              label="成交总数"
              :value="stats.total_trades"
              :icon="Finished"
              icon-color="#b08d47"
              :suffix="`今日 ${stats.total_trades_today}`"
            />
            <StatCard
              label="总资产"
              :value="formatMoney(stats.total_assets)"
              :icon="Money"
              icon-color="#16a34a"
              suffix="全策略合计"
            />
          </div>

          <div class="chart-row">
            <el-card shadow="never" class="chart-card-el">
              <template #header>
                <div class="chart-header">
                  <span>委托订单趋势</span>
                  <el-tag type="info" size="small">模拟/实盘</el-tag>
                </div>
              </template>
              <ChartWrapper :option="ordersChart" :height="320" />
            </el-card>

            <el-card shadow="never" class="chart-card-el">
              <template #header>
                <div class="chart-header">
                  <span>成交趋势</span>
                  <el-tag type="info" size="small">模拟/实盘</el-tag>
                </div>
              </template>
              <ChartWrapper :option="tradesChart" :height="320" />
            </el-card>
          </div>

          <el-card shadow="never" class="chart-card-el full-width">
            <template #header>
              <div class="chart-header">
                <span>资产趋势</span>
                <el-tag type="info" size="small">模拟/实盘</el-tag>
              </div>
            </template>
            <ChartWrapper :option="assetsChart" :height="350" />
          </el-card>
        </div>
      </el-tab-pane>

      <!-- 监控 Tab -->
      <el-tab-pane label="监控" name="monitor">
        <div class="tab-content">
          <div class="stat-grid stagger-children">
            <StatCard label="监控任务" :value="stats.total_monitors" :icon="Bell" icon-color="#d97706" suffix="个监控" />
            <StatCard label="定时任务" :value="stats.total_cron_jobs" :icon="Timer" icon-color="#0891b2" suffix="个 Cron" />
          </div>

          <div class="chart-row">
            <el-card shadow="never" class="chart-card-el">
              <template #header>
                <div class="chart-header">
                  <span>监控告警趋势</span>
                  <el-tag type="info" size="small">按日统计</el-tag>
                </div>
              </template>
              <ChartWrapper :option="monitorAlertsChart" :height="320" />
            </el-card>

            <el-card shadow="never" class="chart-card-el">
              <template #header>
                <div class="chart-header">
                  <span>定时任务执行</span>
                  <el-tag type="info" size="small">成功率</el-tag>
                </div>
              </template>
              <ChartWrapper :option="cronJobsChart" :height="320" />
            </el-card>
          </div>
        </div>
      </el-tab-pane>

      <!-- Agent Tab -->
      <el-tab-pane label="Agent" name="agent">
        <div class="tab-content">
          <div class="chart-row">
            <el-card shadow="never" class="chart-card-el">
              <template #header>
                <div class="chart-header">
                  <span>Agent 会话数</span>
                  <el-tag type="info" size="small">按日统计</el-tag>
                </div>
              </template>
              <ChartWrapper :option="agentSessionsChart" :height="320" />
            </el-card>

            <el-card shadow="never" class="chart-card-el">
              <template #header>
                <div class="chart-header">
                  <span>用户消息数</span>
                  <el-tag type="info" size="small">按日统计</el-tag>
                </div>
              </template>
              <ChartWrapper :option="userMessagesChart" :height="320" />
            </el-card>
          </div>

          <el-card shadow="never" class="chart-card-el full-width">
            <template #header>
              <div class="chart-header">
                <span>上下文长度</span>
                <el-tag type="info" size="small">总字符数</el-tag>
              </div>
            </template>
            <ChartWrapper :option="contextCharsChart" :height="350" />
          </el-card>
        </div>
      </el-tab-pane>

      <!-- 用户 Tab -->
      <el-tab-pane label="用户" name="users">
        <div class="tab-content">
          <div class="stat-grid stagger-children">
            <StatCard label="用户总数" :value="stats.total_users" :icon="User" icon-color="#3b82f6" suffix="注册用户" />
            <StatCard
              label="待处理反馈"
              :value="stats.pending_feedback_count"
              :icon="ChatLineSquare"
              :icon-color="stats.pending_feedback_count > 0 ? '#dc2626' : '#6b7280'"
              :value-color="stats.pending_feedback_count > 0 ? '#dc2626' : 'var(--text-primary)'"
              suffix="条未回复"
            />
          </div>

          <div class="chart-row">
            <el-card shadow="never" class="chart-card-el">
              <template #header>
                <div class="chart-header">
                  <span>用户反馈趋势</span>
                  <el-tag type="info" size="small">提交/待处理/已解决</el-tag>
                </div>
              </template>
              <ChartWrapper :option="feedbacksChart" :height="320" />
            </el-card>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  Refresh, User, Briefcase, Document, Finished,
  ChatLineSquare, Connection, Bell, Timer, Money,
} from '@element-plus/icons-vue'
import StatCard from '@/components/common/StatCard.vue'
import ChartWrapper from '@/components/common/ChartWrapper.vue'
import { getStats, getTrends, type AdminStats, type TrendsResponse } from '@/api/admin'
import type { EChartsOption } from 'echarts'

const loading = ref(false)
const activeTab = ref('overview')

const stats = ref<AdminStats>({
  total_users: 0,
  total_strategies: 0,
  sim_strategies: 0,
  live_strategies: 0,
  total_orders: 0,
  total_orders_today: 0,
  total_trades: 0,
  total_trades_today: 0,
  pending_feedback_count: 0,
  total_monitors: 0,
  total_cron_jobs: 0,
  unique_online_count: 0,
  online_users: [],
  total_assets: 0,
  total_market_value: 0,
})

const trends = ref<TrendsResponse>({
  monitor_alerts: [],
  cron_jobs: [],
  orders: [],
  trades: [],
  assets: [],
  agent_sessions: [],
  user_registrations: [],
  strategy_creations: [],
  feedbacks: [],
})

// 日期范围（默认近 30 天）
const dateRange = ref<[string, string]>([
  new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10),
  new Date().toISOString().slice(0, 10),
])

const dateShortcuts = [
  {
    text: '最近7天',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setTime(start.getTime() - 7 * 86400000)
      return [start, end]
    },
  },
  {
    text: '最近30天',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setTime(start.getTime() - 30 * 86400000)
      return [start, end]
    },
  },
  {
    text: '最近90天',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setTime(start.getTime() - 90 * 86400000)
      return [start, end]
    },
  },
]

let timer: ReturnType<typeof setInterval> | null = null

// 图表配置
const monitorAlertsChart = computed<EChartsOption>(() => {
  const dates = trends.value.monitor_alerts.map(d => d.date)
  const counts = trends.value.monitor_alerts.map(d => d.count)
  return {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: dates },
    yAxis: { type: 'value', name: '告警次数' },
    series: [{
      type: 'line',
      smooth: true,
      data: counts,
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(220,38,38,0.15)' },
            { offset: 1, color: 'rgba(220,38,38,0)' }
          ]
        }
      },
      itemStyle: { color: '#dc2626' },
    }],
  }
})

const cronJobsChart = computed<EChartsOption>(() => {
  const dates = trends.value.cron_jobs.map(d => d.date)
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['成功', '失败'], bottom: 0 },
    xAxis: { type: 'category', data: dates },
    yAxis: { type: 'value', name: '执行次数' },
    series: [
      { name: '成功', type: 'bar', stack: 'total', data: trends.value.cron_jobs.map(d => d.success), itemStyle: { color: '#16a34a' } },
      { name: '失败', type: 'bar', stack: 'total', data: trends.value.cron_jobs.map(d => d.failed), itemStyle: { color: '#dc2626' } },
    ],
  }
})

const ordersChart = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: ['模拟', '实盘'], bottom: 0 },
  xAxis: { type: 'category', data: trends.value.orders.map(d => d.date) },
  yAxis: { type: 'value', name: '订单数' },
  series: [
    { name: '模拟', type: 'bar', stack: 'total', data: trends.value.orders.map(d => d.sim), itemStyle: { color: '#2563eb' } },
    { name: '实盘', type: 'bar', stack: 'total', data: trends.value.orders.map(d => d.live), itemStyle: { color: '#dc2626' } },
  ],
}))

const tradesChart = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: ['模拟', '实盘'], bottom: 0 },
  xAxis: { type: 'category', data: trends.value.trades.map(d => d.date) },
  yAxis: { type: 'value', name: '成交数' },
  series: [
    { name: '模拟', type: 'bar', stack: 'total', data: trends.value.trades.map(d => d.sim_count), itemStyle: { color: '#b08d47' } },
    { name: '实盘', type: 'bar', stack: 'total', data: trends.value.trades.map(d => d.live_count), itemStyle: { color: '#dc2626' } },
  ],
}))

const assetsChart = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: ['模拟总资产', '实盘总资产'], bottom: 0 },
  grid: { left: 80, right: 40, top: 20, bottom: 60 },
  xAxis: { type: 'category', data: trends.value.assets.map(d => d.date) },
  yAxis: {
    type: 'value',
    name: '金额',
    axisLabel: { formatter: (v: number) => `¥${(v/10000).toFixed(1)}万` }
  },
  series: [
    {
      name: '模拟总资产', type: 'line', smooth: true,
      data: trends.value.assets.map(d => d.sim_total),
      itemStyle: { color: '#2563eb' },
      areaStyle: {
        color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(37,99,235,0.15)' },
            { offset: 1, color: 'rgba(37,99,235,0)' }
          ]
        }
      }
    },
    {
      name: '实盘总资产', type: 'line', smooth: true,
      data: trends.value.assets.map(d => d.live_total),
      itemStyle: { color: '#dc2626' },
      areaStyle: {
        color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(220,38,38,0.15)' },
            { offset: 1, color: 'rgba(220,38,38,0)' }
          ]
        }
      }
    },
  ],
}))

const agentSessionsChart = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'category', data: trends.value.agent_sessions.map(d => d.date) },
  yAxis: { type: 'value', name: '会话数' },
  series: [{
    type: 'bar',
    data: trends.value.agent_sessions.map(d => d.new_sessions),
    itemStyle: { color: '#7c3aed', borderRadius: [4, 4, 0, 0] },
  }],
}))

const userMessagesChart = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'category', data: trends.value.agent_sessions.map(d => d.date) },
  yAxis: { type: 'value', name: '消息数' },
  series: [{
    type: 'line',
    smooth: true,
    data: trends.value.agent_sessions.map(d => d.user_messages),
    areaStyle: {
      color: {
        type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [
          { offset: 0, color: 'rgba(8,145,178,0.15)' },
          { offset: 1, color: 'rgba(8,145,178,0)' }
        ]
      }
    },
    itemStyle: { color: '#0891b2' },
  }],
}))

const contextCharsChart = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'category', data: trends.value.agent_sessions.map(d => d.date) },
  yAxis: {
    type: 'value',
    name: '字符数',
    axisLabel: { formatter: (v: number) => v >= 10000 ? `${(v/10000).toFixed(1)}万` : v.toString() }
  },
  series: [{
    type: 'line',
    smooth: true,
    data: trends.value.agent_sessions.map(d => d.context_chars),
    areaStyle: {
      color: {
        type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [
          { offset: 0, color: 'rgba(124,58,237,0.15)' },
          { offset: 1, color: 'rgba(124,58,237,0)' }
        ]
      }
    },
    itemStyle: { color: '#7c3aed' },
  }],
}))

const userRegistrationsChart = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'category', data: trends.value.user_registrations.map(d => d.date) },
  yAxis: { type: 'value', name: '新用户数' },
  series: [{
    type: 'bar',
    data: trends.value.user_registrations.map(d => d.new_users),
    itemStyle: { color: '#3b82f6', borderRadius: [4, 4, 0, 0] },
  }],
}))

const strategyCreationsChart = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: ['模拟', '实盘'], bottom: 0 },
  xAxis: { type: 'category', data: trends.value.strategy_creations.map(d => d.date) },
  yAxis: { type: 'value', name: '策略数' },
  series: [
    { name: '模拟', type: 'bar', stack: 'total', data: trends.value.strategy_creations.map(d => d.sim), itemStyle: { color: '#2563eb' } },
    { name: '实盘', type: 'bar', stack: 'total', data: trends.value.strategy_creations.map(d => d.live), itemStyle: { color: '#dc2626' } },
  ],
}))

const feedbacksChart = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: ['提交', '待处理', '已解决'], bottom: 0 },
  xAxis: { type: 'category', data: trends.value.feedbacks.map(d => d.date) },
  yAxis: { type: 'value', name: '反馈数' },
  series: [
    { name: '提交', type: 'bar', data: trends.value.feedbacks.map(d => d.total), itemStyle: { color: '#2563eb' } },
    { name: '待处理', type: 'bar', data: trends.value.feedbacks.map(d => d.pending), itemStyle: { color: '#d97706' } },
    { name: '已解决', type: 'bar', data: trends.value.feedbacks.map(d => d.resolved), itemStyle: { color: '#16a34a' } },
  ],
}))

function formatMoney(v: number): string {
  return (
    '¥' +
    v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  )
}

function formatTime(iso: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  const diff = Math.max(0, Date.now() - d.getTime())
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins} 分钟前`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} 小时前`
  return d.toLocaleString('zh-CN')
}

async function loadData() {
  loading.value = true
  try {
    const { data } = await getStats()
    stats.value = data
  } catch (err) {
    console.error('Failed to load stats:', err)
  } finally {
    loading.value = false
  }
}

async function loadTrends() {
  if (!dateRange.value) return
  loading.value = true
  try {
    const [startDate, endDate] = dateRange.value
    const { data } = await getTrends(startDate, endDate)
    trends.value = data
  } catch (err) {
    console.error('Failed to load trends:', err)
  } finally {
    loading.value = false
  }
}

async function refreshAll() {
  await Promise.all([loadData(), loadTrends()])
}

onMounted(() => {
  loadData()
  loadTrends()
  timer = setInterval(() => {
    loadData()
  }, 30000)
})

onUnmounted(() => {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
})
</script>

<style scoped>
.admin-dashboard {
  width: 100%;
}

.admin-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 28px;
}

.header-left {
  flex: 1;
}

.hero-title {
  font-family: var(--font-display);
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.01em;
  line-height: 1.2;
}

.hero-subtitle {
  font-size: 14px;
  color: var(--text-secondary);
  margin-top: 4px;
  font-weight: 400;
}

.header-right {
  display: flex;
  gap: 12px;
  align-items: center;
}

.hero-refresh {
  border-color: var(--border-default) !important;
  color: var(--text-secondary) !important;
  transition: all 0.2s;
}

.hero-refresh:hover {
  border-color: var(--color-accent) !important;
  color: var(--color-accent) !important;
}

.admin-tabs :deep(.el-tabs__header) {
  margin-bottom: 24px;
}

.admin-tabs :deep(.el-tabs__nav-wrap::after) {
  background-color: var(--border-subtle);
}

.tab-content {
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

.chart-card-el {
  border-radius: var(--radius-md) !important;
}

.chart-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(500px, 100%), 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.chart-row .chart-card-el {
  margin-bottom: 0;
}

.full-width {
  grid-column: 1 / -1;
  margin-bottom: 24px;
}

.chart-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.time-cell {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--text-secondary);
}

.empty-hint {
  text-align: center;
  padding: 40px 0;
  color: var(--text-muted);
  font-size: 14px;
}
</style>
