<template>
  <div class="exp-page">
    <div class="exp-header">
      <el-icon :size="24" color="#409eff"><Memo /></el-icon>
      <h2>经验沉淀</h2>
    </div>

    <!-- Tabs -->
    <div class="exp-tabs">
      <div
        v-for="t in TABS" :key="t.key"
        class="exp-tab" :class="{ 'exp-tab-on': activeTab === t.key }"
        @click="activeTab = t.key"
      >
        <el-icon :size="15"><component :is="t.icon" /></el-icon>
        {{ t.label }}
      </div>
    </div>

    <!-- Tab 内容 -->
    <div class="exp-content">

      <!-- ═══ 市场认知 ═══ -->
      <div v-if="activeTab === 'market'" class="tab-panel">
        <div v-if="marketLoading" class="panel-loading">
          <el-icon class="loading-spin" :size="24"><Loading /></el-icon>
          <span>加载中...</span>
        </div>
        <div v-else-if="!market || !market.cognition_text" class="panel-empty">
          <el-icon :size="40" color="#dadce0"><Monitor /></el-icon>
          <p>暂无市场认知数据</p>
        </div>
        <div v-else>
          <div class="panel-meta">
            <span>已追加 <strong>{{ market.append_count }}</strong> 次</span>
            <span v-if="market.updated_at" class="meta-time">
              <el-icon :size="13"><Clock /></el-icon>
              更新于 {{ formatTime(market.updated_at) }}
            </span>
          </div>
          <div class="content-card">
            <div class="markdown-body" v-html="renderMd(market.cognition_text)" />
          </div>
        </div>
      </div>

      <!-- ═══ 行业认知 ═══ -->
      <div v-if="activeTab === 'industry'" class="tab-panel">
        <div v-if="industriesLoading" class="panel-loading">
          <el-icon class="loading-spin" :size="24"><Loading /></el-icon>
          <span>加载中...</span>
        </div>
        <div v-else-if="!industries.length" class="panel-empty">
          <el-icon :size="40" color="#dadce0"><OfficeBuilding /></el-icon>
          <p>暂无行业认知数据</p>
        </div>
        <template v-else>
          <div class="sector-chips">
            <span
              v-for="ind in industries" :key="ind.sector"
              class="sector-chip"
              :class="{ 'sector-chip-on': selectedSector === ind.sector }"
              @click="selectSector(ind.sector)"
            >
              {{ ind.sector }}
              <span class="chip-count">{{ ind.append_count }}</span>
            </span>
          </div>
          <div v-if="industryLoading" class="panel-loading">
            <el-icon class="loading-spin" :size="24"><Loading /></el-icon>
          </div>
          <template v-else-if="activeIndustry">
            <div class="panel-meta">
              <span>行业：<strong>{{ activeIndustry.sector }}</strong></span>
              <span>已追加 <strong>{{ activeIndustry.append_count }}</strong> 次</span>
              <span v-if="activeIndustry.updated_at" class="meta-time">
                <el-icon :size="13"><Clock /></el-icon>
                更新于 {{ formatTime(activeIndustry.updated_at) }}
              </span>
            </div>
            <div class="content-card">
              <div class="markdown-body" v-html="renderMd(activeIndustry.cognition_text)" />
            </div>
          </template>
        </template>
      </div>

      <!-- ═══ 宏观报告 ═══ -->
      <div v-if="activeTab === 'macro'" class="tab-panel">
        <div v-if="reportsLoading" class="panel-loading">
          <el-icon class="loading-spin" :size="24"><Loading /></el-icon>
          <span>加载中...</span>
        </div>
        <div v-else-if="!reportVersions.length" class="panel-empty">
          <el-icon :size="40" color="#dadce0"><TrendCharts /></el-icon>
          <p>暂无宏观报告</p>
        </div>
        <template v-else>
          <div class="version-row">
            <span
              v-for="v in reportVersions" :key="v"
              class="version-chip"
              :class="{ 'version-chip-on': selectedVersion === v }"
              @click="selectVersion(v)"
            >v{{ v }}</span>
          </div>
          <div v-if="reportLoading" class="panel-loading">
            <el-icon class="loading-spin" :size="24"><Loading /></el-icon>
          </div>
          <template v-else-if="activeReport">
            <div class="panel-meta">
              <span>版本 <strong>v{{ activeReport.version }}</strong></span>
              <span v-if="activeReport.updated_at" class="meta-time">
                <el-icon :size="13"><Clock /></el-icon>
                生成于 {{ formatTime(activeReport.updated_at) }}
              </span>
            </div>
            <div v-if="activeReport.summary" class="summary-block">
              <div class="block-label">摘要</div>
              <div class="markdown-body" v-html="renderMd(activeReport.summary)" />
            </div>
            <div v-if="activeReport.changed_sections?.length" class="changes-block">
              <div class="block-label">变更章节</div>
              <div class="changes-tags">
                <el-tag
                  v-for="s in activeReport.changed_sections" :key="s"
                  size="small" type="info"
                >{{ s }}</el-tag>
              </div>
            </div>
            <div v-if="activeReport.content" class="content-card">
              <div class="markdown-body" v-html="renderMd(activeReport.content)" />
            </div>
          </template>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { marked } from 'marked'
