<template>
  <div class="cron-panel">
    <!-- ══════ 无选中任务：任务列表 ══════ -->
    <template v-if="!selectedJob">
      <div class="panel-header">
        <h3>定时任务</h3>
        <button class="new-job-btn" @click="startCreate" title="新建任务">
          <el-icon><Plus /></el-icon>
        </button>
      </div>

      <div class="job-list">
        <div v-if="jobs.length === 0" class="empty-hint">暂无任务，点击 + 创建</div>
        <div
          v-for="job in jobs"
          :key="job.id"
          class="job-item"
          @click="selectJob(job)"
        >
          <div class="job-row">
            <span class="job-status-dot" :class="{ enabled: job.enabled }" />
            <span class="job-name">{{ job.name }}</span>
          </div>
          <div class="job-schedule">{{ scheduleLabel(job) }}</div>
          <div v-if="job.next_run_at" class="job-next">
            {{ formatRelative(job.next_run_at) }}
          </div>
        </div>
      </div>
    </template>

    <!-- ══════ 选中任务：任务详情 ══════ -->
    <template v-else>
      <div class="detail-header">
        <button class="back-btn" @click="backToList" title="返回列表">
          <el-icon><ArrowLeft /></el-icon>
        </button>
        <span class="detail-title">{{ selectedJob.name }}</span>
        <div class="detail-actions">
          <button class="icon-btn" @click.stop="triggerRun(selectedJob)" title="立即运行">
            <el-icon><VideoPlay /></el-icon>
          </button>
          <button class="icon-btn" @click.stop="startEdit(selectedJob)" title="编辑">
            <el-icon><EditPen /></el-icon>
          </button>
          <button class="icon-btn danger" @click.stop="confirmDelete(selectedJob)" title="删除">
            <el-icon><Delete /></el-icon>
          </button>
        </div>
      </div>

      <div class="detail-meta">
        <div class="meta-row">
          <span class="meta-label">调度</span>
          <span class="meta-value mono">{{ scheduleLabel(selectedJob) }}</span>
        </div>
        <div class="meta-row">
          <span class="meta-label">状态</span>
          <el-switch
            :model-value="selectedJob.enabled"
            size="small"
            @change="(v: boolean) => toggleEnabled(selectedJob, v)"
          />
        </div>
        <div class="meta-row prompt-row">
          <span class="meta-label">Prompt</span>
          <span class="meta-value prompt-text">{{ selectedJob.prompt }}</span>
        </div>
      </div>

      <div class="runs-section">
        <div class="runs-header">
          <span>运行历史 ({{ runs.length }})</span>
          <button class="refresh-btn" @click="loadRuns(selectedJob.id)" title="刷新">
            <el-icon :size="13"><Refresh /></el-icon>
          </button>
        </div>

        <div v-if="runs.length === 0" class="no-runs">暂无运行记录</div>
        <div
          v-for="run in runs"
          :key="run.id"
          :class="['run-item', { selected: selectedRunId === run.id }]"
          @click="selectRun(run)"
        >
          <span class="run-dot" :class="run.status" />
          <div class="run-info">
            <span class="run-time">{{ formatTime(run.started_at) }}</span>
            <span class="run-status" :class="run.status">{{ statusText(run.status) }}</span>
          </div>
        </div>
      </div>
    </template>

    <!-- ══════ 创建 / 编辑对话框 ══════ -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingJob ? '编辑任务' : '新建任务'"
      width="520px"
      destroy-on-close
      :close-on-click-modal="false"
    >
      <el-form :model="form" label-position="top">
        <el-form-item label="任务名称">
          <el-input v-model="form.name" placeholder="例如：每日市场报告" maxlength="100" />
        </el-form-item>
        <el-form-item label="调度规则">
          <SchedulePicker v-model="form.schedule" />
        </el-form-item>
        <el-form-item label="Prompt">
          <el-input
            v-model="form.prompt"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 10 }"
            placeholder="定时触发时执行的 prompt..."
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveJob" :loading="saving">
          {{ editingJob ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'CronPanel' })

import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { showApiError } from '@/utils/notify'
import {
  Plus, ArrowLeft, EditPen, Delete, VideoPlay, Refresh,
} from '@element-plus/icons-vue'
import SchedulePicker from './SchedulePicker.vue'
import { cronApi } from '@/api/cron'
import type { CronJob, CronJobRun, ContextMessage } from '@/types/cron'

const emit = defineEmits<{
  (e: 'job-select', job: CronJob): void
  (e: 'run-select', run: CronJobRun, messages: ContextMessage[]): void
  (e: 'continue-conversation', job: CronJob): void
}>()

// ── State ──
const jobs = ref<CronJob[]>([])
const selectedJob = ref<CronJob | null>(null)
const runs = ref<CronJobRun[]>([])
const selectedRunId = ref<string | null>(null)
const runContextMessages = ref<ContextMessage[]>([])

