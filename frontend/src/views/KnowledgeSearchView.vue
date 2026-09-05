<template>
  <div class="kb-search-page" :class="{ 'has-results': hasSearched || loading }">

    <!-- ════ 初始状态：居中搜索 ════ -->
    <div v-if="!hasSearched && !loading" class="landing">
      <div class="landing-inner">
        <div class="landing-logo">
          <el-icon :size="36" color="#409eff"><Reading /></el-icon>
          <h1>知识库</h1>
        </div>

        <!-- 搜索框 -->
        <div class="search-pill">
          <el-icon class="search-pill-icon" :size="20"><Search /></el-icon>
          <input
            v-model="query"
            class="search-pill-input"
            placeholder="搜索原始信息、分析报告、复盘、知识节点..."
            @keyup.enter="doSearch"
          />
          <el-dropdown trigger="click" @visible-change="() => {}">
            <button class="search-pill-filter" title="数据范围">
              <el-icon :size="16"><Filter /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-for="t in TABLE_OPTIONS" :key="t.value"
                  :divided="t.value === 'all'"
                  @click="toggleTable(t.value)"
                >
                  <span class="dd-item">
                    <el-checkbox
                      :model-value="t.value === 'all' ? true : selectedTables.includes(t.value as KBTableName)"
                      :disabled="t.value === 'all'" size="small"
                    />
                    <span class="dd-dot" :style="{ background: t.color }" />
                    {{ t.label }}
                  </span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <button class="search-pill-btn" :class="{ 'is-loading': loading }" @click="doSearch">
            <el-icon v-if="!loading" :size="18"><Search /></el-icon>
            <el-icon v-else class="loading-spin" :size="18"><Loading /></el-icon>
          </button>
        </div>

        <!-- 过滤 chips -->
        <div class="landing-chips">
          <span
            v-for="t in ALL_TABLES" :key="t"
            class="chip" :class="{ 'chip-on': selectedTables.includes(t) }"
            @click="toggleTable(t)"
          >
            <span class="chip-dot" :style="{ background: KB_TABLE_COLORS[t] }" />
            {{ KB_TABLE_LABELS[t] }}
          </span>
        </div>
      </div>
    </div>

    <!-- ════ 搜索后：顶部紧凑搜索栏 + 结果 ════ -->
    <template v-else>
      <div class="sticky-header">
        <div class="topbar">
          <div class="topbar-logo" @click="clearSearch">
            <el-icon :size="22" color="#409eff"><Reading /></el-icon>
            <span>知识库</span>
          </div>
          <div class="search-pill search-pill--compact">
            <el-icon class="search-pill-icon" :size="18"><Search /></el-icon>
            <input
              v-model="query" class="search-pill-input"
              placeholder="搜索..."
              @keyup.enter="doSearch"
            />
            <el-dropdown trigger="click">
              <button class="search-pill-filter" title="数据范围">
                <el-icon :size="15"><Filter /></el-icon>
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item
                    v-for="t in TABLE_OPTIONS" :key="t.value"
                    :divided="t.value === 'all'"
                    @click="toggleTable(t.value)"
                  >
                    <span class="dd-item">
                      <el-checkbox
                        :model-value="t.value === 'all' ? true : selectedTables.includes(t.value as KBTableName)"
                        :disabled="t.value === 'all'" size="small"
                      />
                      <span class="dd-dot" :style="{ background: t.color }" />
                      {{ t.label }}
                    </span>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <button class="search-pill-btn" :class="{ 'is-loading': loading }" @click="doSearch">
              <el-icon v-if="!loading" :size="16"><Search /></el-icon>
              <el-icon v-else class="loading-spin" :size="16"><Loading /></el-icon>
            </button>
          </div>
          <div v-if="hasSearched" class="topbar-tags">
            <el-tag
              v-for="t in activeTableTags" :key="t.value"
              :color="t.color" effect="dark" size="small"
              style="border:none;color:#fff"
            >{{ t.label }}</el-tag>
          </div>
        </div>

        <!-- Tabs -->
        <div class="tabs-bar">
          <div
            v-for="tab in KB_TABS" :key="tab.key"
            class="tab-item" :class="{ 'tab-on': activeTab === tab.key }"
            @click="activeTab = tab.key"
          >
            {{ tab.label }}
            <span v-if="tabCounts[tab.key]" class="tab-num">{{ tabCounts[tab.key] }}</span>
          </div>
        </div>
      </div>

      <!-- 结果区 -->
      <div class="results-area">
        <div v-if="loading" class="state-wrap">
          <el-icon class="loading-spin" :size="28"><Loading /></el-icon>
          <span>搜索中...</span>
        </div>

        <div v-else-if="pagedItems.length === 0" class="state-wrap">
          <el-icon :size="40" color="var(--text-muted)"><Document /></el-icon>
          <p class="state-text">没有找到相关结果</p>
        </div>

        <div v-else class="results-list">
          <div
            v-for="item in pagedItems"
            :key="`${activeTab}-${item.id}`"
            class="result-card"
            @click="openDetail(item)"
          >
            <div class="card-top">
              <el-tag v-if="item._tableName" size="small" :color="getTableColor(item._tableName)"
                      effect="dark" class="card-type-tag"
                      style="border:none;color:#fff">{{ getTableLabel(item._tableName) }}</el-tag>
              <span class="card-title">{{ item.title }}</span>
            </div>
            <!-- 节点状态摘要标签 -->
            <div v-if="getNodeState(item)" class="node-state-badges">
              <el-tag size="small" type="info" effect="plain">
                驱动 {{ getNodeState(item)!.primary_drivers?.length ?? 0 }}
              </el-tag>
              <el-tag size="small" type="warning" effect="plain">
                风险 {{ getNodeState(item)!.risks?.length ?? 0 }}
              </el-tag>
              <el-tag size="small" type="success" effect="plain">
                关注 {{ getNodeState(item)!.focus_points?.length ?? 0 }}
              </el-tag>
              <span v-if="getNodeState(item)?.state_summary" class="node-state-oneline">
                {{ getNodeState(item)!.state_summary }}
              </span>
            </div>
            <div v-if="item.snippet" class="card-snippet" v-html="renderMd(item.snippet)" />
            <div class="card-meta">
              <div class="card-meta-left">
                <span v-if="item.time" class="card-time"><el-icon :size="12"><Clock /></el-icon>{{ formatTime(item.time) }}</span>
              </div>
              <div class="card-meta-right">
                <div class="card-score"><div class="score-bar" :style="{ width: `${Math.min(100, (item.score ?? 0) * 120)}%`, background: getTableColor(item._tableName || 'raw_information') }" /></div>
                <span class="score-val">{{ (item.score || 0).toFixed(3) }}</span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="!loading && countForTab(activeTab) > PAGE_SIZE" class="pagination-wrap">
          <el-pagination
            :current-page="pageMap[activeTab] || 1" :page-size="PAGE_SIZE"
            :total="countForTab(activeTab)" layout="prev, pager, next, total"
            @current-change="(p: number) => handlePageChange(activeTab, p)"
          />
        </div>
      </div>
    </template>
    <el-drawer v-model="detailVisible" direction="rtl" size="720px" :show-close="true" class="kb-drawer">
      <template #header>
        <div class="drawer-header">
          <el-tag v-if="detailItem?._tableName" :color="getTableColor(detailItem._tableName)" effect="dark" size="small" style="border:none;color:#fff">{{ getTableLabel(detailItem._tableName) }}</el-tag>
          <h3 class="drawer-title-text">{{ detailItem?.title || '加载中...' }}</h3>
        </div>
      </template>
      <div v-if="articleLoading" class="state-wrap" style="padding:60px 0">
        <el-icon class="loading-spin" :size="28"><Loading /></el-icon><span>加载全文...</span>
      </div>
      <div v-else-if="articleData" class="drawer-body">
        <div class="drawer-meta">
          <span v-if="detailItem?.time" class="meta-item"><el-icon :size="13"><Clock /></el-icon>{{ formatTime(detailItem.time) }}</span>
          <span class="meta-item">相关度 <strong>{{ (detailItem?.score ?? 0).toFixed(4) }}</strong></span>
        </div>

        <!-- ── 节点状态结构化展示 ── -->
        <template v-if="isNodeArticle">
          <!-- 核心逻辑 -->
          <div v-if="nodeStateData?.core_logic" class="article-section">
            <div class="article-field-label">核心逻辑</div>
            <div class="article-field-content markdown-body" v-html="renderMdBlock(nodeStateData.core_logic)" />
          </div>
          <!-- 状态摘要 -->
          <div v-if="nodeStateData?.state_summary" class="article-section">
            <div class="article-field-label">状态摘要</div>
            <div class="article-field-content markdown-body" v-html="renderMdBlock(nodeStateData.state_summary)" />
          </div>
          <!-- 驱动因素 -->
          <div v-if="nodeStateData?.primary_drivers?.length" class="article-section">
            <div class="article-field-label">主要驱动因素</div>
            <div class="state-list">
              <div v-for="(d, i) in nodeStateData.primary_drivers" :key="i" class="state-item">
                <span class="state-item-dot" style="background: #e74c3c" />
                <div class="state-item-body">
                  <strong>{{ d.driver }}</strong>
                  <span v-if="d.strength" class="state-item-sub">强度: {{ d.strength }}</span>
                </div>
              </div>
            </div>
          </div>
          <!-- 风险点 -->
          <div v-if="nodeStateData?.risks?.length" class="article-section">
            <div class="article-field-label">风险点</div>
            <div class="state-list">
              <div v-for="(r, i) in nodeStateData.risks" :key="i" class="state-item">
                <span class="state-item-dot" style="background: #e67e22" />
                <div class="state-item-body">
                  <strong>{{ r.risk }}</strong>
                  <span v-if="r.severity" class="state-item-sub">严重程度: {{ r.severity }}</span>
                </div>
              </div>
            </div>
          </div>
          <!-- 关注要点 -->
          <div v-if="nodeStateData?.focus_points?.length" class="article-section">
            <div class="article-field-label">关注要点</div>
            <div class="state-list">
              <div v-for="(f, i) in nodeStateData.focus_points" :key="i" class="state-item">
                <span class="state-item-dot" style="background: #3498db" />
                <div class="state-item-body">
                  <strong>{{ f.point }}</strong>
                  <span v-if="f.priority" class="state-item-sub">优先级: {{ f.priority }}</span>
                </div>
              </div>
            </div>
          </div>
          <!-- 近期变化 -->
          <div v-if="nodeStateData?.recent_changes" class="article-section">
            <div class="article-field-label">近期变化</div>
            <div class="article-field-content markdown-body" v-html="renderMdBlock(nodeStateData.recent_changes)" />
          </div>
          <!-- 不确定因素 -->
          <div v-if="nodeStateData?.uncertainty_flags?.length" class="article-section">
            <div class="article-field-label">不确定因素</div>
            <div class="state-list">
              <div v-for="(flag, i) in nodeStateData.uncertainty_flags" :key="i" class="state-item">
                <span class="state-item-dot" style="background: #9b59b6" />
                <span>{{ typeof flag === 'string' ? flag : JSON.stringify(flag) }}</span>
              </div>
            </div>
          </div>
          <div v-if="nodeStateData?.version" class="state-version-row">
            <span>版本 v{{ nodeStateData.version }}</span>
            <span v-if="nodeStateData.effective_from">生效: {{ formatTime(nodeStateData.effective_from) }}</span>
          </div>
          <el-divider />
        </template>

        <!-- ── 常规字段展示（排除已结构化的 node_state）── -->
        <div v-for="(val, key) in articleContentFields" :key="key" class="article-section">
          <div class="article-field-label">{{ fieldLabelMap[key as string] || key }}</div>
          <div class="article-field-content markdown-body" v-html="renderMdBlock(val)" />
        </div>
        <div class="article-id-row">
          <span style="font-size:12px;color:var(--text-muted)">ID</span>
          <code class="drawer-id">{{ detailItem?.id }}</code>
        </div>
      </div>
      <div v-else class="state-wrap" style="padding:60px 0">
        <p>加载失败</p>
        <el-button size="small" @click="detailItem && openDetail(detailItem)">重试</el-button>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onActivated, onDeactivated } from 'vue'
