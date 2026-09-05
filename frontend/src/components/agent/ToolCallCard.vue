<template>
  <div class="tool-call-card" :class="{ expanded }">
    <div class="tool-header" @click="expanded = !expanded">
      <el-icon :class="toolCall.status" class="tool-status-icon">
        <Loading v-if="toolCall.status === 'running'" />
        <SuccessFilled v-else-if="toolCall.status === 'done'" />
        <CircleCloseFilled v-else />
      </el-icon>
      <span class="tool-name">{{ toolCall.name }}</span>
      <span class="tool-args-preview">{{ argsPreview }}</span>
      <el-icon class="expand-icon"><ArrowDown v-if="!expanded" /><ArrowUp v-else /></el-icon>
    </div>
    <transition name="expand">
      <div v-show="expanded" class="tool-body">
        <div class="tool-section">
          <div class="section-label">参数</div>
          <pre class="section-content">{{ toolCall.args }}</pre>
        </div>
        <div v-if="toolCall.result" class="tool-section">
          <div class="section-label">结果</div>
          <pre class="section-content">{{ toolCall.result }}</pre>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Loading, SuccessFilled, CircleCloseFilled, ArrowDown, ArrowUp } from '@element-plus/icons-vue'
import type { ToolCall } from '@/composables/useAgentChat'

const props = defineProps<{ toolCall: ToolCall }>()
const expanded = ref(false)

const argsPreview = computed(() => {
  try {
    const args = JSON.parse(props.toolCall.args)
    const str = JSON.stringify(args)
    return str.length > 60 ? str.substring(0, 60) + '...' : str
  } catch {
    return props.toolCall.args.substring(0, 60)
  }
})
</script>

<style scoped>
.tool-call-card {
  margin-top: 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  overflow: hidden;
  transition: border-color 0.2s;
}

.tool-call-card:hover {
  border-color: var(--border-default);
}

.tool-call-card.expanded {
  border-color: var(--border-default);
}

.tool-header {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 13px;
  padding: 10px 12px;
  transition: background 0.15s;
}

.tool-header:hover {
  background: rgba(0, 0, 0, 0.015);
}

.tool-status-icon.running { color: var(--color-warning); }
.tool-status-icon.done { color: var(--color-success); }
.tool-status-icon.error { color: var(--color-danger); }

.tool-name {
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 12px;
}

.tool-args-preview {
  flex: 1;
  color: var(--text-muted);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-mono);
}

.expand-icon {
  color: var(--text-muted);
  font-size: 12px;
}

.tool-body {
  padding: 0 12px 12px;
  border-top: 1px solid var(--border-subtle);
  padding-top: 12px;
}

.tool-section {
  margin-bottom: 10px;
}

.tool-section:last-child {
  margin-bottom: 0;
}

.section-label {
  font-size: 10px;
  color: var(--text-muted);
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 600;
}

.section-content {
  font-size: 12px;
  background: var(--color-surface-hover);
  padding: 10px 12px;
  border-radius: 5px;
  overflow-x: auto;
  max-height: 200px;
  margin: 0;
  font-family: var(--font-mono);
  color: var(--text-primary);
  line-height: 1.5;
  border: 1px solid var(--border-subtle);
}

/* ── Expand Transition ── */
.expand-enter-active,
.expand-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}

.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  max-height: 0;
}
</style>
