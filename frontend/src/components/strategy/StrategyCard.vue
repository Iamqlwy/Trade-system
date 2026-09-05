<template>
  <div class="strategy-card" @click="$emit('click')">
    <!-- Top accent bar -->
    <div class="card-accent" :class="modeClass" />

    <div class="card-inner">
      <!-- Header -->
      <div class="card-header">
        <div class="card-title-group">
          <span class="strategy-name">{{ strategy.name || strategy.strategy_id }}</span>
          <span class="mode-tag" :class="modeClass">
            {{ strategy.trade_mode === 1 ? '实盘' : '模拟' }}
          </span>
        </div>
        <span class="strategy-id">{{ strategy.strategy_id }}</span>
      </div>

      <!-- Body -->
      <div class="card-body">
        <div class="info-row">
          <span class="label">总资产</span>
          <span class="value num accent">¥{{ formatNum(totalAssets) }}</span>
        </div>
        <div class="divider" />
        <div class="info-row">
          <span class="label">可用资金</span>
          <span class="value num">¥{{ formatNum(available) }}</span>
        </div>
        <div class="info-row">
          <span class="label">冻结资金</span>
          <span class="value num">¥{{ formatNum(frozen) }}</span>
        </div>
        <div class="divider" />
        <div class="info-row metrics">
          <div class="metric">
            <span class="metric-value">{{ strategy.position_count }}</span>
            <span class="metric-label">持仓</span>
          </div>
          <div class="metric">
            <span class="metric-value">{{ strategy.order_count_today }}</span>
            <span class="metric-label">今日单</span>
          </div>
          <div class="metric">
            <span class="metric-value">{{ strategy.trade_count_today }}</span>
            <span class="metric-label">成交</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { StrategySummary } from '@/types/strategy'

const props = defineProps<{ strategy: StrategySummary }>()
defineEmits<{ click: [] }>()

const available = computed(() => parseFloat(props.strategy.available_cash || '0'))
const frozen = computed(() => parseFloat(props.strategy.frozen_cash || '0'))
const totalAssets = computed(() => available.value + frozen.value)
const modeClass = computed(() => (props.strategy.trade_mode === 1 ? 'mode-real' : 'mode-sim'))

function formatNum(n: number): string {
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.strategy-card {
  background: var(--color-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  cursor: pointer;
  overflow: hidden;
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  position: relative;
}

.strategy-card:hover {
  border-color: var(--border-default);
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

/* ── Top Accent Bar ── */
.card-accent {
  height: 3px;
  background: var(--border-default);
}

.card-accent.mode-real {
  background: linear-gradient(90deg, var(--color-up), #f97316);
}

.card-accent.mode-sim {
  background: linear-gradient(90deg, var(--color-info), #6366f1);
}

/* ── Mode Tags ── */
.mode-tag {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 4px;
}

.mode-tag.mode-real {
  color: var(--color-up);
  background: var(--color-up-bg);
}

.mode-tag.mode-sim {
  color: var(--color-info);
  background: rgba(37, 99, 235, 0.06);
}

/* ── Inner ── */
.card-inner {
  padding: 18px 20px;
}

/* ── Header ── */
.card-header {
  margin-bottom: 16px;
}

.card-title-group {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.strategy-name {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.strategy-id {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
}

/* ── Body ── */
.card-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.info-row .label {
  color: var(--text-secondary);
  font-size: 13px;
}

.info-row .value {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 500;
}

.info-row .value.accent {
  font-size: 16px;
  font-weight: 700;
  color: var(--color-accent);
}

.divider {
  height: 1px;
  background: var(--border-subtle);
}

/* ── Metrics Row ── */
.info-row.metrics {
  justify-content: space-around;
  padding-top: 4px;
}

.metric {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.metric-value {
  font-family: var(--font-mono);
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.metric-label {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 500;
}
</style>