import { marked } from 'marked'
import { sanitizeHtml } from '@/utils/sanitize'
import {
  Search, Filter, ArrowDown, Reading, Loading, Document, Clock,
} from '@element-plus/icons-vue'
import { searchKnowledge, fetchKBRecords, fetchArticle } from '@/api/knowledge'
import type { KBSearchResultItem, KBTableName, NodeStateData } from '@/types/knowledge'
import { KB_TABS, KB_TABLE_LABELS, KB_TABLE_COLORS } from '@/types/knowledge'

marked.setOptions({ breaks: true, gfm: true })

function renderMd(text: string | null | undefined): string {
  if (!text) return ''
  try { return sanitizeHtml(marked.parseInline(text) as string) }
  catch { return text.replace(/</g, '&lt;') }
}

function renderMdBlock(text: string | null | undefined): string {
  if (!text) return ''
  try { return sanitizeHtml(marked.parse(text) as string) }
  catch { return text.replace(/</g, '&lt;') }
}

const fieldLabelMap: Record<string, string> = {
  body: '正文', content: '内容', lessons_learned: '经验教训',
  description: '描述', summary: '摘要', error_reason: '错误原因',
  expected_outcome: '预期结果', actual_outcome: '实际结果',
  missed_factors: '遗漏因素', adjustment_suggestions: '调整建议',
  source: '来源', source_url: '来源链接', info_type: '资讯类型',
  analysis_type: '分析类型', confidence: '置信度', time_horizon: '时效',
  processing_status: '处理状态', importance_score: '重要性评分',
  node_type: '节点类型', ticker: '代码',
  // 节点状态字段（在抽屉结构化展示中使用）
  core_logic: '核心逻辑', state_summary: '状态摘要',
  primary_drivers: '主要驱动因素', risks: '风险点',
  focus_points: '关注要点', recent_changes: '近期变化',
  uncertainty_flags: '不确定因素', key_evidence_ids: '关键证据',
  version: '版本', effective_from: '生效时间',
  node_state: '当前状态',
}

