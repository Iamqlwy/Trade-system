<template>
  <el-card shadow="never" class="order-table-card">
    <template #header>
      <div class="card-header-row">
        <span class="card-section-title">订单</span>
        <el-button size="small" :icon="Refresh" circle class="mini-refresh" @click="loadOrders" />
      </div>
    </template>
    <el-table ref="tableRef" :data="orders" v-loading="loading" size="small" stripe border style="width: 100%">
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
        <template #default="{ row }">
          <span class="num">{{ parseFloat(row.price).toFixed(2) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="order_volume" label="数量" width="72" align="right" header-align="left" sortable />
      <el-table-column prop="traded_volume" label="成交" width="72" align="right" header-align="left" sortable />
      <el-table-column label="状态" width="92" align="center" header-align="left">
        <template #default="{ row }">
          <StatusBadge :status="row.status" />
        </template>
      </el-table-column>
      <el-table-column label="时间" min-width="155" header-align="left" sortable sort-by="created_at">
        <template #default="{ row }">
          {{ formatTime(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column prop="order_id" label="订单号" min-width="130" header-align="left" show-overflow-tooltip />
      <el-table-column label="操作" width="72" fixed="right" header-align="left">
        <template #default="{ row }">
          <el-button
            v-if="row.status < 3"
            type="danger"
            link
            size="small"
            :loading="cancellingId === row.order_id"
            @click="handleCancel(row.order_id)"
          >
            撤单
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRealtimeResize } from '@/composables/useRealtimeResize'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import StatusBadge from '@/components/common/StatusBadge.vue'
import * as ordersApi from '@/api/orders'
import type { OrderResponse } from '@/types/order'

const props = defineProps<{ strategyId: string }>()

const orders = ref<OrderResponse[]>([])
const loading = ref(false)
const tableRef = ref<HTMLElement | null>(null)

useRealtimeResize(tableRef)
const cancellingId = ref<string | null>(null)

function formatTime(t: string): string {
  if (!t) return ''
  return t.replace('T', ' ').substring(0, 19)
}

async function loadOrders() {
  loading.value = true
  try {
    const res = await ordersApi.listOrders(props.strategyId)
    orders.value = res.data
  } finally {
    loading.value = false
  }
}

async function handleCancel(orderId: string) {
  try {
    await ElMessageBox.confirm('确定要撤销该订单吗？', '撤单确认', { type: 'warning' })
    cancellingId.value = orderId
    const res = await ordersApi.cancelOrder(props.strategyId, orderId)
    if (res.data.success) {
      ElMessage.success('撤单成功')
      await loadOrders()
    } else {
      ElMessage.error(res.data.message || '撤单失败')
    }
  } catch {
    // cancelled
  } finally {
    cancellingId.value = null
  }
}

onMounted(loadOrders)

defineExpose({ loadOrders })
</script>

<style scoped>
.order-table-card {
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
