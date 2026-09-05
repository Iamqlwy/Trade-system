<template>
  <div class="analysis-page">
    <div class="page-header">
      <div>
        <h2>做T分析</h2>
        <p class="page-desc">日内 T+0 交易收益分析</p>
      </div>
      <el-select v-model="strategyId" style="width: 200px" @change="loadData">
        <el-option v-for="s in strategies" :key="s.strategy_id" :label="s.name" :value="s.strategy_id" />
      </el-select>
    </div>

    <div v-loading="loading">
      <!-- Summary -->
      <div class="stat-grid stagger-children" v-if="summary">
        <StatCard label="总收益" :value="'¥' + (summary?.total_profit || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2 })"
          :value-color="(summary?.total_profit || 0) >= 0 ? '#dc2626' : '#16a34a'" icon-color="#b08d47" />
        <StatCard label="总成交量" :value="(summary?.total_volume || 0).toLocaleString()" icon-color="#2563eb" />
        <StatCard label="交易天数" :value="summary?.trade_days || 0" icon-color="#7c3aed" />
        <StatCard label="股票数量" :value="summary?.stock_count || 0" icon-color="#0891b2" />
        <StatCard label="日均收益" :value="'¥' + (summary?.avg_daily || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2 })" icon-color="#16a34a" />
      </div>

      <div class="chart-row">
        <el-card shadow="never">
          <template #header>做T收益趋势</template>
          <ChartWrapper :option="trendOption" :height="350" />
        </el-card>
        <el-card shadow="never">
          <template #header>各股票做T收益</template>
          <ChartWrapper :option="perfOption" :height="350" />
        </el-card>
      </div>

      <!-- Detail Table -->
      <el-card shadow="never" style="margin-top: 16px">
        <template #header>明细记录</template>
        <el-table ref="tableRef" :data="tableData" stripe size="small" max-height="400" border style="width: 100%">
          <el-table-column prop="trade_date" label="日期" width="110" header-align="left" sortable />
          <el-table-column prop="stock_code" label="代码" width="100" header-align="left" />
          <el-table-column prop="stock_name" label="名称" min-width="90" header-align="left" show-overflow-tooltip />
          <el-table-column prop="t_profit" label="T收益" min-width="120" align="right" header-align="left" sortable>
            <template #default="{ row }">
              <span :class="row.t_profit >= 0 ? 'pnl-up' : 'pnl-down'">
                ¥{{ parseFloat(row.t_profit).toLocaleString() }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="t_volume" label="T数量" width="90" align="right" header-align="left" sortable />
        </el-table>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRealtimeResize } from '@/composables/useRealtimeResize'
import { useStrategiesStore } from '@/stores/strategies'
import StatCard from '@/components/common/StatCard.vue'
import ChartWrapper from '@/components/common/ChartWrapper.vue'
import * as analysisApi from '@/api/analysis'
import type { DayTSummary, DayTTrendPoint, DayTStockPerf } from '@/types/analysis'
import type { EChartsOption } from 'echarts'

const strategiesStore = useStrategiesStore()
const strategies = computed(() => strategiesStore.strategies)
const strategyId = ref('')
const loading = ref(false)
const tableRef = ref<HTMLElement | null>(null)

useRealtimeResize(tableRef)

const summary = ref<DayTSummary | null>(null)
const trendData = ref<DayTTrendPoint[]>([])
const perfData = ref<DayTStockPerf[]>([])
 
const tableData = ref<Record<string, unknown>[]>([])

const trendOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: ['每日', '累计'], bottom: 0 },
  grid: { left: 60, right: 60, top: 20, bottom: 50 },
  xAxis: { type: 'category', data: trendData.value.map((d) => d.date) },
  yAxis: [
    { type: 'value', name: '每日(¥)' },
    { type: 'value', name: '累计(¥)' },
  ],
  series: [
    {
      name: '每日', type: 'bar', yAxisIndex: 0,
      data: trendData.value.map((d) => ({
        value: d.profit,
        itemStyle: {
          color: d.profit >= 0 ? 'rgba(220,38,38,0.65)' : 'rgba(22,163,74,0.6)',
          borderRadius: [3, 3, 0, 0],
        },
      })),
    },
    {
      name: '累计', type: 'line', yAxisIndex: 1, smooth: true,
      data: trendData.value.map((d) => d.cumulative),
      lineStyle: { color: '#b08d47', width: 2.5 },
      itemStyle: { color: '#b08d47' },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(176,141,71,0.1)' }, { offset: 1, color: 'rgba(176,141,71,0)' }] } },
    },
  ],
}))

const perfOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 120, right: 20, top: 20, bottom: 30 },
  xAxis: { type: 'value', name: '收益(¥)' },
  yAxis: { type: 'category', data: perfData.value.map((p) => `${p.name}(${p.stock_code})`) },
  series: [{
    type: 'bar',
    data: perfData.value.map((p) => ({
      value: p.profit,
      itemStyle: {
        color: p.profit >= 0 ? 'rgba(220,38,38,0.65)' : 'rgba(22,163,74,0.65)',
        borderRadius: [0, 3, 3, 0],
      },
    })),
  }],
}))

async function loadData() {
  if (!strategyId.value) return
  loading.value = true
  try {
    const res = await analysisApi.daytData(strategyId.value)
    summary.value = res.data.summary || null
    trendData.value = res.data.trend || []
    perfData.value = res.data.perf || []
    tableData.value = res.data.table || []
  } finally {
    loading.value = false
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
