<template>
  <div class="subagent-card" :class="[status, { expanded }]">
    <!-- 头部：点击展开/折叠 -->
    <div class="subagent-header" @click="expanded = !expanded">
      <div class="subagent-status-icon">
        <div v-if="status === 'running'" class="spinner"></div>
        <el-icon v-else-if="status === 'completed'" class="status-done"><SuccessFilled /></el-icon>
        <el-icon v-else class="status-error"><CircleCloseFilled /></el-icon>
      </div>
      <div class="subagent-info">
        <span class="subagent-type">{{ typeLabel }}</span>
        <span class="subagent-desc">{{ subagent.task_description || '子任务' }}</span>
      </div>
      <el-icon class="expand-icon">
        <ArrowUp v-if="expanded" />
        <ArrowDown v-else />
      </el-icon>
    </div>

    <!-- 展开的内容 -->
    <transition name="slide">
      <div v-show="expanded" class="subagent-body">
        <!-- 子 agent 的工具调用 -->
        <div v-if="subagent.toolCalls?.length" class="subagent-section">
          <div class="section-label">执行过程</div>
          <div class="tool-list">
            <div v-for="tc in subagent.toolCalls" :key="tc.id" class="mini-tool">
              <el-icon :class="tc.status">
                <Loading v-if="tc.status === 'running'" />
                <SuccessFilled v-else-if="tc.status === 'done'" />
                <CircleCloseFilled v-else />
              </el-icon>
              <span class="tool-name">{{ tc.name }}</span>
              <span class="tool-args">{{ formatArgs(tc.args) }}</span>
            </div>
          </div>
        </div>

        <!-- 子 agent 的输出 -->
        <div v-if="subagent.output" class="subagent-section">
          <div class="section-label">输出结果</div>
          <pre class="subagent-output">{{ subagent.output }}</pre>
        </div>

        <!-- 运行中但无内容 -->
        <div v-if="status === 'running' && !subagent.toolCalls?.length && !subagent.output" class="subagent-section">
          <div class="thinking-hint">
            <span class="dot"></span><span class="dot"></span><span class="dot"></span>
            <span>子 Agent 正在工作...</span>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { SuccessFilled, CircleCloseFilled, ArrowDown, ArrowUp, Loading } from '@element-plus/icons-vue'
import type { SubAgentInfo, ToolCall } from '@/composables/useAgentChat'

const props = defineProps<{
  subagent: SubAgentInfo
}>()

const expanded = ref(false)

const status = computed(() => props.subagent.status || 'running')

const typeLabel = computed(() => {
  const typeMap: Record<string, string> = {
    'general-purpose': '通用助手',
    'explore': '代码探索',
    'plan': '方案规划',
    'researcher': '研究分析',
  }
  const type = props.subagent.type || ''
  return typeMap[type] || props.subagent.label || '子 Agent'
})

function formatArgs(args: string): string {
  try {
    const parsed = JSON.parse(args)
    // 取第一个有意义的参数值作为预览
    for (const key of ['command', 'query', 'path', 'pattern', 'task', 'prompt']) {
      if (parsed[key]) {
        const v = String(parsed[key])
        return v.length > 50 ? v.substring(0, 50) + '...' : v
      }
    }
    const str = JSON.stringify(parsed)
    return str.length > 50 ? str.substring(0, 50) + '...' : str
  } catch {
    return args.substring(0, 50)
  }
}
</script>

<style scoped>
.subagent-card {
  margin-top: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  background: var(--color-surface);
  overflow: hidden;
  transition: all 0.2s;
}

.subagent-card.running {
  border-color: var(--color-accent);
  border-style: dashed;
}

.subagent-card.completed {
  border-color: var(--border-default);
}

.subagent-card.error {
  border-color: var(--color-danger);
}

.subagent-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  cursor: pointer;
  transition: background 0.15s;
}

.subagent-header:hover {
  background: rgba(0, 0, 0, 0.02);
}

.subagent-status-icon {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--border-subtle);
  border-top-color: var(--color-accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.status-done { color: var(--color-success); font-size: 16px; }
.status-error { color: var(--color-danger); font-size: 16px; }

.subagent-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.subagent-type {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-accent);
  font-family: var(--font-display);
}

.subagent-desc {
  font-size: 13px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.expand-icon {
  color: var(--text-muted);
  font-size: 14px;
  flex-shrink: 0;
}

/* ─── 展开内容 ─── */
.subagent-body {
  padding: 0 14px 14px;
  border-top: 1px solid var(--border-subtle);
}

.subagent-section {
  margin-top: 12px;
}

.section-label {
  font-size: 10px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 600;
  margin-bottom: 6px;
}

.tool-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.mini-tool {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  padding: 4px 8px;
  background: var(--color-surface-hover);
  border-radius: 6px;
}

.mini-tool .el-icon {
  font-size: 12px;
}

.mini-tool .el-icon.running { color: var(--color-warning); }
.mini-tool .el-icon.done { color: var(--color-success); }
.mini-tool .el-icon.error { color: var(--color-danger); }

.mini-tool .tool-name {
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-mono);
}

.mini-tool .tool-args {
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.subagent-output {
  font-size: 12px;
  background: var(--color-surface-hover);
  padding: 10px 12px;
  border-radius: 6px;
  max-height: 200px;
  overflow-y: auto;
  margin: 0;
  font-family: var(--font-mono);
  color: var(--text-primary);
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  border: 1px solid var(--border-subtle);
}

.thinking-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-muted);
  padding: 4px 0;
}

.thinking-hint .dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--color-accent);
  opacity: 0.4;
  animation: pulse 1.4s infinite ease-in-out;
}

.thinking-hint .dot:nth-child(2) { animation-delay: 0.2s; }
.thinking-hint .dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes pulse {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-4px); opacity: 1; }
}

/* ─── 展开动画 ─── */
.slide-enter-active,
.slide-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  max-height: 0;
}
</style>