import { sanitizeHtml } from '@/utils/sanitize'
import {
  Memo, Monitor, OfficeBuilding, TrendCharts, Loading, Clock,
} from '@element-plus/icons-vue'
import {
  fetchMarketCognition,
  fetchIndustryCognitions,
  fetchIndustryCognition,
  fetchMacroReports,
  fetchMacroReport,
} from '@/api/knowledge'
import type {
  MarketCognition,
  IndustryCognition,
  MacroReportSummary,
  MacroReport,
} from '@/types/knowledge'

marked.setOptions({ breaks: true, gfm: true })
function renderMd(text: string): string {
  if (!text) return ''
  try { return sanitizeHtml(marked.parse(text) as string) }
  catch { return text.replace(/</g, '&lt;') }
}

function formatTime(iso: string | null): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch { return iso.slice(0, 16).replace('T', ' ') }
}

const TABS = [
  { key: 'market', label: '市场认知', icon: Monitor },
  { key: 'industry', label: '行业认知', icon: OfficeBuilding },
  { key: 'macro', label: '宏观报告', icon: TrendCharts },
] as const

const activeTab = ref<string>('market')

// ── 市场认知 ──
const market = ref<MarketCognition | null>(null)
const marketLoading = ref(false)

// ── 行业认知 ──
const industries = ref<IndustryCognition[]>([])
const industriesLoading = ref(false)
const selectedSector = ref('')
const activeIndustry = ref<IndustryCognition | null>(null)
const industryLoading = ref(false)

// ── 宏观报告 ──
const reports = ref<MacroReportSummary[]>([])
const reportsLoading = ref(false)
const selectedVersion = ref<number | null>(null)
const activeReport = ref<MacroReport | null>(null)
const reportLoading = ref(false)
const reportVersions = computed(() => reports.value.map(r => r.version))

async function selectSector(sector: string) {
  selectedSector.value = sector
  industryLoading.value = true
  try { activeIndustry.value = await fetchIndustryCognition(sector) }
  catch { activeIndustry.value = null }
  finally { industryLoading.value = false }
}

async function selectVersion(v: number) {
  selectedVersion.value = v
  reportLoading.value = true
  try { activeReport.value = await fetchMacroReport(v) }
  catch { activeReport.value = null }
  finally { reportLoading.value = false }
}

onMounted(() => {
  marketLoading.value = true
  fetchMarketCognition()
    .then(d => { market.value = d })
    .catch(() => {})
    .finally(() => { marketLoading.value = false })

  industriesLoading.value = true
  fetchIndustryCognitions()
    .then(async list => {
      industries.value = list
      const first = list[0]
      if (first) await selectSector(first.sector)
    })
    .catch(() => {})
    .finally(() => { industriesLoading.value = false })

  reportsLoading.value = true
  fetchMacroReports()
    .then(async list => {
      reports.value = list
      const first = list[0]
      if (first) await selectVersion(first.version)
    })
    .catch(() => {})
    .finally(() => { reportsLoading.value = false })
})
</script>

<style scoped>
.exp-page {
  min-height: 100%;
  background: #fff;
  padding: 24px 32px 60px;
  max-width: 1100px;
  margin: 0 auto;
}