const dialogVisible = ref(false)
const editingJob = ref<CronJob | null>(null)
const saving = ref(false)
const form = ref({ name: '', schedule: '', prompt: '' })

// ── Helpers ──
function scheduleLabel(job: CronJob | null): string {
  if (!job) return ''
  if (job.schedule_type === 'oneshot') return `一次性: ${job.schedule}`
  if (job.schedule_type === 'interval') return `间隔: ${job.schedule}`
  return `Cron: ${job.schedule}`
}

function formatTime(iso: string): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', {
      month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    })
  } catch { return iso }
}

function formatRelative(iso: string): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    const now = Date.now()
    const diff = d.getTime() - now
    if (diff < 0) return '已过期'
    const mins = Math.floor(diff / 60000)
    if (mins < 60) return `${mins} 分钟后`
    const hours = Math.floor(mins / 60)
    if (hours < 24) return `${hours} 小时后`
    return `${Math.floor(hours / 24)} 天后`
  } catch { return iso }
}

function statusText(s: string): string {
  const map: Record<string, string> = {
    running: '运行中', completed: '完成', failed: '失败',
  }
  return map[s] || s
}

// ── Data Loading ──
async function loadJobs() {
  try {
    const { data } = await cronApi.listJobs()
    jobs.value = data.jobs
  } catch { /* ignore */ }
}

async function loadRuns(jobId: string) {
  try {
    const { data } = await cronApi.listRuns(jobId)
    runs.value = data.runs
  } catch {
    runs.value = []
  }
}

async function loadRunContext(run: CronJobRun) {
  selectedRunId.value = run.id
  if (run.context_file) {
    try {
      const { data } = await cronApi.getRunContext(run.id)
      runContextMessages.value = data.messages
    } catch {
      runContextMessages.value = []
    }
  } else {
    runContextMessages.value = []
  }
  emit('run-select', run, runContextMessages.value)
}

// ── Job Actions ──
function selectJob(job: CronJob) {
  selectedJob.value = job
  selectedRunId.value = null
  runs.value = []
  runContextMessages.value = []
  loadRuns(job.id)
  emit('job-select', job)
}

function backToList() {
  selectedJob.value = null
  selectedRunId.value = null
  runs.value = []
  runContextMessages.value = []
}

async function toggleEnabled(job: CronJob | null, val: boolean) {
  if (!job) return
  try {
    await cronApi.updateJob(job.id, { enabled: val })
    job.enabled = val
  } catch (err) {
    showApiError(err, '操作失败')
  }
}

async function triggerRun(job: CronJob) {
  try {
    await cronApi.triggerJob(job.id)
    ElMessage.success('任务已触发')
    setTimeout(async () => {
      await loadRuns(job.id)
      await loadJobs()
    }, 2000)
  } catch (e: any) {
    showApiError(e, '触发失败')
  }
}

async function confirmDelete(job: CronJob) {
  try {
    await ElMessageBox.confirm(`确定删除任务"${job.name}"？`, '确认删除', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch { return }
  try {
    await cronApi.deleteJob(job.id)
    ElMessage.success('已删除')
    if (selectedJob.value?.id === job.id) {
      selectedJob.value = null
    }
    await loadJobs()
  } catch (err) {
    showApiError(err, '删除失败')
  }
}

// ── Create / Edit ──
function startCreate() {
  editingJob.value = null
  form.value = { name: '', schedule: '', prompt: '' }
  dialogVisible.value = true
}

function startEdit(job: CronJob) {
  editingJob.value = job
  form.value = { name: job.name, schedule: job.schedule, prompt: job.prompt }
  dialogVisible.value = true
}

async function saveJob() {
  if (!form.value.name.trim()) { ElMessage.warning('请输入任务名称'); return }
  if (!form.value.schedule.trim()) { ElMessage.warning('请输入调度规则'); return }
  if (!form.value.prompt.trim()) { ElMessage.warning('请输入 Prompt'); return }
  saving.value = true
  try {
    if (editingJob.value) {
      await cronApi.updateJob(editingJob.value.id, {
        name: form.value.name, schedule: form.value.schedule, prompt: form.value.prompt,
      })
      ElMessage.success('已更新')
      if (selectedJob.value?.id === editingJob.value.id) {
        selectedJob.value = { ...selectedJob.value, name: form.value.name, schedule: form.value.schedule, prompt: form.value.prompt }
      }
    } else {
      await cronApi.createJob({
        name: form.value.name, schedule: form.value.schedule, prompt: form.value.prompt,
      })
      ElMessage.success('已创建')
    }
    dialogVisible.value = false
    await loadJobs()
  } catch (e: any) {
    showApiError(e, '操作失败')
  } finally {
    saving.value = false
  }
}

function selectRun(run: CronJobRun) {
  loadRunContext(run)
}

function handleContinueConversation() {
  if (!selectedJob.value) return
  emit('continue-conversation', selectedJob.value)
}

// ── External: handle cron WebSocket events ──
function handleCronEvent(event: string, data: Record<string, unknown>) {
  const jobId = data.job_id as string
  if (!jobId) return

  if (event === 'cron_job_created' || event === 'cron_job_updated') {
    loadJobs()
  } else if (event === 'cron_job_deleted') {
    jobs.value = jobs.value.filter(j => j.id !== jobId)
    if (selectedJob.value?.id === jobId) {
      selectedJob.value = null
    }
  } else if (['cron_run_completed', 'cron_run_failed', 'cron_run_started'].includes(event)) {
    loadJobs()
    if (selectedJob.value?.id === jobId) {
      loadRuns(jobId)
    }
  }
}

defineExpose({ handleCronEvent })

onMounted(() => {
  loadJobs()
})
</script>

<style scoped>
.cron-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* ── Header ── */
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border-subtle, #e0ddd6);
}

.panel-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  font-family: var(--font-display);
}

