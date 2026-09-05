<template>
  <div class="analysis-page">
    <div class="page-header">
      <div>
        <h2>持仓监控</h2>
        <p class="page-desc">实时持仓分布与盈亏跟踪</p>
      </div>
      <div class="header-actions">
        <el-select v-model="strategyId" style="width: 200px" clearable placeholder="全部策略" @change="loadData">
          <el-option v-for="s in strategies" :key="s.strategy_id" :label="s.name" :value="s.strategy_id" />
        </el-select>
        <div class="toggle-group">
          <span class="toggle-label">实时</span>
          <el-switch v-model="useRealtime" @change="loadData" />
        </div>
      </div>
    </div>

    <div v-loading="loading">
      <!-- Summary -->
      <div class="stat-grid stagger-children" v-if="summaryData">
        <StatCard label="总市值" :value="'¥' + (summaryData?.total_mv || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2 })" icon-color="#b08d47" />
        <StatCard label="总成本" :value="'¥' + (summaryData?.total_cv || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2 })" icon-color="#2563eb" />
        <StatCard label="浮动盈亏" :value="'¥' + (summaryData?.total_pnl || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2 })"
          :value-color="(summaryData?.total_pnl || 0) >= 0 ? '#dc2626' : '#16a34a'" icon-color="#7c3aed" />
        <StatCard label="持仓数量" :value="summaryData?.count || 0" icon-color="#0891b2" />
      </div>

      <div class="chart-row">
        <el-card shadow="never">
          <template #header>持仓分布</template>
          <ChartWrapper :option="pieOption" :height="320" />
        </el-card>
        <el-card shadow="never">
          <template #header>持仓盈亏</template>
          <ChartWrapper :option="barOption" :height="320" />
        </el-card>
      </div>

      <!-- Detail Table -->
      <el-card shadow="never" style="margin-top: 16px">
        <template #header>持仓明细</template>
        <el-table ref="tableRef" :data="tableData" stripe size="small" border style="width: 100%">
          <el-table-column prop="策略" label="策略" min-width="120" header-align="left" show-overflow-tooltip />
          <el-table-column prop="代码" label="代码" width="100" header-align="left" />
          <el-table-column prop="股票" label="名称" min-width="90" header-align="left" show-overflow-tooltip />
          <el-table-column prop="持仓" label="持仓" width="76" align="right" header-align="left" sortable />
          <el-table-column prop="可用" label="可用" width="76" align="right" header-align="left" sortable />
          <el-table-column prop="成本价" label="成本价" width="86" align="right" header-align="left" sortable>
            <template #default="{ row }"><span class="num">{{ parseFloat(row['成本价'] || 0).toFixed(2) }}</span></template>
          </el-table-column>
          <el-table-column prop="市价" label="市价" width="86" align="right" header-align="left" sortable>
            <template #default="{ row }"><span class="num">{{ parseFloat(row['市价'] || 0).toFixed(2) }}</span></template>
          </el-table-column>
          <el-table-column prop="市值" label="市值" width="118" align="right" header-align="left" sortable>
            <template #default="{ row }"><span class="num">¥{{ parseFloat(row['市值'] || 0).toLocaleString() }}</span></template>
          </el-table-column>
          <el-table-column prop="浮动盈亏" label="浮动盈亏" min-width="120" align="right" header-align="left" sortable>
            <template #default="{ row }">
              <span :class="parseFloat(row['浮动盈亏'] || 0) >= 0 ? 'pnl-up' : 'pnl-down'" class="num">
                ¥{{ parseFloat(row['浮动盈亏'] || 0).toLocaleString() }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="盈亏比" label="盈亏%" width="88" align="right" header-align="left" sortable>
            <template #default="{ row }">
              <span :class="parseFloat(row['盈亏比'] || 0) >= 0 ? 'pnl-up' : 'pnl-down'" class="num">
                {{ parseFloat(row['盈亏比'] || 0).toFixed(2) }}%
              </span>
            </template>
          </el-table-column>
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
import type { EChartsOption } from 'echarts'

const strategiesStore = useStrategiesStore()
const strategies = computed(() => strategiesStore.strategies)
const strategyId = ref('')
const useRealtime = ref(true)
const loading = ref(false)
const tableRef = ref<HTMLElement | null>(null)

useRealtimeResize(tableRef)

const pieData = ref<{ name: string; value: number }[]>([])
const barData = ref<{ name: string; pnl: number }[]>([])
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const tableData = ref<any[]>([])
const summaryData = ref<{ total_mv: number; total_cv: number; total_pnl: number; count: number } | null>(null)

const pieOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'item', formatter: '{b}: ¥{c} ({d}%)' },
  series: [{
    type: 'pie',
    radius: ['42%', '72%'],
    data: pieData.value,
    itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 3 },
    emphasis: {
      label: { show: true, fontSize: 14, fontWeight: 'bold' },
      itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.1)' },
    },
  }],
}))

const barOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 100, right: 20, top: 20, bottom: 30 },
  xAxis: { type: 'value', name: '盈亏(万元)' },
  yAxis: { type: 'category', data: barData.value.map((d) => d.name) },
  series: [{
    type: 'bar',
    data: barData.value.map((d) => ({
      value: d.pnl / 10000,
      itemStyle: {
        color: d.pnl >= 0 ? 'rgba(220,38,38,0.65)' : 'rgba(22,163,74,0.65)',
        borderRadius: [0, 4, 4, 0],
      },
    })),
  }],
}))

async function loadData() {
  loading.value = true
  try {
    const res = await analysisApi.positionsData(strategyId.value, useRealtime.value)
    const d = res.data
    pieData.value = d.pie || []
    barData.value = d.bar || []
    tableData.value = d.table || []
    summaryData.value = d.summary || null
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  strategiesStore.fetchStrategies()
  loadData()
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
  gap: 14px;
  align-items: center;
  flex-wrap: wrap;
}

.toggle-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toggle-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}
</style>
