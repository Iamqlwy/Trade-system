<template>
  <div class="analysis-page">
    <div class="page-header">
      <div>
        <h2>交易统计</h2>
        <p class="page-desc">个股交易汇总与胜率分析</p>
      </div>
      <el-select v-model="strategyId" style="width: 200px" @change="loadData">
        <el-option v-for="s in strategies" :key="s.strategy_id" :label="s.name" :value="s.strategy_id" />
      </el-select>
    </div>

    <div v-loading="loading">
      <!-- Summary -->
      <div class="stat-grid stagger-children" v-if="summaryData">
        <StatCard label="总交易" :value="summaryData['总交易'] || 0" icon-color="#b08d47" />
        <StatCard label="买入" :value="summaryData['买入'] || 0" value-color="#dc2626" icon-color="#dc2626" />
        <StatCard label="卖出" :value="summaryData['卖出'] || 0" value-color="#16a34a" icon-color="#16a34a" />
        <StatCard label="日均笔数" :value="summaryData['日均笔数'] || '0'" icon-color="#2563eb" />
        <StatCard label="平均金额" :value="summaryData['平均金额'] || '¥0'" icon-color="#7c3aed" />
      </div>

      <!-- Stock Stats Table -->
      <el-card shadow="never">
        <template #header>个股统计</template>
        <el-table ref="tableRef" :data="stockStats" stripe size="small" border style="width: 100%">
          <el-table-column prop="代码" label="代码" width="100" header-align="left" />
          <el-table-column prop="名称" label="名称" min-width="90" header-align="left" show-overflow-tooltip />
          <el-table-column prop="总盈亏" label="总盈亏" min-width="128" align="right" header-align="left" sortable>
            <template #default="{ row }">
              <span :class="row.total_profit_raw >= 0 ? 'pnl-up' : 'pnl-down'" class="num">
                {{ row['总盈亏'] }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="盈利次数" label="盈利" width="76" align="center" header-align="left" sortable>
            <template #default="{ row }">
              <span class="win-count">{{ row['盈利次数'] }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="亏损次数" label="亏损" width="76" align="center" header-align="left" sortable>
            <template #default="{ row }">
              <span class="loss-count">{{ row['亏损次数'] }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="胜率" label="胜率" width="78" align="center" header-align="left" sortable />
          <el-table-column prop="交易次数" label="交易次数" width="99" align="center" header-align="left" sortable />
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
import * as analysisApi from '@/api/analysis'
import type { StatisticsSummary, StockStat } from '@/types/analysis'

const strategiesStore = useStrategiesStore()
const strategies = computed(() => strategiesStore.strategies)
const strategyId = ref('')
const loading = ref(false)
const tableRef = ref<HTMLElement | null>(null)

useRealtimeResize(tableRef)

const summaryData = ref<StatisticsSummary | null>(null)
const stockStats = ref<StockStat[]>([])

async function loadData() {
  if (!strategyId.value) return
  loading.value = true
  try {
    const res = await analysisApi.statisticsData(strategyId.value)
    summaryData.value = res.data.summary || null
    stockStats.value = res.data.stock_stats || []
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

.win-count {
  color: var(--color-up);
  font-weight: 600;
  font-family: var(--font-mono);
}

.loss-count {
  color: var(--color-down);
  font-weight: 600;
  font-family: var(--font-mono);
}
</style>
