<template>
  <div class="schedule-picker">
    <!-- 模式选择 -->
    <div class="mode-tabs">
      <button
        type="button"
        v-for="m in modes"
        :key="m.key"
        :class="['mode-btn', { active: mode === m.key }]"
        @click="selectMode(m.key)"
      >
        <span class="mode-icon" v-html="m.icon"></span>
        <span>{{ m.label }}</span>
      </button>
    </div>

    <!-- 间隔模式 -->
    <template v-if="mode === 'interval'">
      <div class="field-row">
        <span class="field-label">每隔</span>
        <el-input-number v-model="intervalValue" :min="1" :max="1440" controls-position="right" style="width: 90px" />
        <el-select v-model="intervalUnit" style="width: 80px">
          <el-option label="分钟" value="m" />
          <el-option label="小时" value="h" />
          <el-option label="天" value="d" />
        </el-select>
        <span class="field-hint">执行一次</span>
      </div>
    </template>

    <!-- 每天模式 -->
    <template v-if="mode === 'daily'">
      <div class="field-row">
        <span class="field-label">每天</span>
        <el-time-picker
          v-model="dailyTime"
          format="HH:mm"
          value-format="HH:mm"
          placeholder="选择时间"
          style="width: 140px"
        />
        <span class="field-hint">执行</span>
      </div>
      <div v-if="dailyTime" class="preview-tag">生成规则: {{ dailyPreview }}</div>
    </template>

    <!-- 每周模式 — 可视化选日期 -->
    <template v-if="mode === 'weekly'">
      <div class="weekday-picker">
        <span class="field-label">选择星期</span>
        <div class="weekday-grid">
          <button
            type="button"
            v-for="d in weekDays"
            :key="d.value"
            :class="['weekday-chip', { active: weeklyDays.includes(d.value) }]"
            @click="toggleWeekDay(d.value)"
          >
            {{ d.label }}
          </button>
        </div>
      </div>
      <div class="field-row" style="margin-top: 12px">
        <span class="field-label">在</span>
        <el-time-picker
          v-model="weeklyTime"
          format="HH:mm"
          value-format="HH:mm"
          placeholder="选择时间"
          style="width: 140px"
        />
        <span class="field-hint">执行</span>
      </div>
      <div v-if="weeklyDays.length && weeklyTime" class="preview-tag">生成规则: {{ weeklyPreview }}</div>
    </template>

    <!-- 每月模式 -->
    <template v-if="mode === 'monthly'">
      <div class="field-row">
        <span class="field-label">每月</span>
        <el-select v-model="monthlyDays" multiple collapse-tags style="width: 200px" placeholder="选择日期">
          <el-option v-for="d in monthlyDayOptions" :key="d.value" :label="d.label" :value="d.value" />
        </el-select>
        <span class="field-label">在</span>
        <el-time-picker v-model="monthlyTime" format="HH:mm" value-format="HH:mm" placeholder="时间" style="width: 140px" />
      </div>
      <div v-if="monthlyDays.length && monthlyTime" class="preview-tag">生成规则: {{ monthlyPreview }}</div>
    </template>

    <!-- 一次性模式 -->
    <template v-if="mode === 'oneshot'">
      <div class="field-row">
        <el-date-picker
          v-model="oneshotDate"
          type="datetime"
          placeholder="选择日期和时间"
          format="YYYY-MM-DD HH:mm"
          value-format="YYYY-MM-DDTHH:mm"
          style="width: 240px"
        />
      </div>
    </template>

    <!-- 高级模式 — Cron 表达式 -->
    <template v-if="mode === 'advanced'">
      <div class="cron-presets">
        <span class="section-label">快捷选择</span>
        <div class="preset-grid">
          <button
            type="button"
            v-for="p in cronPresets"
            :key="p.value"
            :class="['preset-chip', { active: cronPreset === p.value }]"
            @click="selectCronPreset(p.value)"
          >
            {{ p.label }}
          </button>
        </div>
      </div>
      <div class="cron-custom">
        <span class="section-label">自定义 Cron 表达式</span>
        <el-input
          v-model="cronExpr"
          placeholder="分 时 日 月 周 — 例如 0 9 * * 1-5"
          :class="{ invalid: cronExpr && !cronValid }"
        />
        <span v-if="cronExpr && cronValid" class="cron-desc">{{ cronDescription }}</span>
        <span v-if="cronExpr && !cronValid" class="cron-error">格式应为 5 个字段，空格分隔</span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