const PAGE_SIZE = 20
const ALL_TABLES: KBTableName[] = ['raw_information', 'analyses', 'feedbacks', 'nodes']

const TABLE_OPTIONS = [
  { value: 'all', label: '全选 / 取消全选', color: '#409eff' },
  ...ALL_TABLES.map(t => ({
    value: t, label: KB_TABLE_LABELS[t], color: KB_TABLE_COLORS[t],
  })),
]

// ── 状态 ──
const query = ref('')
const loading = ref(false)
const hasSearched = ref(false)
const selectedTables = ref<KBTableName[]>([...ALL_TABLES])
type KBActiveTab = 'all' | KBTableName

const activeTab = ref<KBActiveTab>('all')
const searchResults = ref<Record<string, KBSearchResultItem[]>>({})
const counts = ref<Record<string, number>>({})
const pageMap = ref<Record<string, number>>({})

// 详情抽屉
const detailVisible = ref(false)
const detailItem = ref<(KBSearchResultItem & { _tableName?: string }) | null>(null)
const articleLoading = ref(false)
const articleData = ref<Record<string, unknown> | null>(null)

// ── 计算属性 ──
const activeTableTags = computed(() =>
  TABLE_OPTIONS.filter(t => t.value !== 'all' && selectedTables.value.includes(t.value as KBTableName))
)

