<template>
  <div class="analysis-page">
    <div class="page-header">
      <div>
        <h2>净值曲线</h2>
        <p class="page-desc">策略净值走势与风险指标</p>
      </div>
      <el-select v-model="strategyId" style="width: 200px" @change="loadData">
        <el-option v-for="s in strategies" :key="s.strategy_id" :label="s.name" :value="s.strategy_id" />
      </el-select>
    </div>

    <!-- Risk Metrics -->
    <div class="stat-grid stagger-children" v-if="metrics">
      <StatCard label="总收益率" :value="(metrics.total_return * 100).toFixed(2) + '%'"
        :value-color="metrics.total_return >= 0 ? '#dc2626' : '#16a34a'" icon-color="#b08d47" />
      <StatCard label="年化收益" :value="(metrics.annual_return * 100).toFixed(2) + '%'"
        :value-color="metrics.annual_return >= 0 ? '#dc2626' : '#16a34a'" icon-color="#2563eb" />
      <StatCard label="最大回撤" :value="(metrics.max_drawdown * 100).toFixed(2) + '%'" value-color="#16a34a" icon-color="#dc2626" />
      <StatCard label="夏普比率" :value="metrics.sharpe_ratio.toFixed(2)" icon-color="#7c3aed" />
      <StatCard label="波动率" :value="(metrics.volatility * 100).toFixed(2) + '%'" icon-color="#d97706" />
      <StatCard label="胜率" :value="(metrics.win_rate * 100).toFixed(1) + '%'" icon-color="#16a34a" />
    </div>

    <!-- Charts -->
    <div class="chart-row">
      <el-card shadow="never">
        <template #header>净值曲线</template>
        <ChartWrapper :option="equityChartOption" :height="350" />
      </el-card>
      <el-card shadow="never">
        <template #header>收益率</template>
        <ChartWrapper :option="returnChartOption" :height="350" />
      </el-card>
    </div>
    <el-card shadow="never" style="margin-top: 16px">
      <template #header>回撤曲线</template>
      <ChartWrapper :option="drawdownChartOption" :height="300" />
    </el-card>

    <!-- Data Table -->
    <el-card shadow="never" style="margin-top: 16px">
      <template #header>明细数据（近90日）</template>
      <el-table :data="tableData" stripe size="small" max-height="400" border style="width: 100%">
        <el-table-column prop="date" label="日期" width="110" sortable />
        <el-table-column label="净值比率" width="110" align="right" sortable sort-by="equity_ratio">
          <template #default="{ row }">{{ row.equity_ratio?.toFixed(4) }}</template>
        </el-table-column>
        <el-table-column label="收益率" width="108" align="right" sortable sort-by="return_pct">
          <template #default="{ row }">
            <span :class="row.return_pct >= 0 ? 'pnl-up' : 'pnl-down'">
              {{ (row.return_pct * 100).toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useStrategiesStore } from '@/stores/strategies'
import StatCard from '@/components/common/StatCard.vue'
import ChartWrapper from '@/components/common/ChartWrapper.vue'
import * as analysisApi from '@/api/analysis'
import type { RiskMetrics, EquityDataPoint } from '@/types/analysis'
import type { EChartsOption } from 'echarts'

const strategiesStore = useStrategiesStore()
const strategies = computed(() => strategiesStore.strategies)
const strategyId = ref('')

const metrics = ref<RiskMetrics | null>(null)
const tableData = ref<EquityDataPoint[]>([])
const equityDates = ref<string[]>([])
const equityValues = ref<number[]>([])
const returnValues = ref<number[]>([])
const drawdownValues = ref<number[]>([])

const equityChartOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 50, right: 20, top: 20, bottom: 30 },
  xAxis: { type: 'category', data: equityDates.value },
  yAxis: { type: 'value' },
  series: [{
    type: 'line', data: equityValues.value, smooth: true,
    lineStyle: { color: '#b08d47', width: 2.5 },
    itemStyle: { color: '#b08d47' },
    areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(176,141,71,0.12)' }, { offset: 1, color: 'rgba(176,141,71,0)' }] } },
    markLine: { data: [{ yAxis: 1.0, lineStyle: { type: 'dashed', color: '#d6d3cd' } }] },
  }],
}))

const returnChartOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis', formatter: (p: unknown) => `${(p as { value: number }[])[0]?.value?.toFixed(2)}%` },
  grid: { left: 50, right: 20, top: 20, bottom: 30 },
  xAxis: { type: 'category', data: equityDates.value },
  yAxis: { type: 'value', axisLabel: { formatter: '{value}%' } },
  series: [{
    type: 'line', data: returnValues.value, smooth: true,
    areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(37,99,235,0.12)' }, { offset: 1, color: 'rgba(37,99,235,0)' }] } },
    lineStyle: { color: '#2563eb', width: 2.5 },
    itemStyle: { color: '#2563eb' },
  }],
}))

const drawdownChartOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 50, right: 20, top: 20, bottom: 30 },
  xAxis: { type: 'category', data: equityDates.value },
  yAxis: { type: 'value', axisLabel: { formatter: '{value}%' } },
  series: [{
    type: 'line', data: drawdownValues.value, smooth: true,
    areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(220,38,38,0.12)' }, { offset: 1, color: 'rgba(220,38,38,0)' }] } },
    lineStyle: { color: '#dc2626', width: 2 },
    itemStyle: { color: '#dc2626' },
  }],
}))

async function loadData() {
  if (!strategyId.value) return
  try {
    const res = await analysisApi.equityData(strategyId.value)
    const d = res.data
    metrics.value = d.metrics || null
    tableData.value = d.table || []
    equityDates.value = d.equity?.dates || []
    equityValues.value = d.equity?.values || []
    returnValues.value = d.return_curve?.values || []
    drawdownValues.value = d.drawdown?.values || []
  } catch {
    metrics.value = null
  }
}

onMounted(() => {
  strategiesStore.fetchStrategies().then(() => {
    if (strategies.value.length > 0) {
      strategyId.value = strategies.value[0]!.strategy_id
      loadData()
    }
  })
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
</style>