defineOptions({ name: 'SchedulePicker' })

const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: string): void }>()

const modes = [
  { key: 'interval', label: '间隔', icon: '&#8635;' },
  { key: 'daily',   label: '每天', icon: '&#9788;' },
  { key: 'weekly',  label: '每周', icon: '&#128197;' },
    { key: 'monthly', label: '每月', icon: '&#128198;' },
  { key: 'oneshot', label: '一次性', icon: '&#9200;' },
  { key: 'advanced', label: '高级', icon: '&#9881;' },
]

type Mode = 'interval' | 'daily' | 'weekly' | 'monthly' | 'oneshot' | 'advanced'
const mode = ref<Mode>('interval')

// interval
const intervalValue = ref(30)
const intervalUnit  = ref<'m' | 'h' | 'd'>('m')

// daily
const dailyTime = ref('')

// weekly
const weekDays = [
  { label: '一', value: 1 }, { label: '二', value: 2 }, { label: '三', value: 3 },
  { label: '四', value: 4 }, { label: '五', value: 5 }, { label: '六', value: 6 }, { label: '日', value: 0 },
]
const weeklyDays = ref<number[]>([])
const weeklyTime = ref('')

// monthly
const monthlyDays = ref<number[]>([])
const monthlyTime = ref("")
const monthlyDayOptions = [
  ...Array.from({ length: 31 }, (_, i) => ({ label: `${i + 1}号`, value: i + 1 })),
]

// oneshot
const oneshotDate = ref('')

// advanced cron
const cronExpr   = ref('')
const cronPreset = ref('')

const cronPresets = [
  { label: '每分钟', value: '* * * * *' },
  { label: '每5分钟', value: '*/5 * * * *' },
  { label: '每15分钟', value: '*/15 * * * *' },
  { label: '每30分钟', value: '*/30 * * * *' },
  { label: '整点', value: '0 * * * *' },
  { label: '工作日 9:00', value: '0 9 * * 1-5' },
  { label: '工作日 15:00', value: '0 15 * * 1-5' },
  { label: '每月1号 9:00', value: '0 9 1 * *' },
  { label: '每小时第5分', value: '5 * * * *' },
]

function parseHourMinute(value: string): [string, string] | null {
  const [h, m] = value.split(':')
  if (h === undefined || m === undefined) return null
  return [h, m]
}

// ── 预览 ──
const dailyPreview = computed(() => {
  if (!dailyTime.value) return ''
  const parsed = parseHourMinute(dailyTime.value)
  if (!parsed) return ''
  const [h, m] = parsed
  return `${parseInt(h)} 点 ${parseInt(m)} 分 · 每天执行一次`
})

const weeklyPreview = computed(() => {
  if (!weeklyTime.value || !weeklyDays.value.length) return ''
  const names = weeklyDays.value
    .map(v => weekDays.find(d => d.value === v)?.label)
    .filter((label): label is string => Boolean(label))
    .join('、')
  const parsed = parseHourMinute(weeklyTime.value)
  if (!parsed) return ''
  const [h, m] = parsed
  return `每${names} ${parseInt(h)}:${m.padStart(2, '0')} · 共 ${weeklyDays.value.length} 天`
})