const displayTabs = computed(() => KB_TABS)

const tabCounts = computed(() => {
  const r = searchResults.value
  return { all: Object.values(r).reduce((s, a) => s + (a?.length || 0), 0), ...counts.value } as Record<string, number>
})

const pagedItems = computed(() => {
  const results = searchResults.value
  let items: (KBSearchResultItem & { _tableName?: string })[] = []
  if (activeTab.value === 'all') {
    for (const [table, arr] of Object.entries(results)) {
      if (arr) items.push(...arr.map(i => ({ ...i, score: i.score ?? 0, _tableName: table })))
    }
    items.sort((a, b) => b.score - a.score)
  } else {
    items = (results[activeTab.value] || []).map(i => ({ ...i, score: i.score ?? 0, _tableName: activeTab.value }))
  }
  const page = pageMap.value[activeTab.value] || 1
  return items.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
})

const articleContentFields = computed(() => {
  if (!articleData.value) return {}
  const skip = new Set(['id', 'created_at', 'updated_at', 'is_active', 'agent_id'])
  // 节点文章：排除已结构化的状态字段，避免重复展示
  if (isNodeArticle.value) {
    for (const k of ['node_state', 'core_logic', 'state_summary', 'primary_drivers', 'risks',
      'focus_points', 'recent_changes', 'uncertainty_flags', 'key_evidence_ids', 'version', 'effective_from']) {
      skip.add(k)
    }
  }
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(articleData.value)) {
    if (skip.has(k) || v === null || v === undefined || v === '' || v === false) continue
    out[k] = typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v)
  }
  return out
})

