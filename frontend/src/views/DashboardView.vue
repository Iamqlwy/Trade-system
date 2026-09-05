<template>
  <div class="dashboard">
    <!-- Hero Header -->
    <div class="dashboard-hero">
      <div class="hero-text">
        <h1 class="hero-title">仪表盘</h1>
        <p class="hero-subtitle">全局策略资产概览</p>
      </div>
      <el-button :icon="Refresh" circle class="hero-refresh" @click="loadData" />
    </div>

    <!-- Stats Grid -->
    <div class="stat-grid stagger-children">
      <StatCard
        label="策略数量"
        :value="strategies.length"
        :icon="Briefcase"
        icon-color="#b08d47"
        suffix="个策略"
      />
      <StatCard
        label="初始资金"
        :value="formatMoney(totalInitial)"
        :icon="Wallet"
        icon-color="#2563eb"
      />
      <StatCard
        label="可用资金"
        :value="formatMoney(totalAvailable)"
        :icon="Money"
        icon-color="#16a34a"
      />
      <StatCard
        label="冻结资金"
        :value="formatMoney(totalFrozen)"
        :icon="Lock"
        icon-color="#d97706"
      />
    </div>

    <!-- Charts -->
    <div class="chart-row">
      <el-card shadow="never" class="chart-card-el">
        <template #header>资金分配</template>
        <ChartWrapper :option="pieOption" :height="320" />
      </el-card>
      <el-card shadow="never" class="chart-card-el">
        <template #header>资产趋势</template>
        <ChartWrapper :option="lineOption" :height="320" />
      </el-card>
    </div>

    <!-- Strategy Cards -->
    <div class="section-header">
      <h2>策略概览</h2>
      <span class="section-count">{{ strategies.length }} 个策略</span>
    </div>
    <div class="strategy-cards stagger-children">
      <StrategyCard
        v-for="s in strategies"
        :key="s.strategy_id"
        :strategy="s"
        @click="router.push(`/strategies/${s.strategy_id}`)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useStrategiesStore } from '@/stores/strategies'
import { Refresh, Briefcase, Wallet, Money, Lock } from '@element-plus/icons-vue'
import StatCard from '@/components/common/StatCard.vue'
import ChartWrapper from '@/components/common/ChartWrapper.vue'
import StrategyCard from '@/components/strategy/StrategyCard.vue'
import type { EChartsOption } from 'echarts'

const router = useRouter()
const strategiesStore = useStrategiesStore()
const strategies = computed(() => strategiesStore.strategies)

const totalInitial = computed(() =>
  strategies.value.reduce((sum, s) => sum + parseFloat(s.initial_cash || '0'), 0),
)
const totalAvailable = computed(() =>
  strategies.value.reduce((sum, s) => sum + parseFloat(s.available_cash || '0'), 0),
)
const totalFrozen = computed(() =>
  strategies.value.reduce((sum, s) => sum + parseFloat(s.frozen_cash || '0'), 0),
)

function formatMoney(v: number): string {
  return (
    '¥' +
    v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  )
}

const pieOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'item', formatter: '{b}: ¥{c} ({d}%)' },
  legend: { bottom: 0 },
  series: [
    {
      type: 'pie',
      radius: ['45%', '72%'],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 8, borderColor: '#fff', borderWidth: 3 },
      label: { show: false },
      emphasis: {
        label: { show: true, fontSize: 14, fontWeight: 'bold' },
        itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.1)' },
      },
      data: strategies.value.map((s) => ({
        name: s.name || s.strategy_id,
        value: parseFloat(s.available_cash || '0'),
      })),
    },
  ],
}))

const lineOption = computed<EChartsOption>(() => {
  const colors = ['#b08d47', '#2563eb', '#dc2626', '#16a34a', '#7c3aed', '#0891b2']
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: strategies.value.map((s) => s.name || s.strategy_id), bottom: 0 },
    grid: { left: 60, right: 20, top: 20, bottom: 50 },
    xAxis: { type: 'category', data: ['初始', '当前'] },
    yAxis: {
      type: 'value',
      axisLabel: { formatter: (v: number) => `¥${(v / 10000).toFixed(1)}万` },
    },
    series: strategies.value.map((s, i) => ({
      name: s.name || s.strategy_id,
      type: 'line',
      smooth: true,
      color: colors[i % colors.length],
      symbolSize: 6,
      lineStyle: { width: 2.5 },
      data: [parseFloat(s.initial_cash || '0'), parseFloat(s.available_cash || '0')],
    })),
  }
})

async function loadData() {
  await strategiesStore.fetchStrategies()
}

onMounted(loadData)
</script>

<style scoped>
.dashboard {
  width: 100%;
}

/* ── Hero Header ── */
.dashboard-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 28px;
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

.hero-refresh {
  border-color: var(--border-default) !important;
  color: var(--text-secondary) !important;
  transition: all 0.2s;
}

.hero-refresh:hover {
  border-color: var(--color-accent) !important;
  color: var(--color-accent) !important;
}

/* ── Chart Card ── */
.chart-card-el {
  border-radius: var(--radius-md) !important;
}

/* ── Section Header ── */
.section-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 20px;
  margin-top: 8px;
}

.section-header h2 {
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.section-count {
  font-size: 13px;
  color: var(--text-muted);
  font-weight: 500;
}

/* ── Strategy Cards ── */
.strategy-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(400px, 100%), 1fr));
  gap: 16px;
}
</style>
