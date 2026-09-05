<template>
  <div class="stat-card">
    <div class="stat-card__icon" :style="{ background: iconBg }">
      <el-icon :size="18" :style="{ color: iconColor }">
        <component :is="icon" />
      </el-icon>
    </div>
    <div class="stat-card__content">
      <div class="stat-card__label">{{ label }}</div>
      <div class="stat-card__value" :style="{ color: valueColor }">{{ displayValue }}</div>
      <div v-if="suffix" class="stat-card__suffix">{{ suffix }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Component } from 'vue'

const props = withDefaults(
  defineProps<{
    label: string
    value: string | number
    icon?: Component
    iconColor?: string
    valueColor?: string
    suffix?: string
  }>(),
  {
    iconColor: '#b08d47',
    valueColor: 'var(--text-primary)',
  },
)

const iconBg = computed(() => {
  // Create subtle background from icon color
  const color = props.iconColor
  if (color.startsWith('#')) {
    const r = parseInt(color.slice(1, 3), 16)
    const g = parseInt(color.slice(3, 5), 16)
    const b = parseInt(color.slice(5, 7), 16)
    return `rgba(${r}, ${g}, ${b}, 0.08)`
  }
  return 'var(--color-accent-subtle)'
})

const displayValue = computed(() => {
  if (typeof props.value === 'number') {
    return props.value.toLocaleString('zh-CN')
  }
  return props.value
})
</script>

<style scoped>
.stat-card {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 20px;
  background: var(--color-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}

.stat-card:hover {
  border-color: var(--border-default);
  box-shadow: var(--shadow-sm);
  transform: translateY(-1px);
}

.stat-card__icon {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-card__content {
  flex: 1;
  min-width: 0;
}

.stat-card__label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  letter-spacing: 0.03em;
  text-transform: uppercase;
  margin-bottom: 6px;
}

.stat-card__value {
  font-family: var(--font-mono);
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.02em;
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
  word-break: break-all;
}

.stat-card__suffix {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
  font-weight: 500;
}
</style>
