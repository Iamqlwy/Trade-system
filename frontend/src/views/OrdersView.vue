<template>
  <div class="orders-page">
    <div class="page-header">
      <div>
        <h2>订单管理</h2>
        <p class="page-desc">查看和管理所有委托订单</p>
      </div>
      <div class="header-actions">
        <el-select v-model="selectedStrategy" placeholder="选择策略" clearable style="width: 200px" @change="loadOrders">
          <el-option v-for="s in strategies" :key="s.strategy_id" :label="s.name" :value="s.strategy_id" />
        </el-select>
        <el-button :icon="Download" class="export-btn" @click="exportData">导出 CSV</el-button>
      </div>
    </div>

    <el-card shadow="never">
      <el-table ref="tableRef" :data="orders" v-loading="loading" stripe size="default" border style="width: 100%">
        <el-table-column prop="stock_code" label="代码" width="100" header-align="left" />
        <el-table-column prop="stock_name" label="名称" min-width="90" header-align="left" show-overflow-tooltip />
        <el-table-column label="方向" width="64" align="center" header-align="left">
          <template #default="{ row }">
            <span :class="row.order_type === 23 ? 'direction-buy' : 'direction-sell'" style="font-weight: 600">
              {{ row.order_type === 23 ? '买' : '卖' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="委托价" width="86" align="right" header-align="left" sortable>
          <template #default="{ row }"><span class="num">{{ parseFloat(row.price).toFixed(2) }}</span></template>
        </el-table-column>
        <el-table-column prop="order_volume" label="数量" width="80" align="right" header-align="left" sortable />
        <el-table-column prop="traded_volume" label="成交" width="80" align="right" header-align="left" sortable />
        <el-table-column label="成交价" width="86" align="right" header-align="left" sortable>
          <template #default="{ row }"><span class="num">{{ row.traded_price ? parseFloat(row.traded_price).toFixed(2) : '--' }}</span></template>
        </el-table-column>
        <el-table-column label="状态" width="92" align="center" header-align="left">
          <template #default="{ row }"><StatusBadge :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="时间" min-width="160" header-align="left" sortable sort-by="created_at">
          <template #default="{ row }">{{ row.created_at?.replace('T', ' ').substring(0, 19) }}</template>
        </el-table-column>
        <el-table-column prop="order_id" label="订单号" min-width="150" header-align="left" show-overflow-tooltip />
        <el-table-column prop="strategy_id" label="策略" min-width="120" header-align="left" show-overflow-tooltip />
        <el-table-column prop="order_remark" label="备注" min-width="130" show-overflow-tooltip header-align="left" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRealtimeResize } from '@/composables/useRealtimeResize'
import { Download } from '@element-plus/icons-vue'
import { useStrategiesStore } from '@/stores/strategies'
import { useCsvExport } from '@/composables/useCsvExport'
import StatusBadge from '@/components/common/StatusBadge.vue'
import * as ordersApi from '@/api/orders'
import type { OrderResponse } from '@/types/order'

const strategiesStore = useStrategiesStore()
const { exportCsv } = useCsvExport()
const strategies = computed(() => strategiesStore.strategies)

const selectedStrategy = ref('')
const orders = ref<OrderResponse[]>([])
const loading = ref(false)
const tableRef = ref<HTMLElement | null>(null)

useRealtimeResize(tableRef)

async function loadOrders() {
  if (!selectedStrategy.value) return
  loading.value = true
  try {
    const res = await ordersApi.listOrders(selectedStrategy.value)
    orders.value = res.data
  } finally {
    loading.value = false
  }
}

function exportData() {
  const headers = ['代码', '名称', '方向', '委托价', '数量', '成交', '成交价', '状态', '时间', '订单号', '策略', '备注']
  const rows = orders.value.map((o) => [
    o.stock_code, o.stock_name,
    o.order_type === 23 ? '买入' : '卖出',
    o.price, o.order_volume, o.traded_volume, o.traded_price,
    o.status_msg, o.created_at,
    o.order_id, o.strategy_id, o.order_remark,
  ])
  exportCsv(`订单_${selectedStrategy.value}.csv`, headers, rows)
}

onMounted(async () => {
  await strategiesStore.fetchStrategies()
  if (strategies.value.length > 0) {
    selectedStrategy.value = strategies.value[0]!.strategy_id
    loadOrders()
  }
})
</script>

<style scoped>
.orders-page {
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
