<template>
  <div class="trades-page">
    <div class="page-header">
      <div>
        <h2>成交记录</h2>
        <p class="page-desc">历史交易明细</p>
      </div>
      <div class="header-actions">
        <el-select v-model="selectedStrategy" placeholder="选择策略" clearable style="width: 200px" @change="loadTrades">
          <el-option v-for="s in strategies" :key="s.strategy_id" :label="s.name" :value="s.strategy_id" />
        </el-select>
        <el-button :icon="Download" class="export-btn" @click="exportData">导出 CSV</el-button>
      </div>
    </div>

    <!-- Charts -->
    <div class="chart-row" v-if="trades.length > 0">
      <el-card shadow="never">
        <template #header>每日成交量</template>
        <ChartWrapper :option="volumeChartOption" :height="300" />
      </el-card>
      <el-card shadow="never">
        <template #header>买卖分布</template>
        <ChartWrapper :option="pieChartOption" :height="300" />
      </el-card>
    </div>

    <!-- Table -->
    <el-card shadow="never">
      <el-table ref="tableRef" :data="trades" v-loading="loading" stripe size="default" border style="width: 100%">
        <el-table-column prop="stock_code" label="代码" width="100" header-align="left" />
        <el-table-column prop="stock_name" label="名称" min-width="90" header-align="left" show-overflow-tooltip />
        <el-table-column label="方向" width="64" align="center" header-align="left">
          <template #default="{ row }">
            <span :class="row.order_type === 23 ? 'direction-buy' : 'direction-sell'" style="font-weight: 600">
              {{ row.order_type === 23 ? '买' : '卖' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="成交价" width="92" align="right" header-align="left" sortable>
          <template #default="{ row }"><span class="num">{{ parseFloat(row.traded_price).toFixed(2) }}</span></template>
        </el-table-column>
        <el-table-column prop="traded_volume" label="数量" width="80" align="right" header-align="left" sortable />
        <el-table-column label="金额" width="118" align="right" header-align="left" sortable>
          <template #default="{ row }"><span class="num">¥{{ parseFloat(row.traded_amount).toLocaleString() }}</span></template>
        </el-table-column>
        <el-table-column label="时间" min-width="160" header-align="left" sortable sort-by="traded_time">
          <template #default="{ row }">{{ row.traded_time?.replace('T', ' ').substring(0, 19) }}</template>
        </el-table-column>
        <el-table-column prop="traded_id" label="成交号" min-width="150" header-align="left" show-overflow-tooltip />
        <el-table-column prop="strategy_id" label="策略" min-width="120" header-align="left" show-overflow-tooltip />
        <el-table-column prop="order_remark" label="备注" min-width="120" show-overflow-tooltip header-align="left" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRealtimeResize } from '@/composables/useRealtimeResize'
import { Download } from '@element-plus/icons-vue'
import { useStrategiesStore } from '@/stores/strategies'
import { useCsvExport } from '@/composables/useCsvExport'
import ChartWrapper from '@/components/common/ChartWrapper.vue'
import * as tradesApi from '@/api/trades'
import type { TradeResponse } from '@/types/trade'
import type { EChartsOption } from 'echarts'

const strategiesStore = useStrategiesStore()
const { exportCsv } = useCsvExport()
const strategies = computed(() => strategiesStore.strategies)

const selectedStrategy = ref('')
const trades = ref<TradeResponse[]>([])
const loading = ref(false)
const tableRef = ref<HTMLElement | null>(null)

useRealtimeResize(tableRef)

async function loadTrades() {
  if (!selectedStrategy.value) return
  loading.value = true
  try {
    const res = await tradesApi.listTrades(selectedStrategy.value)
    trades.value = res.data
  } finally {
    loading.value = false
  }
}

const volumeChartOption = computed<EChartsOption>(() => {
  const daily: Record<string, number> = {}
  for (const t of trades.value) {
    const date = t.traded_time?.substring(0, 10) || '未知'
    daily[date] = (daily[date] || 0) + t.traded_volume
  }
  const dates = Object.keys(daily).sort()
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 20, top: 20, bottom: 30 },
    xAxis: { type: 'category', data: dates },
    yAxis: { type: 'value' },
    series: [{
      type: 'bar',
      data: dates.map((d) => ({
        value: daily[d],
        itemStyle: { color: 'rgba(176, 141, 71, 0.6)', borderRadius: [3, 3, 0, 0] },
      })),
    }],
  }
})

const pieChartOption = computed<EChartsOption>(() => {
  const buyCount = trades.value.filter((t) => t.order_type === 23).length
  const sellCount = trades.value.filter((t) => t.order_type === 24).length
  return {
    tooltip: { trigger: 'item' },
    series: [{
      type: 'pie',
      radius: ['42%', '72%'],
      data: [
        { name: '买入', value: buyCount, itemStyle: { color: '#dc2626' } },
        { name: '卖出', value: sellCount, itemStyle: { color: '#16a34a' } },
      ],
      itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
    }],
  }
})

function exportData() {
  const headers = ['代码', '名称', '方向', '成交价', '数量', '金额', '时间', '成交号', '策略', '备注']
  const rows = trades.value.map((t) => [
    t.stock_code, t.stock_name,
    t.order_type === 23 ? '买入' : '卖出',
    t.traded_price, t.traded_volume, t.traded_amount, t.traded_time,
    t.traded_id, t.strategy_id, t.order_remark,
  ])
  exportCsv(`成交记录_${selectedStrategy.value}.csv`, headers, rows)
}

onMounted(async () => {
  await strategiesStore.fetchStrategies()
  if (strategies.value.length > 0) {
    selectedStrategy.value = strategies.value[0]!.strategy_id
    loadTrades()
  }
})
</script>

<style scoped>
.trades-page {
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

.export-btn {
  border-color: var(--border-default) !important;
  color: var(--text-secondary) !important;
  font-weight: 500;
}

.export-btn:hover {
  border-color: var(--color-accent) !important;
  color: var(--color-accent) !important;
}
</style>
