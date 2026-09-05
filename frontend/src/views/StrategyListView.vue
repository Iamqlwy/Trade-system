<template>
  <div class="strategies-page">
    <div class="page-header">
      <div>
        <h2>策略列表</h2>
        <p class="page-desc">管理所有交易策略</p>
      </div>
      <div class="header-actions">
        <el-tooltip
          :disabled="!isStrategyLimitReached"
          :content="`策略数量已达上限 (${authStore.maxStrategies})`"
          placement="top"
        >
          <el-button type="primary" @click="showCreate = true" :disabled="isStrategyLimitReached">
            <el-icon><Plus /></el-icon>
            创建策略
          </el-button>
        </el-tooltip>
        <el-button :icon="Refresh" circle class="refresh-btn" @click="strategiesStore.fetchStrategies()" />
      </div>
    </div>

    <el-card shadow="never" class="table-card">
      <el-table ref="tableRef" :data="strategiesStore.strategies" v-loading="strategiesStore.loading"
        stripe size="default" border style="width: 100%"
      >
        <el-table-column prop="name" label="策略名称" min-width="120" header-align="left" sortable>
          <template #default="{ row }">
            <router-link :to="`/strategies/${row.strategy_id}`" class="strategy-link">
              {{ row.name || row.strategy_id }}
            </router-link>
          </template>
        </el-table-column>
        <el-table-column label="模式" width="80" align="center" header-align="left" sortable sort-by="trade_mode">
          <template #default="{ row }">
            <span class="mode-tag" :class="row.trade_mode === 1 ? 'mode-real' : 'mode-sim'">
              {{ row.trade_mode === 1 ? '实盘' : '模拟' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="可用资金" width="120" align="right" header-align="left" sortable sort-by="available_cash">
          <template #default="{ row }">
            <span class="num">¥{{ formatNum(row.available_cash) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="冻结资金" width="110" align="right" header-align="left" sortable sort-by="frozen_cash">
          <template #default="{ row }">
            <span class="num">¥{{ formatNum(row.frozen_cash) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="position_count" label="持仓" width="80" align="center" header-align="left" sortable />
        <el-table-column prop="order_count_today" label="今日单" width="90" align="center" header-align="left" sortable />
        <el-table-column prop="trade_count_today" label="今日成交" width="99" align="center" header-align="left" sortable />
        <el-table-column prop="description" label="描述" min-width="120" header-align="left" show-overflow-tooltip sortable>
          <template #default="{ row }">
            {{ row.description || '—' }}
          </template>
        </el-table-column>
        <el-table-column prop="strategy_id" label="策略ID" min-width="120" header-align="left">
          <template #default="{ row }">
            <span class="strategy-id-text">{{ row.strategy_id }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="64" fixed="right">
          <template #default="{ row }">
            <el-popconfirm
              title="确定要删除此策略吗？删除后无法恢复。"
              confirm-button-text="删除"
              cancel-button-text="取消"
              icon-color="#dc2626"
              @confirm="handleDelete(row.strategy_id)"
            >
              <template #reference>
                <el-button type="danger" link size="small">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建策略对话框 -->
    <el-dialog v-model="showCreate" title="创建策略" width="720px" :close-on-click-modal="false">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="90px">
        <el-form-item label="策略名称" prop="name">
          <el-input v-model="createForm.name" placeholder="输入策略名称" maxlength="64" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="createForm.description"
            type="textarea"
            :rows="2"
            placeholder="简短描述（可选）"
            maxlength="200"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="详情">
          <el-input
            v-model="createForm.detail"
            type="textarea"
            :rows="5"
            placeholder="策略详细说明（可选）"
            maxlength="5000"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="交易模式" prop="trade_mode">
          <el-radio-group v-model="createForm.trade_mode">
            <el-radio :value="0">模拟</el-radio>
            <el-tooltip
              :disabled="authStore.canCreateReal"
              content="您没有创建实盘策略的权限"
              placement="top"
            >
              <el-radio :value="1" :disabled="!authStore.canCreateReal">实盘</el-radio>
            </el-tooltip>
          </el-radio-group>
          <div v-if="createForm.trade_mode === 1" class="trade-mode-hint">
            <el-icon><WarningFilled /></el-icon>
            <span>实盘模式将验证券商账户可用资金</span>
          </div>
        </el-form-item>
        <el-form-item label="初始资金" prop="initial_cash">
          <el-input-number
            v-model="createForm.initial_cash"
            :min="10000"
            :step="100000"
            :precision="2"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRealtimeResize } from '@/composables/useRealtimeResize'
import { useStrategiesStore } from '@/stores/strategies'
import { useAuthStore } from '@/stores/auth'
import { Refresh, Plus, WarningFilled, Lock } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { showApiError } from '@/utils/notify'
import type { FormInstance, FormRules } from 'element-plus'
import type { CreateStrategyRequest } from '@/types/strategy'

const strategiesStore = useStrategiesStore()
const authStore = useAuthStore()

const showCreate = ref(false)
const creating = ref(false)
const createFormRef = ref<FormInstance>()
const tableRef = ref<HTMLElement | null>(null)

useRealtimeResize(tableRef)

const createForm = reactive<CreateStrategyRequest>({
  name: '',
  description: '',
  detail: '',
  trade_mode: 0,
  initial_cash: '1000000',
})

const createRules: FormRules = {
  name: [
    { required: true, message: '请输入策略名称', trigger: 'blur' },
    { min: 1, max: 64, message: '名称长度 1-64 个字符', trigger: 'blur' },
  ],
  trade_mode: [{ required: true, message: '请选择交易模式', trigger: 'change' }],
  initial_cash: [{ required: true, message: '请输入初始资金', trigger: 'blur' }],
}

/** 策略数量是否已达上限 */
const isStrategyLimitReached = computed(() => {
  const max = authStore.maxStrategies
  if (max === -1) return false
  return strategiesStore.strategies.length >= max
})

function formatNum(v: string): string {
  return parseFloat(v || '0').toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

async function handleCreate() {
  const valid = await createFormRef.value?.validate().catch(() => false)
  if (!valid) return

  creating.value = true
  try {
    const res = await strategiesStore.createStrategy({
      name: createForm.name,
      description: createForm.description || '',
      detail: createForm.detail || '',
      trade_mode: createForm.trade_mode,
      initial_cash: String(createForm.initial_cash),
    })
    ElMessage.success(res.message || '策略创建成功')
    showCreate.value = false
    // 重置表单
    createForm.name = ''
    createForm.description = ''
    createForm.detail = ''
    createForm.trade_mode = 0
    createForm.initial_cash = '1000000'
  } catch (err: unknown) {
    showApiError(err, '创建失败')
  } finally {
    creating.value = false
  }
}

async function handleDelete(strategyId: string) {
  try {
    const res = await strategiesStore.deleteStrategy(strategyId)
    ElMessage.success(res.message || '策略已删除')
  } catch (err: unknown) {
    showApiError(err, '删除失败')
  }
}

onMounted(() => strategiesStore.fetchStrategies())
</script>

<style scoped>
.strategies-page {
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
  align-items: center;
}

.refresh-btn {
  border-color: var(--border-default) !important;
  color: var(--text-secondary) !important;
}

.table-card {
  border-radius: var(--radius-md) !important;
}

.strategy-link {
  color: var(--color-accent);
  text-decoration: none;
  font-weight: 600;
  transition: color 0.15s;
}

.strategy-link:hover {
  color: var(--color-accent-light);
  text-decoration: underline;
}

.strategy-id-text {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);
}

.mode-tag {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
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

.trade-mode-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  font-size: 12px;
  color: var(--color-warning);
}

.trade-mode-hint .el-icon {
  font-size: 14px;
}
</style>
