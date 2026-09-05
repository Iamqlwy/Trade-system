<template>
  <el-card shadow="never" class="position-table-card">
    <template #header>
      <div class="card-header-row">
        <span class="card-section-title">持仓</span>
        <el-button size="small" :icon="Refresh" circle class="mini-refresh" @click="loadPositions" />
      </div>
    </template>
    <el-table ref="tableRef" :data="positions" v-loading="loading" size="small" stripe border style="width: 100%">
      <el-table-column prop="stock_code" label="代码" width="100" header-align="left" />
      <el-table-column prop="stock_name" label="名称" min-width="90" header-align="left" show-overflow-tooltip />
      <el-table-column label="市价" width="88" align="right" header-align="left" sortable :sort-method="(a: any, b: any) => parseFloat(getMarketPrice(a.stock_code)) - parseFloat(getMarketPrice(b.stock_code))">
        <template #default="{ row }">
          <span class="num">{{ getMarketPrice(row.stock_code) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="成本价" width="88" align="right" header-align="left" sortable :sort-method="(a: any, b: any) => parseFloat(a.avg_price) - parseFloat(b.avg_price)">
        <template #default="{ row }">
          <span class="num">{{ parseFloat(row.avg_price).toFixed(2) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="市值" width="120" align="right" header-align="left" sortable :sort-method="(a: any, b: any) => parseFloat(calcMarketValue(a).replace(/,/g, '')) - parseFloat(calcMarketValue(b).replace(/,/g, ''))">
        <template #default="{ row }">
          <span class="num">¥{{ calcMarketValue(row) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="浮动盈亏" width="118" align="right" header-align="left" sortable :sort-method="(a: any, b: any) => parseFloat(calcPnl(a).replace(/[,+]/g, '')) - parseFloat(calcPnl(b).replace(/[,+]/g, ''))">
        <template #default="{ row }">
          <span :class="pnlClass(row)" class="num">{{ calcPnl(row) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="盈亏%" width="86" align="right" header-align="left" sortable :sort-method="(a: any, b: any) => parseFloat(calcPnlPct(a).replace(/[%+]/g, '')) - parseFloat(calcPnlPct(b).replace(/[%+]/g, ''))">
        <template #default="{ row }">
          <span :class="pnlClass(row)" class="num">{{ calcPnlPct(row) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="total" label="总量" width="76" align="right" header-align="left" sortable />
      <el-table-column prop="available" label="可用" width="76" align="right" header-align="left" sortable />
      <el-table-column prop="frozen" label="冻结" width="76" align="right" header-align="left" sortable />
      <el-table-column prop="remark" label="备注" min-width="110" header-align="left">
        <template #default="{ row }">
          <el-input
            :model-value="row.remark"
            size="small"
            placeholder="备注"
            @blur="(e: FocusEvent) => updateRemark(row.stock_code, (e.target as HTMLInputElement).value)"
          />
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRealtimeResize } from '@/composables/useRealtimeResize'
import { Refresh } from '@element-plus/icons-vue'
import { useMarketStore } from '@/stores/market'
import * as positionsApi from '@/api/positions'
import type { PositionResponse } from '@/types/position'
import { ElMessage } from 'element-plus'
import { showApiError } from '@/utils/notify'

const props = defineProps<{ strategyId: string }>()

const positions = ref<PositionResponse[]>([])
const loading = ref(false)
const tableRef = ref<HTMLElement | null>(null)

useRealtimeResize(tableRef)
const marketStore = useMarketStore()

function getMarketPrice(code: string): string {
  const tick = marketStore.getTick(code)
  return tick ? parseFloat(tick.last_price).toFixed(2) : '--'
}

function calcMarketValue(row: PositionResponse): string {
  const tick = marketStore.getTick(row.stock_code)
  const price = tick ? parseFloat(tick.last_price) : parseFloat(row.avg_price)
  return (price * row.total).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function calcPnl(row: PositionResponse): string {
  const tick = marketStore.getTick(row.stock_code)
  const price = tick ? parseFloat(tick.last_price) : parseFloat(row.avg_price)
  const avgPrice = parseFloat(row.avg_price)
  const pnl = (price - avgPrice) * row.total
  const sign = pnl >= 0 ? '+' : ''
  return sign + pnl.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function calcPnlPct(row: PositionResponse): string {
  const tick = marketStore.getTick(row.stock_code)
  const price = tick ? parseFloat(tick.last_price) : parseFloat(row.avg_price)
  const avgPrice = parseFloat(row.avg_price)
  if (avgPrice === 0) return '0.00%'
  const pct = ((price - avgPrice) / avgPrice) * 100
  const sign = pct >= 0 ? '+' : ''
  return sign + pct.toFixed(2) + '%'
}

function pnlClass(row: PositionResponse): string {
  const tick = marketStore.getTick(row.stock_code)
  const price = tick ? parseFloat(tick.last_price) : parseFloat(row.avg_price)
  const avgPrice = parseFloat(row.avg_price)
  if (price > avgPrice) return 'pnl-up'
  if (price < avgPrice) return 'pnl-down'
  return 'pnl-flat'
}

async function loadPositions() {
  loading.value = true
  try {
    const res = await positionsApi.listPositions(props.strategyId)
    positions.value = res.data
  } finally {
    loading.value = false
  }
}

async function updateRemark(stockCode: string, remark: string) {
  try {
    await positionsApi.updateRemark(props.strategyId, stockCode, remark)
  } catch (err) {
    showApiError(err, '更新备注失败')
  }
}

onMounted(loadPositions)

defineExpose({ loadPositions })
</script>

<style scoped>
.position-table-card {
  border-radius: var(--radius-md) !important;
}

.card-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-section-title {
  font-family: var(--font-display);
  font-weight: 600;
  font-size: 15px;
}

.mini-refresh {
  border-color: var(--border-default) !important;
  color: var(--text-muted) !important;
}

.mini-refresh:hover {
  border-color: var(--color-accent) !important;
  color: var(--color-accent) !important;
}
</style>