const monthlyPreview = computed(() => {
  if (!monthlyTime.value || !monthlyDays.value.length) return ""
  const parsed = parseHourMinute(monthlyTime.value)
  if (!parsed) return ""
  const [h, m] = parsed
  const days = monthlyDays.value
    .sort((a, b) => a - b)
    .map(d => `${d}号`).join("、")
  return `每月${days} ${parseInt(h)}:${m.padStart(2, "0")} · 共 ${monthlyDays.value.length} 天`
})

// ── 生成最终值 ──
function buildValue(): string {
  if (mode.value === 'interval') return `${intervalValue.value}${intervalUnit.value}`
  if (mode.value === 'daily' && dailyTime.value) {
    const parsed = parseHourMinute(dailyTime.value)
    if (!parsed) return ''
    const [h, m] = parsed
    return `${parseInt(m)} ${parseInt(h)} * * *`
  }
  if (mode.value === 'monthly' && monthlyDays.value.length && monthlyTime.value) {
    const parsed = parseHourMinute(monthlyTime.value)
    if (!parsed) return ''
    const [hm, mm] = parsed
    const days = monthlyDays.value.sort((a, b) => a - b).join(',')
    return `${parseInt(mm)} ${parseInt(hm)} ${days} * *`
  }
  if (mode.value === 'weekly' && weeklyDays.value.length && weeklyTime.value) {
    const parsed = parseHourMinute(weeklyTime.value)
    if (!parsed) return ''
    const [h, m] = parsed
    const days = weeklyDays.value.sort((a, b) => a - b).join(',')
    return `${parseInt(m)} ${parseInt(h)} * * ${days}`
  }
  if (mode.value === 'oneshot') return oneshotDate.value
  if (mode.value === 'advanced') return cronExpr.value
  return ''
}

const cronValid = computed(() => {
  if (!cronExpr.value) return true
  return cronExpr.value.trim().split(/\s+/).length === 5
})

const cronDescription = computed(() => {
  return cronExpr.value && cronValid.value ? cronExpr.value : ''
})

// ── 事件 ──
function selectMode(m: string) { mode.value = m as Mode; emitCurrent() }
function toggleWeekDay(v: number) {
  const idx = weeklyDays.value.indexOf(v)
  if (idx >= 0) weeklyDays.value.splice(idx, 1)
  else weeklyDays.value.push(v)
  emitCurrent()
}
function selectCronPreset(value: string) {
  cronPreset.value = value
  cronExpr.value = value
  emitCurrent()
}
function emitCurrent() {
  const v = buildValue()
  if (v) emit('update:modelValue', v)
}

watch([intervalValue, intervalUnit], () => { if (mode.value === 'interval') emitCurrent() })
watch(dailyTime, () => { if (mode.value === 'daily' && dailyTime.value) emitCurrent() })
watch([monthlyDays, monthlyTime], () => { if (mode.value === "monthly") emitCurrent() }, { deep: true })
watch([weeklyDays, weeklyTime], () => { if (mode.value === 'weekly') emitCurrent() }, { deep: true })
watch(oneshotDate, () => { if (mode.value === 'oneshot' && oneshotDate.value) emitCurrent() })
watch(cronExpr, () => { cronPreset.value = ''; if (mode.value === 'advanced') emitCurrent() })