.new-job-btn {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  border: none;
  background: var(--color-accent, #b08d47);
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  transition: all 0.15s;
}

.new-job-btn:hover { opacity: 0.85; }

/* ── Job List ── */
.job-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.empty-hint {
  text-align: center;
  padding: 24px 16px;
  font-size: 13px;
  color: var(--text-muted, #999);
}

.job-item {
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 4px;
  transition: all 0.15s;
  border: 1px solid transparent;
}

.job-item:hover {
  background: rgba(0, 0, 0, 0.03);
}

.job-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.job-status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text-muted, #999);
  flex-shrink: 0;
}

.job-status-dot.enabled {
  background: var(--color-success, #27ae60);
  box-shadow: 0 0 5px rgba(39, 174, 96, 0.4);
}

.job-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #1a1a1a);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

.job-schedule {
  font-size: 11px;
  color: var(--text-muted, #999);
  margin-top: 3px;
  padding-left: 15px;
  font-family: var(--font-mono, monospace);
}

.job-next {
  font-size: 11px;
  color: var(--color-accent, #b08d47);
  margin-top: 1px;
  padding-left: 15px;
}

/* ── Detail Header ── */
.detail-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border-subtle, #e0ddd6);
}

.back-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 1px solid var(--border-subtle, #e0ddd6);
  background: var(--color-input-bg);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary, #666);
  transition: all 0.12s;
  flex-shrink: 0;
}

.back-btn:hover {
  background: rgba(0, 0, 0, 0.04);
  color: var(--text-primary);
}

.detail-title {
  flex: 1;
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.detail-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.icon-btn {
  width: 26px;
  height: 26px;
  border-radius: 6px;
  border: none;
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted, #999);
  font-size: 13px;
  transition: all 0.12s;
}

.icon-btn:hover {
  background: rgba(0, 0, 0, 0.06);
  color: var(--text-primary);
}

.icon-btn.danger:hover {
  color: #e74c3c;
  background: #fef0ef;
}

/* ── Detail Meta ── */
.detail-meta {
  padding: 12px 14px;
  border-bottom: 1px solid var(--border-subtle, #e0ddd6);
}

.meta-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 0;
  font-size: 12px;
}

.meta-label {
  color: var(--text-muted, #999);
  min-width: 40px;
  flex-shrink: 0;
}

.meta-value {
  color: var(--text-primary, #1a1a1a);
  min-width: 0;
}

.meta-value.mono {
  font-family: var(--font-mono, monospace);
  font-size: 11px;
}

.prompt-row {
  align-items: flex-start;
}

.prompt-text {
  font-size: 11px;
  line-height: 1.4;
  word-break: break-all;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ── Runs Section ── */
.runs-section {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.runs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted, #999);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 1px solid var(--border-subtle, #e0ddd6);
}

.refresh-btn {
  width: 22px;
  height: 22px;
  border-radius: 4px;
  border: none;
  background: transparent;
  cursor: pointer;
  color: var(--text-muted, #999);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.12s;
}

.refresh-btn:hover {
  background: rgba(0, 0, 0, 0.04);
  color: var(--text-primary);
}

.no-runs {
  padding: 20px 14px;
  font-size: 12px;
  color: var(--text-muted, #999);
  text-align: center;
}

.run-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 14px;
  cursor: pointer;
  border-bottom: 1px solid var(--border-subtle, #e0ddd6);
  transition: all 0.12s;
}

.run-item:hover {
  background: rgba(0, 0, 0, 0.02);
}

.run-item.selected {
  background: var(--color-accent-subtle, #f5f0e5);
  border-left: 3px solid var(--color-accent, #b08d47);
}

.run-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.run-dot.completed { background: var(--color-success, #27ae60); }
.run-dot.failed { background: #e74c3c; }
.run-dot.running { background: #1976d2; }

.run-info {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.run-time {
  font-size: 12px;
  color: var(--text-primary, #1a1a1a);
}

.run-status {
  font-size: 11px;
  color: var(--text-muted, #999);
}

.run-status.completed { color: var(--color-success, #27ae60); }
.run-status.failed { color: #e74c3c; }
.run-status.running { color: #1976d2; }
</style>
