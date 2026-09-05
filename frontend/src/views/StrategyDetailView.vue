<template>
  <div class="strategy-detail" v-loading="loading">
    <!-- Header -->
    <div class="page-header">
      <div>
        <div class="header-row">
          <h2>{{ strategy?.name || id }}</h2>
          <span v-if="strategy" class="mode-tag" :class="strategy.trade_mode === 1 ? 'mode-real' : 'mode-sim'">
            {{ strategy.trade_mode === 1 ? '实盘' : '模拟' }}
          </span>
        </div>
        <p class="page-desc">策略 {{ id }}</p>
      </div>
      <el-button v-if="strategy" type="primary" plain @click="showEdit = true">
        <el-icon><Edit /></el-icon>
        编辑信息
      </el-button>
    </div>

    <!-- Description + Detail (merged card) -->
    <el-card v-if="strategy?.description || strategy?.detail" shadow="never" class="desc-card">
      <div class="desc-label">策略描述</div>
      <div class="desc-text">{{ strategy?.description || '暂无描述' }}</div>

      <div v-if="strategy?.detail" class="detail-section">
        <div class="detail-toggle" @click="detailExpanded = !detailExpanded">
          <span>策略详情</span>
          <el-icon :class="{ rotated: detailExpanded }"><ArrowDown /></el-icon>
        </div>
        <transition name="expand">
          <div v-show="detailExpanded" class="detail-text">{{ strategy.detail }}</div>
        </transition>
      </div>
    </el-card>

    <!-- Stats -->
    <div class="stat-grid stagger-children" v-if="strategy">
      <StatCard label="可用资金" :value="'¥' + formatNum(availableCash)" icon-color="#16a34a" />
      <StatCard label="冻结资金" :value="'¥' + formatNum(frozenCash)" icon-color="#d97706" />
      <StatCard label="今日订单" :value="strategy.order_count_today" icon-color="#2563eb" />
      <StatCard label="今日成交" :value="strategy.trade_count_today" icon-color="#b08d47" />
    </div>

    <!-- Order Form + Positions -->
    <div class="detail-grid">
      <OrderForm :strategy-id="id" @success="refresh" />
      <PositionTable ref="positionTableRef" :strategy-id="id" />
    </div>

    <!-- Orders -->
    <div style="margin-top: 20px">
      <OrderTable ref="orderTableRef" :strategy-id="id" />
    </div>

    <!-- 编辑对话框 -->
    <el-dialog v-model="showEdit" title="编辑策略信息" width="640px" :close-on-click-modal="false">
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="90px">
        <el-form-item label="策略名称" prop="name">
          <el-input v-model="editForm.name" placeholder="输入策略名称" maxlength="64" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="editForm.description"
            type="textarea"
            :rows="3"
            placeholder="策略描述（可选）"
            maxlength="1000"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="详情">
          <el-input
            v-model="editForm.detail"
            type="textarea"
            :rows="6"
            placeholder="策略详细说明（可选）"
            maxlength="5000"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEdit = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useStrategiesStore } from '@/stores/strategies'
import { Edit, ArrowDown } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { showApiError } from '@/utils/notify'
import type { FormInstance, FormRules } from 'element-plus'
import type { StrategySummary } from '@/types/strategy'
import * as strategiesApi from '@/api/strategies'
import StatCard from '@/components/common/StatCard.vue'
import OrderForm from '@/components/strategy/OrderForm.vue'
import PositionTable from '@/components/strategy/PositionTable.vue'
import OrderTable from '@/components/strategy/OrderTable.vue'

const props = defineProps<{ id: string }>()
const route = useRoute()
const strategyId = computed(() => props.id || (route.params.id as string))
const strategiesStore = useStrategiesStore()

const strategy = ref<StrategySummary | null>(null)
const loading = ref(false)
const positionTableRef = ref<InstanceType<typeof PositionTable>>()
const orderTableRef = ref<InstanceType<typeof OrderTable>>()

// 编辑相关
const showEdit = ref(false)
const saving = ref(false)
const detailExpanded = ref(false)
const editFormRef = ref<FormInstance>()
const editForm = reactive({
  name: '',
  description: '',
  detail: '',
})

const editRules: FormRules = {
  name: [
    { required: true, message: '请输入策略名称', trigger: 'blur' },
    { min: 1, max: 64, message: '名称长度 1-64 个字符', trigger: 'blur' },
  ],
}

const availableCash = computed(() => parseFloat(strategy.value?.available_cash || '0'))
const frozenCash = computed(() => parseFloat(strategy.value?.frozen_cash || '0'))

function formatNum(n: number): string {
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function openEditDialog() {
  if (!strategy.value) return
  editForm.name = strategy.value.name
  editForm.description = strategy.value.description || ''
  editForm.detail = strategy.value.detail || ''
}

// 监听对话框打开
watch(showEdit, (val) => {
  if (val) openEditDialog()
})

async function handleSave() {
  const valid = await editFormRef.value?.validate().catch(() => false)
  if (!valid) return

  saving.value = true
  try {
    await strategiesStore.updateStrategy(strategyId.value, {
      name: editForm.name,
      description: editForm.description || '',
      detail: editForm.detail || '',
    })
    ElMessage.success('策略信息已更新')
    showEdit.value = false
    await refresh()
  } catch (err: unknown) {
    showApiError(err, '保存失败')
  } finally {
    saving.value = false
  }
}

async function refresh() {
  positionTableRef.value?.loadPositions()
  orderTableRef.value?.loadOrders()
  await loadStrategy()
}

async function loadStrategy() {
  loading.value = true
  try {
    const res = await strategiesApi.getStrategy(strategyId.value)
    strategy.value = res.data
  } finally {
    loading.value = false
  }
}

onMounted(loadStrategy)
</script>

<style scoped>
.strategy-detail {
  width: 100%;
}

.header-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.page-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 4px;
  font-family: var(--font-mono);
}

.mode-tag {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 4px;
  letter-spacing: 0.03em;
}

.mode-tag.mode-real {
  color: var(--color-up);
  background: var(--color-up-bg);
}

.mode-tag.mode-sim {
  color: var(--color-info);
  background: rgba(37, 99, 235, 0.06);
}

.desc-card {
  margin-bottom: 20px;
  border-radius: var(--radius-md) !important;
}

.desc-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 8px;
}

.desc-text {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}

/* ── Detail Section (collapsible) ─ */
.detail-section {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--border-subtle);
}

.detail-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  cursor: pointer;
  user-select: none;
  transition: color 0.2s;
}

.detail-toggle:hover {
  color: var(--color-accent);
}

.detail-toggle .el-icon {
  font-size: 14px;
  transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.detail-toggle .rotated {
  transform: rotate(180deg);
}

.detail-text {
  margin-top: 12px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.7;
  background: #faf9f7;
  padding: 12px 16px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-subtle);
  white-space: pre-wrap;
  word-break: break-word;
}

/* ── Expand Transition ── */
.expand-enter-active,
.expand-leave-active {
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  overflow: hidden;
}

.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  max-height: 0;
  margin-top: 0;
}

.detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 380px) minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}

@media (max-width: 900px) {
  .detail-grid {
    grid-template-columns: 1fr;
  }
}
</style>
