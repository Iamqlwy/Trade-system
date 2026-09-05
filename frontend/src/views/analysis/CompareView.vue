<template>
  <div class="analysis-page">
    <div class="page-header">
      <div>
        <h2>策略对比</h2>
        <p class="page-desc">多策略横向对比分析</p>
      </div>
    </div>

    <!-- Strategy Selection -->
    <el-card shadow="never" class="selection-card">
      <el-checkbox-group v-model="selectedIds" @change="loadData">
        <el-checkbox v-for="s in strategies" :key="s.strategy_id" :value="s.strategy_id" :label="s.name" />
      </el-checkbox-group>
    </el-card>

    <div v-loading="loading">
      <!-- Charts -->
      <div class="chart-row">
        <el-card shadow="never">
          <template #header>净值对比</template>
          <ChartWrapper :option="equityChartOption" :height="350" />
        </el-card>
        <el-card shadow="never">
          <template #header>收益率对比</template>
          <ChartWrapper :option="returnChartOption" :height="350" />
        </el-card>
      </div>
      <el-card shadow="never" style="margin-top: 16px">
        <template #header>回撤对比</template>
        <ChartWrapper :option="drawdownChartOption" :height="300" />
      </el-card>

      <!-- Risk Comparison Table -->
      <el-card shadow="never" style="margin-top: 16px">
        <template #header>风险指标对比</template>
        <el-table :data="riskTable" stripe size="small" border style="width: 100%">
          <el-table-column
            v-for="col in riskColumns"
            :key="col"
            :prop="col"
            :label="col"
            :min-width="col === '策略' ? 140 : 100"
            :align="col === '策略' ? 'left' : 'right'"
            :show-overflow-tooltip="col === '策略'"
            :sortable="col !== '策略'"
          />
        </el-table>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useStrategiesStore } from '@/stores/strategies'
import ChartWrapper from '@/components/common/ChartWrapper.vue'
import * as analysisApi from '@/api/analysis'
import type { CompareSeries, CompareRiskRow } from '@/types/analysis'
import type { EChartsOption } from 'echarts'

const strategiesStore = useStrategiesStore()
const strategies = computed(() => strategiesStore.strategies)
const selectedIds = ref<string[]>([])
const loading = ref(false)
const series = ref<CompareSeries[]>([])
const riskTable = ref<CompareRiskRow[]>([])
const riskColumns = ['策略', '总收益率', '年化收益', '最大回撤', '夏普比率', '波动率', '胜率']

const colors = ['#b08d47', '#2563eb', '#dc2626', '#16a34a', '#7c3aed', '#0891b2', '#d97706', '#be185d']

const equityChartOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: series.value.map((s) => s.name), bottom: 0 },
  grid: { left: 50, right: 20, top: 20, bottom: 50 },
  xAxis: { type: 'category', data: series.value[0]?.dates || [] },
  yAxis: { type: 'value' },
  series: series.value.map((s, i) => ({
    name: s.name, type: 'line' as const, data: s.equity, smooth: true,
    lineStyle: { width: 2.5, color: colors[i % colors.length] },
    itemStyle: { color: colors[i % colors.length] },
  })),
}))

const returnChartOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: series.value.map((s) => s.name), bottom: 0 },
  grid: { left: 50, right: 20, top: 20, bottom: 50 },
  xAxis: { type: 'category', data: series.value[0]?.dates || [] },
  yAxis: { type: 'value', axisLabel: { formatter: '{value}%' } },
  series: series.value.map((s, i) => ({
    name: s.name, type: 'line' as const, data: s.return_pct, smooth: true,
    lineStyle: { width: 2.5, color: colors[i % colors.length] },
    itemStyle: { color: colors[i % colors.length] },
  })),
}))

const drawdownChartOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: series.value.map((s) => s.name), bottom: 0 },
  grid: { left: 50, right: 20, top: 20, bottom: 50 },
  xAxis: { type: 'category', data: series.value[0]?.dates || [] },
  yAxis: { type: 'value', axisLabel: { formatter: '{value}%' } },
  series: series.value.map((s, i) => ({
    name: s.name, type: 'line' as const, data: s.drawdown, smooth: true,
    lineStyle: { width: 2, color: colors[i % colors.length] },
    itemStyle: { color: colors[i % colors.length] },
  })),
}))

async function loadData() {
  if (selectedIds.value.length === 0) return
  loading.value = true
  try {
    const res = await analysisApi.compareData(selectedIds.value)
    series.value = res.data.series || []
    riskTable.value = res.data.risk_table || []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  strategiesStore.fetchStrategies()
})
</script>

<style scoped>
.analysis-page {
  width: 100%;
}

.page-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 4px;
}

.selection-card {
  margin-bottom: 20px;
  border-radius: var(--radius-md) !important;
}

.selection-card :deep(.el-checkbox-group) {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
