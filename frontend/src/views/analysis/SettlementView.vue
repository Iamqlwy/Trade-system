<template>
  <div class="analysis-page">
    <div class="page-header">
      <div>
        <h2>清算分析</h2>
        <p class="page-desc">已清仓/未清仓收益分析</p>
      </div>
      <div class="header-actions">
        <el-select v-model="strategyId" style="width: 200px" @change="loadData">
          <el-option v-for="s in strategies" :key="s.strategy_id" :label="s.name" :value="s.strategy_id" />
        </el-select>
        <el-select v-model="status" style="width: 120px" @change="loadData">
          <el-option value="全部" label="全部" />
          <el-option value="已清仓" label="已清仓" />
          <el-option value="未清仓" label="未清仓" />
        </el-select>
      </div>
    </div>

    <div v-loading="loading">
      <!-- Summary -->
      <div class="stat-grid stagger-children" v-if="summary">
        <StatCard label="总收益" :value="'¥' + (summary?.total_profit || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2 })"
          :value-color="(summary?.total_profit || 0) >= 0 ? '#dc2626' : '#16a34a'" icon-color="#b08d47" />
        <StatCard label="已清仓" :value="summary?.closed_count || 0" icon-color="#2563eb" />
        <StatCard label="未清仓" :value="summary?.open_count || 0" icon-color="#d97706" />
        <StatCard label="盈利次数" :value="summary?.win_count || 0" value-color="#dc2626" icon-color="#dc2626" />
        <StatCard label="亏损次数" :value="summary?.loss_count || 0" value-color="#16a34a" icon-color="#16a34a" />
        <StatCard label="胜率" :value="(summary?.win_rate || 0).toFixed(1) + '%'" icon-color="#7c3aed" />
      </div>

      <!-- Profit Distribution Chart -->
      <el-card shadow="never" style="margin-bottom: 16px">
        <template #header>已清仓收益分布</template>
        <ChartWrapper :option="chartOption" :height="350" />
      </el-card>

      <!-- Detail Table -->
      <el-card shadow="never">
        <template #header>清算明细</template>
        <el-table ref="tableRef" :data="tableData" stripe size="small" max-height="400" border style="width: 100%">
          <el-table-column prop="stock_code" label="代码" width="100" header-align="left" />
          <el-table-column prop="name" label="名称" min-width="110" header-align="left" show-overflow-tooltip />
          <el-table-column label="实现收益" min-width="128" align="right" header-align="left" sortable sort-by="realized_profit">
            <template #default="{ row }">
              <span :class="(row.realized_profit || 0) >= 0 ? 'pnl-up' : 'pnl-down'">
                ¥{{ parseFloat(row.realized_profit || 0).toLocaleString() }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="82" align="center" header-align="left" sortable sort-by="is_closed">
            <template #default="{ row }">
              <span class="status-pill" :class="row.is_closed ? 'pill-closed' : 'pill-open'">
                {{ row.is_closed ? '已清仓' : '持仓中' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="first_buy_time" label="首次建仓" width="164" header-align="left" sortable sort-by="first_buy_time" />
          <el-table-column prop="close_time" label="清仓时间" width="164" header-align="left" sortable sort-by="close_time" />
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
import type { SettlementSummary, SettlementRow } from '@/types/analysis'
import type { EChartsOption } from 'echarts'

const strategiesStore = useStrategiesStore()
const strategies = computed(() => strategiesStore.strategies)
const strategyId = ref('')
const status = ref('全部')
const loading = ref(false)
const tableRef = ref<HTMLElement | null>(null)

useRealtimeResize(tableRef)

const summary = ref<SettlementSummary | null>(null)
const chartData = ref<{ code: string; name: string; profit: number }[]>([])
const tableData = ref<SettlementRow[]>([])

const chartOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 120, right: 40, top: 20, bottom: 30 },
  xAxis: { type: 'value', name: '收益(¥)' },
  yAxis: { type: 'category', data: chartData.value.map((d) => `${d.name}(${d.code})`) },
  series: [{
    type: 'bar',
    data: chartData.value.map((d) => ({
      value: d.profit,
      itemStyle: {
        color: d.profit >= 0 ? 'rgba(220,38,38,0.65)' : 'rgba(22,163,74,0.65)',
        borderRadius: [0, 4, 4, 0],
      },
    })),
    label: {
      show: true, position: 'outside',
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      formatter: (p: any) => `¥${Number(p.value).toFixed(2)}`,
      fontSize: 11,
      color: '#6b7280',
      fontFamily: "'IBM Plex Mono', monospace",
    },
  }],
}))

async function loadData() {
  if (!strategyId.value) return
  loading.value = true
  try {
    const res = await analysisApi.settlementData(strategyId.value, status.value)
    summary.value = res.data.summary || null
    chartData.value = res.data.data || []
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

.header-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.status-pill {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 10px;
  letter-spacing: 0.02em;
}

.pill-closed {
  color: var(--color-success);
  background: rgba(22, 163, 74, 0.08);
}

.pill-open {
  color: var(--color-warning);
  background: rgba(217, 119, 6, 0.08);
}
</style>
