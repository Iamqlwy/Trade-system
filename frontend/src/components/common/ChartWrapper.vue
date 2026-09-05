<template>
  <div class="chart-card">
    <div v-if="$slots.header" class="chart-card__header">
      <slot name="header" />
    </div>
    <div ref="chartRef" class="chart-card__canvas" :style="{ height: height + 'px' }"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, computed } from 'vue'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { useThemeStore } from '@/stores/theme'

const props = withDefaults(
  defineProps<{
    option: EChartsOption
    height?: number
    theme?: string
  }>(),
  {
    height: 400,
    theme: 'default',
  },
)

const chartRef = ref<HTMLElement>()
let chart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null

// Design system chart colors
const DESIGN_COLORS = [
  '#b08d47', '#2563eb', '#dc2626', '#16a34a',
  '#7c3aed', '#0891b2', '#d97706', '#be185d',
]

// 保留函数的深拷贝 — JSON.parse/stringify 会丢失 formatter 等回调函数
function deepClonePreservingFns(val: unknown): unknown {
  if (val === null || typeof val !== 'object') return val
  if (typeof val === 'function') return val
  if (val instanceof Date) return new Date(val.getTime())
  if (val instanceof RegExp) return new RegExp(val.source, val.flags)
  if (Array.isArray(val)) return val.map(deepClonePreservingFns)
  const result: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(val as Record<string, unknown>)) {
    result[k] = deepClonePreservingFns(v)
  }
  return result
}

const themeStore = useThemeStore()
const isDark = computed(() => themeStore.mode === 'dark')

function injectThemeDefaults(opt: EChartsOption): EChartsOption {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const cloned = deepClonePreservingFns(opt) as any
  const dark = isDark.value

  // Theme-aware colors
  const axisLineColor = dark ? '#242836' : '#e8e6e1'
  const splitLineColor = dark ? '#181c26' : '#f0eee9'
  const labelColor = dark ? '#8b8fa4' : '#9ca3af'
  const tooltipBg = dark ? 'rgba(24,28,38,0.96)' : 'rgba(255,255,255,0.96)'
  const tooltipBorder = dark ? '#242836' : '#e8e6e1'
  const tooltipTextColor = dark ? '#e2e4ea' : '#1a1a2e'
  const tooltipShadow = dark ? '0 4px 12px rgba(0,0,0,0.4)' : '0 4px 12px rgba(0,0,0,0.08)'
  const legendColor = dark ? '#8b8fa4' : '#6b7280'

  // Inject font family
  if (cloned.textStyle) {
    cloned.textStyle.fontFamily = "'Plus Jakarta Sans', sans-serif"
  } else {
    cloned.textStyle = { fontFamily: "'Plus Jakarta Sans', sans-serif" }
  }
  // Inject axis styles
  if (cloned.xAxis) {
    const axes = Array.isArray(cloned.xAxis) ? cloned.xAxis : [cloned.xAxis]
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    axes.forEach((axis: any) => {
      if (axis.axisLine) {
        axis.axisLine.lineStyle = { color: axisLineColor }
      } else {
        axis.axisLine = { lineStyle: { color: axisLineColor } }
      }
      if (axis.axisLabel) {
        axis.axisLabel.color = labelColor
        axis.axisLabel.fontSize = 11
      } else {
        axis.axisLabel = { color: labelColor, fontSize: 11 }
      }
    })
  }
  if (cloned.yAxis) {
    const axes = Array.isArray(cloned.yAxis) ? cloned.yAxis : [cloned.yAxis]
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    axes.forEach((axis: any) => {
      if (axis.splitLine) {
        axis.splitLine.lineStyle = { color: splitLineColor, type: 'dashed' }
      } else {
        axis.splitLine = { lineStyle: { color: splitLineColor, type: 'dashed' } }
      }
      if (axis.axisLabel) {
        axis.axisLabel.color = labelColor
        axis.axisLabel.fontSize = 11
      } else {
        axis.axisLabel = { color: labelColor, fontSize: 11 }
      }
    })
  }
  // Inject tooltip theme
  if (cloned.tooltip) {
    const tip = cloned.tooltip as Record<string, unknown>
    tip.backgroundColor = tooltipBg
    tip.borderColor = tooltipBorder
    tip.borderWidth = 1
    tip.textStyle = { color: tooltipTextColor, fontSize: 12, fontFamily: "'Plus Jakarta Sans', sans-serif" }
    tip.extraCssText = `box-shadow: ${tooltipShadow}; border-radius: 8px; padding: 10px 14px;`
  }
  // Inject legend theme
  if (cloned.legend) {
    const leg = cloned.legend as Record<string, unknown>
    leg.textStyle = { color: legendColor, fontSize: 12, fontFamily: "'Plus Jakarta Sans', sans-serif" }
    leg.icon = 'roundRect'
    leg.itemWidth = 12
    leg.itemHeight = 3
  }
  // Inject default color palette
  if (!cloned.color) {
    cloned.color = DESIGN_COLORS
  }
  return cloned
}

onMounted(() => {
  if (chartRef.value) {
    chart = echarts.init(chartRef.value, undefined, { renderer: 'canvas' })
    chart.setOption(injectThemeDefaults(props.option), true)

    resizeObserver = new ResizeObserver(() => {
      chart?.resize()
    })
    resizeObserver.observe(chartRef.value)
  }
})

watch(
  () => props.option,
  (newOption) => {
    if (chart) {
      chart.setOption(injectThemeDefaults(newOption), true)
    }
  },
  { deep: true },
)

// 主题切换时重新渲染图表
watch(isDark, () => {
  if (chart) {
    chart.setOption(injectThemeDefaults(props.option), true)
  }
})

onUnmounted(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.chart-card {
  width: 100%;
}

.chart-card__header {
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.chart-card__canvas {
  width: 100%;
}
</style>