/** 是否为节点相关文章 */
const isNodeArticle = computed(() => detailItem.value?._tableName === 'nodes')

/** 从 articleData 中提取结构化节点状态 */
const nodeStateData = computed<NodeStateData | null>(() => {
  if (!articleData.value) return null
  const ns = articleData.value.node_state as NodeStateData | null | undefined
  if (ns && typeof ns === 'object' && (ns.state_summary || ns.core_logic)) return ns
  return null
})

// ── 页面白色背景（覆盖暗色主题）──
function setMainBg(color: string) {
  const mc = document.querySelector('.main-content') as HTMLElement | null
  if (mc) {
    if (color) mc.style.setProperty('background', color, 'important')
    else mc.style.removeProperty('background')
  }
}
onActivated(() => setMainBg(''))
onDeactivated(() => setMainBg(''))

// ── 方法 ─
function toggleTable(value: string) {
  if (value === 'all') {
    const firstTable = ALL_TABLES[0]
    if (!firstTable) return
    selectedTables.value = selectedTables.value.length === ALL_TABLES.length
      ? [firstTable] : [...ALL_TABLES]
  } else {
    const t = value as KBTableName
    const idx = selectedTables.value.indexOf(t)
    if (idx >= 0 && selectedTables.value.length > 1) selectedTables.value.splice(idx, 1)
    else if (idx < 0) selectedTables.value.push(t)
  }
  if (hasSearched.value) doSearch()
}

function clearSearch() {
  hasSearched.value = false
  searchResults.value = {}
  counts.value = {}
  pageMap.value = {}
}

async function doSearch() {
  const q = query.value.trim()
  if (!q) { clearSearch(); return }
  loading.value = true
  pageMap.value = {}
  try {
    const res = await searchKnowledge({ query: q, tables: selectedTables.value, limit: 200 })
    searchResults.value = res.results
    counts.value = res.counts
    hasSearched.value = true
  } catch (e) {
    console.error('[KB Search]', e)
  } finally {
    loading.value = false
  }
}

function handlePageChange(tab: string, page: number) {
  pageMap.value = { ...pageMap.value, [tab]: page }
}

function countForTab(tab: string): number {
  return tabCounts.value[tab] ?? 0
}

async function openDetail(item: KBSearchResultItem & { _tableName?: string }) {
  detailItem.value = item
  detailVisible.value = true
  articleLoading.value = true
  articleData.value = null
  if (!item._tableName) { articleLoading.value = false; return }
  try {
    articleData.value = await fetchArticle(item._tableName, item.id)
  } catch (e) {
    console.error('[KB Article]', e)
    articleData.value = null
  } finally {
    articleLoading.value = false
  }
}

