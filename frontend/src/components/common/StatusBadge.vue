<template>
  <el-tag :type="tagType" :effect="effect" size="small" class="status-badge">
    <span v-if="showDot" class="status-dot" :class="dotClass" />
    {{ label }}
  </el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    status: number | string
    effect?: 'light' | 'dark' | 'plain'
    showDot?: boolean
  }>(),
  {
    effect: 'light',
    showDot: false,
  },
)

const statusMap: Record<number, { label: string; type: 'success' | 'warning' | 'danger' | 'info' | ''; dot: string }> = {
  0: { label: '待提交', type: 'info', dot: 'dot-info' },
  1: { label: '已提交', type: '', dot: 'dot-primary' },
  2: { label: '部分成交', type: 'warning', dot: 'dot-warning' },
  3: { label: '全部成交', type: 'success', dot: 'dot-success' },
  4: { label: '已撤单', type: 'danger', dot: 'dot-danger' },
  5: { label: '撤单中', type: 'warning', dot: 'dot-warning' },
  6: { label: '已失败', type: 'danger', dot: 'dot-danger' },
}

const tagType = computed(() => {
  if (typeof props.status === 'number') {
    return statusMap[props.status]?.type || 'info'
  }
  return 'info'
})

const label = computed(() => {
  if (typeof props.status === 'number') {
    return statusMap[props.status]?.label || `未知(${props.status})`
  }
  return String(props.status)
})

const dotClass = computed(() => {
  if (typeof props.status === 'number') {
    return statusMap[props.status]?.dot || 'dot-info'
  }
  return 'dot-info'
})
</script>

<style scoped>
.status-badge {
  font-size: 12px;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.status-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
}

.dot-info { background: var(--text-muted); }
.dot-primary { background: var(--color-info); }
.dot-success { background: var(--color-success); }
.dot-warning { background: var(--color-warning); }
.dot-danger { background: var(--color-danger); }
</style>
