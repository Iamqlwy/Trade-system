<template>
  <div class="analysis-page">
    <div class="page-header">
      <div>
        <h2>风险评估</h2>
        <p class="page-desc">策略风险分析与评级</p>
      </div>
      <el-select v-model="strategyId" style="width: 200px" @change="loadData">
        <el-option v-for="s in strategies" :key="s.strategy_id" :label="s.name" :value="s.strategy_id" />
      </el-select>
    </div>

    <div v-loading="loading">
      <!-- Risk Level -->
      <el-card shadow="never" class="risk-level-card" v-if="metrics">
        <div class="risk-level" :class="riskLevelClass">
          <div class="risk-indicator">
            <div class="risk-circle">
              <el-icon :size="28"><WarningFilled /></el-icon>
            </div>
            <div class="risk-info">
              <span class="risk-label">风险等级</span>
              <span class="risk-value">{{ riskLevelText }}</span>
            </div>
          </div>
          <el-tag :type="riskLevelTag" size="large" effect="dark">{{ riskLevelText }}</el-tag>
        </div>
        <p class="risk-advice">{{ riskAdvice }}</p>
      </el-card>

      <!-- Metrics -->
      <div class="stat-grid stagger-children" v-if="metrics">
        <StatCard label="最大回撤" :value="(metrics.max_drawdown * 100).toFixed(2) + '%'" value-color="#16a34a" icon-color="#dc2626" />
        <StatCard label="年化收益" :value="(metrics.annual_return * 100).toFixed(2) + '%'" icon-color="#2563eb" />
        <StatCard label="夏普比率" :value="metrics.sharpe_ratio.toFixed(2)" icon-color="#7c3aed" />
        <StatCard label="波动率" :value="(metrics.volatility * 100).toFixed(2) + '%'" icon-color="#d97706" />
        <StatCard label="总收益率" :value="(metrics.total_return * 100).toFixed(2) + '%'" icon-color="#b08d47" />
        <StatCard label="胜率" :value="(metrics.win_rate * 100).toFixed(1) + '%'" icon-color="#16a34a" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'
import { useStrategiesStore } from '@/stores/strategies'
import StatCard from '@/components/common/StatCard.vue'
import * as analysisApi from '@/api/analysis'
import type { RiskMetrics } from '@/types/analysis'

const strategiesStore = useStrategiesStore()
const strategies = computed(() => strategiesStore.strategies)
const strategyId = ref('')
const loading = ref(false)
const metrics = ref<RiskMetrics | null>(null)

const riskLevelClass = computed(() => {
  if (!metrics.value) return ''
  const dd = Math.abs(metrics.value.max_drawdown)
  if (dd < 0.05) return 'risk-low'
  if (dd < 0.15) return 'risk-medium'
  return 'risk-high'
})

const riskLevelTag = computed(() => {
  if (!metrics.value) return 'info'
  const dd = Math.abs(metrics.value.max_drawdown)
  if (dd < 0.05) return 'success'
  if (dd < 0.15) return 'warning'
  return 'danger'
})

const riskLevelText = computed(() => {
  if (!metrics.value) return '--'
  const dd = Math.abs(metrics.value.max_drawdown)
  if (dd < 0.05) return '低风险'
  if (dd < 0.15) return '中等风险'
  return '高风险'
})

const riskAdvice = computed(() => {
  if (!metrics.value) return '请选择策略查看风险评估'
  const dd = Math.abs(metrics.value.max_drawdown)
  if (dd < 0.05) return '该策略最大回撤较小，风险控制良好，可以继续维持当前策略。'
  if (dd < 0.15) return '该策略最大回撤处于中等水平，建议关注持仓集中度，适当分散风险。'
  return '该策略最大回撤较大，建议降低仓位或调整策略参数，控制风险敞口。'
})

async function loadData() {
  if (!strategyId.value) return
  loading.value = true
  try {
    const res = await analysisApi.riskData(strategyId.value)
    metrics.value = res.data as RiskMetrics
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

.risk-level-card {
  border-radius: var(--radius-md) !important;
  margin-bottom: 20px;
}

.risk-level {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.risk-indicator {
  display: flex;
  align-items: center;
  gap: 16px;
}

.risk-circle {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.3s;
}

.risk-low .risk-circle {
  background: rgba(22, 163, 74, 0.08);
  color: var(--color-success);
}

.risk-medium .risk-circle {
  background: rgba(217, 119, 6, 0.08);
  color: var(--color-warning);
}

.risk-high .risk-circle {
  background: rgba(220, 38, 38, 0.08);
  color: var(--color-danger);
}

.risk-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.risk-label {
  font-size: 12px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 500;
}

.risk-value {
  font-family: var(--font-display);
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
}

.risk-advice {
  color: var(--text-secondary);
  font-size: 14px;
  margin-top: 16px;
  line-height: 1.6;
  padding-top: 16px;
  border-top: 1px solid var(--border-subtle);
}
</style>