function getTableLabel(table: string): string {
  return KB_TABLE_LABELS[table as KBTableName] || table
}

function getTableColor(table: string): string {
  return KB_TABLE_COLORS[table as KBTableName] || '#409eff'
}

/** 从搜索结果的 extra 中提取节点状态数据 */
function getNodeState(item: KBSearchResultItem & { _tableName?: string }): NodeStateData | null {
  if (item._tableName !== 'nodes') return null
  const extra = item.extra as Record<string, unknown> | undefined
  const ns = extra?.node_state as NodeStateData | undefined
  return ns || null
}

function formatTime(iso: string | null): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch {
    return iso.slice(0, 16).replace('T', ' ')
  }
}
</script>

<style scoped>
.kb-search-page {
  min-height: 100vh;
  background: var(--color-surface);
}

/* ─ 搜索结果容器 ── */
.search-layout {
  min-height: 100%;
}

/* ══════════════════════════════════════════════
   Landing（初始居中搜索）
   ══════════════════════════════════════════════ */
.landing {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - 100px);
  padding: 20px;
}

.landing-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  max-width: 680px;
  margin-top: -80px;   /* 视觉上偏上 */
}

.landing-logo {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 32px;
}

.landing-logo h1 {
  margin: 0;
  font-size: 28px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.5px;
}

/* ── Search Pill ── */
.search-pill {
  display: flex;
  align-items: center;
  width: 100%;
  height: 52px;
  background: var(--color-surface);
  border: 1px solid var(--border-default);
  border-radius: 28px;
  padding: 0 6px 0 18px;
  transition: box-shadow 0.2s, border-color 0.2s;
}

.search-pill:hover,
.search-pill:focus-within {
  border-color: var(--border-strong);
  box-shadow: 0 2px 12px rgba(0,0,0,0.08);
}

.search-pill-icon {
  color: var(--text-muted);
  flex-shrink: 0;
  margin-right: 12px;
}

.search-pill-input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 16px;
  color: var(--text-primary);
  background: transparent;
  min-width: 0;
}

.search-pill-input::placeholder {
  color: var(--text-muted);
}

.search-pill-filter {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  background: transparent;
  border-radius: 50%;
  cursor: pointer;
  color: var(--text-muted);
  transition: background 0.15s;
  flex-shrink: 0;
}

.search-pill-filter:hover {
  background: var(--color-surface-muted);
  color: var(--text-primary);
}

.search-pill-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: none;
  background: #409eff;
  border-radius: 50%;
  cursor: pointer;
  color: #fff;
  margin-left: 4px;
  flex-shrink: 0;
  transition: background 0.15s, transform 0.1s;
}

.search-pill-btn:hover {
  background: #337ecc;
  transform: scale(1.05);
}

.search-pill-btn:active {
  transform: scale(0.95);
}

.search-pill-btn.is-loading {
  background: #79bbff;
  pointer-events: none;
}

/* 紧凑版（搜索后顶部） */
.search-pill--compact {
  height: 44px;
  padding: 0 4px 0 14px;
  flex: 1;
  max-width: 560px;
}

.search-pill--compact .search-pill-input {
  font-size: 14px;
}

/* ── Landing chips ── */
.landing-chips {
  display: flex;
  gap: 8px;
  margin-top: 20px;
  flex-wrap: wrap;
  justify-content: center;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 14px;
  border-radius: 16px;
  font-size: 13px;
  color: var(--text-secondary);
  background: var(--color-surface-muted);
  cursor: pointer;
  transition: all 0.15s;
  user-select: none;
}

.chip:hover { background: var(--color-surface-hover); }

.chip-on {
  background: var(--color-info-bg, rgba(91, 141, 239, 0.1));
  color: var(--color-info);
  font-weight: 500;
}

.chip-dot {
  width: 7px; height: 7px; border-radius: 50%;
}