// ── 初始化 ──
function initFromValue(val: string) {
  if (!val) return
  const v = val.trim()
  // oneshot
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(v)) {
    mode.value = 'oneshot'; oneshotDate.value = v; return
  }
  // interval
  const im = v.match(/^(\d+)\s*(m|h|d)$/i)
  if (im) {
    mode.value = 'interval'
    const amount = im[1]
    const unit = im[2]
    if (!amount || !unit) return
    intervalValue.value = parseInt(amount)
    intervalUnit.value = unit.toLowerCase() as 'm' | 'h' | 'd'
    return
  }
  // cron — try to decompose into high-level modes
  const parts = v.split(/\s+/)
  if (parts.length === 5) {
    const [minute, hour, day, month, weekday] = parts as [string, string, string, string, string]
    // daily: "mm HH * * *"
    if (day === '*' && month === '*' && weekday === '*') {
      mode.value = 'daily'
      dailyTime.value = `${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`
      return
    }
    // monthly: "mm HH day1,day2,... * *"
    if (month === '*' && weekday === '*') {
      const days = day.split(',').map(Number).filter(n => !isNaN(n))
      if (days.length) {
        mode.value = 'monthly'
        monthlyDays.value = days
        monthlyTime.value = `${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`
        return
      }
    }
    if (day === '*' && month === '*') {
      const days = weekday.split(',').map(Number).filter(n => !isNaN(n))
      if (days.length) {
        mode.value = 'weekly'
        weeklyDays.value = days
        weeklyTime.value = `${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`
        return
      }
    }
  }
  // fallback to advanced
  mode.value = 'advanced'
  cronExpr.value = v
  const preset = cronPresets.find(p => p.value === v)
  if (preset) cronPreset.value = preset.value
}

initFromValue(props.modelValue)
</script>

<style scoped>
.schedule-picker {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ── 模式切换 ── */
.mode-tabs {
  display: flex;
  gap: 2px;
  background: #f2f2f3;
  border-radius: 10px;
  padding: 3px;
}

.mode-btn {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 8px 0 6px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-muted, #959595);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  font-family: var(--font-display);
  line-height: 1;
}

.mode-btn:hover { color: var(--text-secondary); }

.mode-btn.active {
  background: var(--color-input-bg);
  color: var(--text-primary, #1a1a1a);
  box-shadow: 0 1px 3px rgba(0,0,0,.06);
}

.mode-icon { font-size: 16px; line-height: 1; }

/* ── 通用 ── */
.field-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.field-label {
  font-size: 13px;
  color: var(--text-secondary, #666);
  white-space: nowrap;
}

.field-hint {
  font-size: 13px;
  color: var(--text-muted, #959595);
}

.preview-tag {
  font-size: 12px;
  color: #27ae60;
  background: #edfaf1;
  padding: 5px 10px;
  border-radius: 6px;
  font-weight: 500;
}

/* ── 每周日期选择 ── */
.weekday-picker { display: flex; flex-direction: column; gap: 10px; }

.weekday-grid {
  display: flex;
  gap: 6px;
}

.weekday-chip {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 2px solid var(--border-subtle, #e0ddd6);
  background: var(--color-input-bg);
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary, #666);
  cursor: pointer;
  transition: all 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.weekday-chip:hover {
  border-color: var(--color-accent, #b08d47);
  color: var(--color-accent, #b08d47);
}

.weekday-chip.active {
  background: var(--color-accent, #b08d47);
  border-color: var(--color-accent, #b08d47);
  color: white;
}

/* ── 高级 Cron ── */
.section-label {
  display: block;
  font-size: 12px;
  color: var(--text-muted, #999);
  margin-bottom: 8px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.preset-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
  margin-bottom: 4px;
}

.preset-chip {
  padding: 6px 8px;
  border-radius: 6px;
  border: 1px solid var(--border-subtle, #e0ddd6);
  background: var(--color-input-bg);
  font-size: 12px;
  color: var(--text-secondary, #666);
  cursor: pointer;
  text-align: center;
  transition: all 0.12s;
  white-space: nowrap;
}

.preset-chip:hover {
  border-color: var(--color-accent, #b08d47);
  color: var(--color-accent, #b08d47);
}

.preset-chip.active {
  background: var(--color-accent-subtle, #f5f0e5);
  border-color: var(--color-accent, #b08d47);
  color: var(--color-accent, #b08d47);
  font-weight: 600;
}

.cron-custom { margin-top: 8px; }

.cron-desc {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: #27ae60;
  font-family: var(--font-mono);
}

.cron-error {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: #d32f2f;
}
</style>