.exp-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 20px;
}

.exp-header h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  color: #202124;
}

/* ── Tabs ── */
.exp-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid #e0e0e0;
  margin-bottom: 24px;
}

.exp-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 20px 12px;
  font-size: 14px;
  color: #555;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.15s;
}

.exp-tab:hover { color: #1a73e8; }

.exp-tab-on {
  color: #1a73e8;
  font-weight: 500;
  border-bottom-color: #1a73e8;
}

/* ── Panel ── */
.tab-panel { min-height: 200px; }

.panel-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 60px 0;
  color: #999;
}

.panel-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 60px 0;
  color: #aaa;
}

.panel-empty p { margin: 0; font-size: 14px; }

.panel-meta {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 13px;
  color: #70757a;
  margin-bottom: 14px;
}

.panel-meta strong { color: #202124; }

.meta-time {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* ── Chips ── */
.sector-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.sector-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 14px;
  border-radius: 16px;
  font-size: 13px;
  color: #555;
  background: #f1f3f4;
  cursor: pointer;
  transition: all 0.15s;
  user-select: none;
}

.sector-chip:hover { background: #e8eaed; }

.sector-chip-on {
  background: #e8f0fe;
  color: #1a73e8;
  font-weight: 500;
}

.chip-count {
  font-size: 11px;
  color: #999;
}

.sector-chip-on .chip-count { color: #1a73e8; }

/* ── Version chips ── */
.version-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.version-chip {
  padding: 5px 12px;
  border-radius: 14px;
  font-size: 13px;
  color: #555;
  background: #f1f3f4;
  cursor: pointer;
  transition: all 0.15s;
  user-select: none;
}

.version-chip:hover { background: #e8eaed; }

.version-chip-on {
  background: #1a73e8;
  color: #fff;
  font-weight: 500;
}

/* ── Content card ── */
.content-card {
  background: #f8f9fa;
  border: 1px solid #e8eaed;
  border-radius: 10px;
  padding: 20px 24px;
  line-height: 1.75;
}

/* ── Summary & changes ── */
.summary-block {
  background: #f0f5ff;
  border: 1px solid #d4e4ff;
  border-radius: 8px;
  padding: 14px 18px;
  margin-bottom: 14px;
}

.block-label {
  font-size: 11px;
  font-weight: 600;
  color: #1a73e8;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}

.changes-block {
  margin-bottom: 14px;
}

.changes-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

/* ── Markdown ── */
.markdown-body :deep(p) { margin: 0 0 10px; }
.markdown-body :deep(p:last-child) { margin-bottom: 0; }
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) { margin: 16px 0 8px; font-weight: 600; color: #202124; }
.markdown-body :deep(h1) { font-size: 20px; }
.markdown-body :deep(h2) { font-size: 17px; }
.markdown-body :deep(h3) { font-size: 15px; }
.markdown-body :deep(ul),
.markdown-body :deep(ol) { padding-left: 20px; margin: 8px 0; }
.markdown-body :deep(li) { margin-bottom: 4px; }
.markdown-body :deep(code) {
  background: #e8eaed; padding: 2px 5px; border-radius: 3px;
  font-size: 13px; font-family: monospace;
}
.markdown-body :deep(pre) {
  background: #1e2430; color: #e0e0e0;
  padding: 12px 14px; border-radius: 6px;
  overflow-x: auto; margin: 10px 0;
}
.markdown-body :deep(pre code) { background: none; padding: 0; color: inherit; }
.markdown-body :deep(blockquote) {
  border-left: 3px solid #1a73e8; padding: 4px 12px;
  margin: 10px 0; color: #555; background: #f8f9ff;
  border-radius: 0 4px 4px 0;
}
.markdown-body :deep(table) {
  border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 13px;
}
.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid #dde3ea; padding: 6px 10px; text-align: left;
}
.markdown-body :deep(th) { background: #f0f3f7; font-weight: 600; }
.markdown-body :deep(a) { color: #1a73e8; }
.markdown-body :deep(hr) { border: none; border-top: 1px solid #e0e0e0; margin: 14px 0; }

.loading-spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