/*  粘性头部 ── */
.sticky-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--color-surface);
}

/* ══════════════════════════════════════════════
   Topbar（搜索后顶部）
   ══════════════════════════════════════════════ */
.topbar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 24px;
  max-width: 860px;
  margin: 0 auto;
  border-bottom: 1px solid var(--border-subtle);
}

.topbar-logo {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  flex-shrink: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.topbar-logo:hover { opacity: 0.7; }

.topbar-tags {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

/* ── Tabs bar ── */
.tabs-bar {
  display: flex;
  gap: 0;
  padding: 0 24px;
  max-width: 860px;
  margin: 0 auto;
  border-bottom: 1px solid var(--border-subtle);
}

.tab-item {
  padding: 12px 18px;
  font-size: 14px;
  color: var(--text-secondary);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.15s;
  display: flex;
  align-items: center;
  gap: 5px;
}

.tab-item:hover { color: var(--color-info); }

.tab-on {
  color: var(--color-info);
  font-weight: 500;
  border-bottom-color: var(--color-info);
}

.tab-num {
  font-size: 11px;
  color: var(--text-muted);
}

/* ══════════════════════════════════════════════
   结果区
   ══════════════════════════════════════════════ */
.results-area {
  padding: 16px 24px 40px;
  max-width: 860px;
  margin: 0 auto;
}

.state-wrap {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; gap: 10px; padding: 60px 20px; color: var(--text-muted);
}

.state-text { font-size: 14px; color: var(--text-secondary); margin: 0; }

.loading-spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.results-list {
  display: flex; flex-direction: column; gap: 12px;
}

/* ── 结果卡片 ── */
.result-card {
  padding: 18px 20px;
  border: 1px solid var(--border-default);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
  background: var(--color-surface);
}

.result-card:hover {
  border-color: var(--border-strong);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  transform: translateY(-1px);
}

.card-top {
  display: flex; align-items: center; gap: 10px; margin-bottom: 6px;
}

.card-type-tag {
  font-size: 11px !important;
  padding: 0 7px !important;
  height: 20px !important;
  line-height: 20px !important;
  border-radius: 4px !important;
  flex-shrink: 0;
}

.card-title {
  font-size: 17px;
  color: var(--color-info);
  line-height: 1.4;
  overflow: hidden; text-overflow: ellipsis;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  font-weight: 500;
}

.result-card:hover .card-title {
  text-decoration: underline;
}

.card-snippet {
  font-size: 13.5px; color: var(--text-secondary); line-height: 1.65;
  margin: 8px 0 10px;
  word-break: break-word;
}

.card-snippet :deep(p) { margin: 0; }
.card-snippet :deep(strong), .card-snippet :deep(em) { color: var(--text-primary); font-weight: 600; }
.card-snippet :deep(em) { font-style: normal; color: #d93025; }
.card-snippet :deep(code) {
  background: var(--color-surface-muted); padding: 1px 4px; border-radius: 3px; font-size: 12px;
}

.card-meta {
  display: flex; align-items: center; justify-content: space-between;
  margin-top: 2px;
}

.card-meta-left {
  display: flex; align-items: center; gap: 10px;
}

.card-meta-right {
  display: flex; align-items: center; gap: 10px; flex-shrink: 0;
}

.card-time {
  display: flex; align-items: center; gap: 4px;
  font-size: 12px; color: var(--text-muted);
}

.card-score {
  width: 52px; height: 4px;
  background: var(--color-surface-muted); border-radius: 2px; overflow: hidden;
}

.score-bar { height: 100%; border-radius: 2px; transition: width 0.3s; }

.score-val { font-size: 11px; color: var(--text-muted); font-family: monospace; min-width: 36px; }

/* ── 分页 ── */
.pagination-wrap {
  display: flex; justify-content: center; padding-top: 24px;
}

/* ══════════════════════════════════════════════
   抽屉
   ══════════════════════════════════════════════ */
.drawer-header {
  display: flex; align-items: center; gap: 10px;
}

.drawer-title-text {
  margin: 0; font-size: 17px; font-weight: 600; color: var(--text-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;
}

.drawer-body { padding: 0 4px; }

.drawer-meta {
  display: flex; align-items: center; gap: 16px;
  padding-bottom: 14px; border-bottom: 1px solid var(--border-subtle);
  margin-bottom: 18px; font-size: 13px; color: var(--text-muted);
}

.meta-item { display: flex; align-items: center; gap: 4px; }
.meta-item strong { color: var(--text-primary); font-weight: 600; }

.article-section { margin-bottom: 20px; }

.article-field-label {
  font-size: 11px; font-weight: 600; color: var(--color-info);
  text-transform: uppercase; letter-spacing: 0.5px;
  margin-bottom: 6px; padding-bottom: 4px;
  border-bottom: 1px solid rgba(91, 141, 239, 0.15);
}

.article-field-content {
  font-size: 14px; color: var(--text-primary); line-height: 1.75; word-break: break-word;
}

/* ── Markdown ── */
.markdown-body :deep(p) { margin: 0 0 10px; }
.markdown-body :deep(p:last-child) { margin-bottom: 0; }
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) { margin: 16px 0 8px; font-weight: 600; color: var(--text-primary); }
.markdown-body :deep(h1) { font-size: 18px; }
.markdown-body :deep(h2) { font-size: 16px; }
.markdown-body :deep(h3) { font-size: 15px; }
.markdown-body :deep(ul),
.markdown-body :deep(ol) { padding-left: 20px; margin: 8px 0; }
.markdown-body :deep(li) { margin-bottom: 4px; }
.markdown-body :deep(code) {
  background: var(--color-surface-muted); padding: 2px 5px; border-radius: 3px;
  font-size: 13px; font-family: monospace;
}
.markdown-body :deep(pre) {
  background: #1e2430; color: #e0e0e0;
  padding: 12px 14px; border-radius: 6px;
  overflow-x: auto; margin: 10px 0;
}
.markdown-body :deep(pre code) { background: none; padding: 0; color: inherit; }
.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--color-info); padding: 4px 12px;
  margin: 10px 0; color: var(--text-secondary); background: var(--color-surface-alt);
  border-radius: 0 4px 4px 0;
}
.markdown-body :deep(table) {
  border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 13px;
}
.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--border-default); padding: 6px 10px; text-align: left;
}
.markdown-body :deep(th) { background: var(--color-surface-alt); font-weight: 600; }
.markdown-body :deep(a) { color: var(--color-info); text-decoration: none; }
.markdown-body :deep(a:hover) { text-decoration: underline; }
.markdown-body :deep(hr) {
  border: none; border-top: 1px solid var(--border-default); margin: 14px 0;
}

.article-id-row {
  margin-top: 24px; padding-top: 14px;
  border-top: 1px solid var(--border-subtle);
  display: flex; align-items: center; gap: 8px;
}

.drawer-id {
  font-size: 11px; color: var(--text-muted); background: var(--color-surface-muted);
  padding: 3px 6px; border-radius: 3px; word-break: break-all;
}

/* ── Dropdown 内部 ── */
.dd-item { display: flex; align-items: center; gap: 6px; min-width: 110px; }
.dd-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }

/* ══════════════════════════════════════════════
   节点状态展示
   ══════════════════════════════════════════════ */

/* ── 搜索结果卡片中的状态摘要 ── */
.node-state-badges {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 6px 0 4px;
  flex-wrap: wrap;
}

.node-state-oneline {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 400px;
  margin-left: 4px;
}

/* ── 抽屉内结构化状态列表 ── */
.state-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.state-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 12px;
  background: var(--color-surface-alt, var(--color-surface-muted));
  border-radius: 6px;
  border-left: 3px solid transparent;
}

.state-item-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 5px;
}

.state-item-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.state-item-body strong {
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.4;
}

.state-item-sub {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

/* ── 版本行 ── */
.state-version-row {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 12px;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
