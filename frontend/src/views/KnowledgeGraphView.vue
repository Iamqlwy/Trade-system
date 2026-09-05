<template>
  <div class="knowledge-graph-page">
    <!-- 顶部工具栏 -->
    <div class="graph-toolbar">
      <div class="toolbar-left">
        <h2 class="toolbar-title">知识图谱</h2>
        <el-tag type="info" size="small">
          节点 {{ loadedNodeCount }} / {{ totalEntities }}
          <template v-if="filteredCount > 0">
            &nbsp;|&nbsp; <el-tooltip content="关系度过高已被过滤的超级节点"><span class="filtered-hint">已过滤 {{ filteredCount }}</span></el-tooltip>
          </template>
          &nbsp;|&nbsp; 边 {{ loadedEdgeCount }}
        </el-tag>
      </div>
      <div class="toolbar-center">
        <el-input
          v-model="searchQuery"
          placeholder="搜索实体名称..."
          :prefix-icon="Search"
          clearable
          style="width: 280px"
          @keyup.enter="handleSearch"
          @clear="clearSearch"
        />
        <div v-if="searchResults.length" class="search-dropdown">
          <div
            v-for="item in searchResults"
            :key="item.id"
            class="search-item"
            @click="focusEntity(item.id)"
          >
            <span class="search-dot" :style="{ background: getTypeColor(item.entity_type) }" />
            <span class="search-name">{{ item.name }}</span>
            <el-tag size="small" :color="getTypeColor(item.entity_type)" effect="dark"
              style="border: none; color: #fff; font-size: 11px">
              {{ getTypeLabel(item.entity_type) }}
            </el-tag>
            <span class="search-count">{{ item.info_count }} 条资讯</span>
          </div>
        </div>
      </div>
      <div class="toolbar-right">
        <el-tooltip content="过滤关系度过高的超级节点（如'中国'），值越小过滤越严格" placement="bottom">
          <div class="degree-control">
            <span class="degree-label">最大关联</span>
            <el-slider v-model="maxDegree" :min="10" :max="200" :step="10"
              :format-tooltip="(v: number) => v <= 0 ? '不过滤' : `≤ ${v}`"
              style="width: 120px" @change="handleTypeFilter" />
          </div>
        </el-tooltip>
        <el-select v-model="filterType" placeholder="筛选类型" clearable style="width: 130px"
          @change="handleTypeFilter">
          <el-option v-for="ts in typeStats" :key="ts.entity_type"
            :label="`${getTypeLabel(ts.entity_type)} (${ts.count})`" :value="ts.entity_type" />
        </el-select>
        <el-button :icon="Refresh" @click="reloadGraph" :loading="loading">刷新</el-button>
        <el-button :icon="Aim" @click="fitView">居中</el-button>
      </div>
    </div>

    <!-- 主体 -->
    <div class="graph-body">
      <div class="graph-canvas-wrap" ref="canvasWrap">
        <div v-if="loading" class="graph-loading">
          <el-icon class="loading-spin" :size="32"><Loading /></el-icon>
          <span>加载图谱数据中...</span>
        </div>
        <div v-if="!loading && loadedNodeCount === 0" class="graph-empty">
          <el-icon :size="48" color="var(--text-muted)"><Share /></el-icon>
          <p>暂无数据</p>
          <p class="empty-hint">请确认知识库数据库已连接，且存在实体数据</p>
        </div>
        <div ref="graphContainer" class="graph-container" />
      </div>

      <!-- 右侧详情面板 -->
      <transition name="slide-right">
        <div v-if="selectedEntity" class="detail-panel">
          <div class="detail-header">
            <span class="detail-type-dot" :style="{ background: getTypeColor(selectedEntity.entity_type) }" />
            <h3 class="detail-name">{{ selectedEntity.name }}</h3>
            <el-button class="detail-close" :icon="Close" text @click="closeDetail" />
          </div>

          <div class="detail-body">
            <div class="detail-badges">
              <el-tag :color="getTypeColor(selectedEntity.entity_type)" effect="dark"
                style="border: none; color: #fff">{{ getTypeLabel(selectedEntity.entity_type) }}</el-tag>
              <el-tag type="info">{{ selectedEntity.info_count }} 条资讯</el-tag>
            </div>

            <div v-if="selectedEntity.aliases && selectedEntity.aliases.length" class="detail-section">
              <div class="section-label">别名</div>
              <div class="alias-list">
                <el-tag v-for="alias in selectedEntity.aliases" :key="alias" size="small" type="info">{{ alias }}</el-tag>
              </div>
            </div>

            <div class="detail-section">
              <div class="section-label">关联实体 <el-tag size="small" round>{{ neighborNodes.length }}</el-tag></div>
              <div v-if="expanding" class="neighbor-loading">
                <el-icon class="loading-spin" :size="16"><Loading /></el-icon>
              </div>
              <div v-else class="neighbor-list">
                <div v-for="n in neighborNodes" :key="n.id" class="neighbor-item" @click="focusEntity(n.id)">
                  <span class="neighbor-dot" :style="{ background: getTypeColor(n.entity_type) }" />
                  <span class="neighbor-name">{{ n.name }}</span>
                  <span class="neighbor-type">{{ getTypeLabel(n.entity_type) }}</span>
                </div>
                <div v-if="!neighborNodes.length" class="neighbor-empty">暂无关联实体</div>
              </div>
            </div>

            <div v-if="selectedEdges.length" class="detail-section">
              <div class="section-label">关系类型</div>
              <div class="relation-list">
                <div v-for="edge in selectedEdges" :key="`${edge.source}-${edge.target}-${edge.relationship_type}`" class="relation-item">
                  <el-tag size="small">{{ getRelLabel(edge.relationship_type) }}</el-tag>
                  <span v-if="edge.description" class="relation-desc">{{ edge.description }}</span>
                </div>
              </div>
            </div>

            <div v-if="entityDetail" class="detail-section">
              <div class="section-label">详细信息</div>
              <div class="meta-grid">
                <div class="meta-item">
                  <span class="meta-label">标准化名称</span>
                  <span class="meta-value">{{ entityDetail.normalized_name }}</span>
                </div>
                <div class="meta-item">
                  <span class="meta-label">关联数</span>
                  <span class="meta-value">{{ entityDetail.relationship_count }}</span>
                </div>
                <div v-if="entityDetail.created_at" class="meta-item">
                  <span class="meta-label">创建时间</span>
                  <span class="meta-value">{{ formatDate(entityDetail.created_at) }}</span>
                </div>
              </div>
            </div>

            <div class="detail-actions">
              <el-button type="primary" size="small" @click="handleExpandClick"
                :loading="expanding" :disabled="expandedIds.has(selectedEntity.id)">
                展开邻居
              </el-button>
            </div>
          </div>
        </div>
      </transition>
    </div>

    <!-- 底部图例 -->
    <div class="graph-legend">
      <div class="legend-title">实体类型</div>
      <div class="legend-items">
        <div v-for="(color, type) in visibleTypes" :key="type" class="legend-item"
          :class="{ 'legend-active': filterType === type }" @click="toggleTypeFilter(type)">
          <span class="legend-dot" :style="{ background: color }" />
          <span class="legend-label">{{ getTypeLabel(type) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { Search, Refresh, Aim, Close, Loading, Share } from '@element-plus/icons-vue'
import {
  fetchGraphData, expandEntity, fetchEntityDetail, searchEntities, fetchTypeStats,
} from '@/api/knowledge'
import type {
  EntityNode, EntityEdge, EntityDetail as EntityDetailType,
  EntitySearchResult, TypeStats,
} from '@/types/knowledge'
import {
  ENTITY_TYPE_COLORS as TYPE_COLORS,
  ENTITY_TYPE_LABELS as TYPE_LABELS,
  RELATIONSHIP_TYPE_LABELS as REL_LABELS,
} from '@/types/knowledge'
import { useThemeStore } from '@/stores/theme'

const themeStore = useThemeStore()
const isDark = computed(() => themeStore.mode === 'dark')

// ── 状态 ──
const canvasWrap = ref<HTMLDivElement>()
const graphContainer = ref<HTMLDivElement>()
const loading = ref(false)
const expanding = ref(false)

const allNodes = ref<EntityNode[]>([])
const allEdges = ref<EntityEdge[]>([])
const totalEntities = ref(0)
const filteredCount = ref(0)
const expandedIds = ref<Set<string>>(new Set())

const selectedEntity = ref<EntityNode | null>(null)
const entityDetail = ref<EntityDetailType | null>(null)
const neighborNodes = ref<EntityNode[]>([])
const selectedEdges = ref<EntityEdge[]>([])

const searchQuery = ref('')
const searchResults = ref<EntitySearchResult[]>([])
const filterType = ref('')
const maxDegree = ref(50)
const typeStats = ref<TypeStats[]>([])

let graph: any = null

// ── 计算属性 ──
const loadedNodeCount = computed(() => allNodes.value.length)
const loadedEdgeCount = computed(() => allEdges.value.length)

const visibleTypes = computed(() => {
  const types = new Set(allNodes.value.map(n => n.entity_type))
  const result: Record<string, string> = {}
  types.forEach(t => { result[t] = TYPE_COLORS[t] || '#999' })
  return result
})

// ── 辅助 ──
function getTypeColor(type: string): string { return TYPE_COLORS[type] || '#999' }
function getTypeLabel(type: string): string { return TYPE_LABELS[type] || type }
function getRelLabel(type: string): string { return REL_LABELS[type] || type }
function formatDate(s: string): string { try { return new Date(s).toLocaleDateString('zh-CN') } catch { return s } }

function nodeSize(c: number): number {
  return Math.max(20, Math.min(50, 20 + Math.log2(c + 1) * 5))
}

// ── 缩放感知标签 ──
function updateNodeLabelsForZoom() {
  if (!graph) return
  const zoom = graph.getZoom()
  const opacity = zoom >= 0.6 ? 1 : 0
  graph.getNodes().forEach((n: any) => {
    graph.updateItem(n, { labelCfg: { style: { opacity } } })
  })
}

// ── G6 v4 初始化 ──
async function initGraph() {
  if (!graphContainer.value) return

  let G6: any
  try {
    G6 = (await import('@antv/g6')).default || await import('@antv/g6')
  } catch {
    console.error('[KnowledgeGraph] @antv/g6 未安装')
    return
  }

  const width = graphContainer.value.clientWidth || 800
  const height = graphContainer.value.clientHeight || 600

  graph = new G6.Graph({
    container: graphContainer.value,
    width,
    height,
    fitView: true,
    fitViewPadding: 40,
    modes: {
      default: ['drag-canvas', 'zoom-canvas', 'drag-node'],
    },
    layout: {
      type: 'force',
      workerEnabled: true,
      maxIteration: 500,
      preventOverlap: true,
      nodeStrength: -150,
      edgeStrength: 0.15,
      nodeSpacing: 15,
      alphaDecay: 0.06,
      alphaMin: 0.08,
    },
    defaultNode: {
      type: 'circle',
      style: {
        stroke: isDark.value ? '#12151c' : '#fff',
        lineWidth: 1.5,
        cursor: 'pointer',
      },
      labelCfg: {
        position: 'bottom',
        offset: 6,
        style: {
          fill: isDark.value ? '#e2e4ea' : '#333',
          fontSize: 11,
          textBaseline: 'top',
        },
      },
    },
    defaultEdge: {
      type: 'quadratic',
      style: {
        stroke: isDark.value ? '#323848' : '#C8CDD4',
        lineWidth: 1,
        endArrow: { path: 'M 0,0 L 6,3 L 6,-3 Z', fill: isDark.value ? '#323848' : '#C8CDD4' },
      },
      labelCfg: {
        autoRotate: true,
        style: {
          fill: isDark.value ? '#8b8fa4' : '#999', fontSize: 9, opacity: 0,
          background: { fill: isDark.value ? '#12151c' : '#fff', padding: [1, 3, 1, 3], radius: 2 },
        },
      },
    },
    nodeStateStyles: {
      highlight: { stroke: '#c9a55a', lineWidth: 3, shadowBlur: 10, shadowColor: 'rgba(201,165,90,0.4)' },
      dim: { opacity: 0.3 },
    },
    edgeStateStyles: {
      highlight: { stroke: '#c9a55a', lineWidth: 2 },
      dim: { opacity: 0.15 },
    },
    animate: false,
  })

  // 点击节点
  graph.on('node:click', (evt: any) => {
    const model = evt.item?.getModel()
    if (model?.id) handleNodeClick(model.id)
  })

  // 点击画布取消选中
  graph.on('canvas:click', () => clearSelection())

  // 边 hover：显示/隐藏标签
  graph.on('edge:mouseenter', (evt: any) => {
    const item = evt.item
    if (item) graph.updateItem(item, { labelCfg: { style: { opacity: 1 } } })
  })
  graph.on('edge:mouseleave', (evt: any) => {
    const item = evt.item
    if (item) graph.updateItem(item, { labelCfg: { style: { opacity: 0 } } })
  })

  // 节点 hover：始终显示标签（即使缩放级别很低）
  graph.on('node:mouseenter', (evt: any) => {
    const item = evt.item
    if (item) graph.updateItem(item, { labelCfg: { style: { opacity: 1 } } })
  })
  graph.on('node:mouseleave', (evt: any) => {
    const item = evt.item
    if (item) updateNodeLabelsForZoom()
  })

  // 缩放感知：缩放低于阈值时隐藏节点标签
  let rafId: number | null = null
  graph.on('viewportchange', () => {
    if (rafId) cancelAnimationFrame(rafId)
    rafId = requestAnimationFrame(() => updateNodeLabelsForZoom())
  })

  window.addEventListener('resize', handleResize)
}

// ── 数据加载 ──
async function loadGraphData() {
  loading.value = true
  try {
    const [graphData, stats] = await Promise.all([
      fetchGraphData({
        limit: 100,
        entity_type: filterType.value || undefined,
        max_degree: maxDegree.value || undefined,
      }),
      fetchTypeStats(),
    ])
    allNodes.value = graphData.nodes
    allEdges.value = graphData.edges
    totalEntities.value = graphData.total_entities
    filteredCount.value = graphData.filtered_count ?? 0
    typeStats.value = stats
    renderGraph()
  } catch (e) {
    console.error('[KnowledgeGraph] 加载失败:', e)
  } finally {
    loading.value = false
  }
}

function buildNodeModel(n: EntityNode) {
  return {
    id: n.id,
    label: n.name,
    size: nodeSize(n.info_count),
    style: { fill: getTypeColor(n.entity_type) },
  }
}

function buildEdgeModel(e: EntityEdge, i: number, edgeType: string) {
  return {
    id: `e_${e.source}_${e.target}_${e.relationship_type}_${i}`,
    source: e.source,
    target: e.target,
    type: edgeType,
    label: getRelLabel(e.relationship_type),
  }
}

function renderGraph() {
  if (!graph) return

  // 高密度时用直线代替曲线，减少渲染开销
  const edgeType = allEdges.value.length > 500 ? 'line' : 'quadratic'

  const nodes = allNodes.value.map(n => buildNodeModel(n))
  const edges = allEdges.value.map((e, i) => buildEdgeModel(e, i, edgeType))

  graph.data({ nodes, edges })
  graph.render()
}

// ── 节点点击 ──
async function handleNodeClick(nodeId: string) {
  const node = allNodes.value.find(n => n.id === nodeId)
  if (!node) return

  selectedEntity.value = node
  entityDetail.value = null
  neighborNodes.value = []
  selectedEdges.value = []

  // 高亮
  if (graph) {
    graph.getNodes().forEach((n: any) => {
      graph.clearItemStates(n, ['highlight', 'dim'])
    })
    const item = graph.findById(nodeId)
    if (item) graph.setItemState(item, 'highlight', true)
  }

  try {
    const [detail, expandData] = await Promise.all([
      fetchEntityDetail(nodeId),
      expandEntity(nodeId, maxDegree.value || undefined),
    ])
    entityDetail.value = detail
    neighborNodes.value = expandData.neighbors
    selectedEdges.value = expandData.edges
  } catch (e) {
    console.error('[KnowledgeGraph] 加载详情失败:', e)
  }
}

// ── 展开 ──
async function handleExpandClick() {
  if (!selectedEntity.value || expanding.value) return
  await expandNode(selectedEntity.value.id)
}

async function expandNode(nodeId: string) {
  if (expandedIds.value.has(nodeId)) return
  expanding.value = true
  try {
    const result = await expandEntity(nodeId, maxDegree.value || undefined)
    const existingIds = new Set(allNodes.value.map(n => n.id))
    const newNodes = result.neighbors.filter(n => !existingIds.has(n.id))
    if (newNodes.length) allNodes.value.push(...newNodes)

    const edgeKeys = new Set(allEdges.value.map(e => `${e.source}-${e.target}-${e.relationship_type}`))
    const newEdges = result.edges.filter(e => !edgeKeys.has(`${e.source}-${e.target}-${e.relationship_type}`))
    if (newEdges.length) allEdges.value.push(...newEdges)

    expandedIds.value.add(nodeId)

    // 增量更新：只添加新节点/边，避免全量重渲染
    if (graph && (newNodes.length || newEdges.length)) {
      const edgeType = allEdges.value.length > 500 ? 'line' : 'quadratic'
      newNodes.forEach(n => {
        graph!.addItem('node', buildNodeModel(n))
      })
      const edgeOffset = allEdges.value.length - newEdges.length
      newEdges.forEach((e, i) => {
        graph!.addItem('edge', buildEdgeModel(e, edgeOffset + i, edgeType))
      })
      // 重新触发布局计算（仅对新节点）
      graph.refreshPositions()
    }
  } catch (e) {
    console.error('[KnowledgeGraph] 展开失败:', e)
  } finally {
    expanding.value = false
  }
}

// ── 搜索 ──
async function handleSearch() {
  if (!searchQuery.value.trim()) return
  try { searchResults.value = await searchEntities(searchQuery.value.trim()) }
  catch (e) { console.error('[KnowledgeGraph] 搜索失败:', e) }
}
function clearSearch() { searchQuery.value = ''; searchResults.value = [] }

function focusEntity(entityId: string) {
  searchResults.value = []
  const node = allNodes.value.find(n => n.id === entityId)
  if (node) {
    graph?.focusItem(entityId, true, { duration: 300 })
    handleNodeClick(entityId)
  } else {
    expandNode(entityId).then(() => {
      nextTick(() => {
        graph?.focusItem(entityId, true, { duration: 300 })
        handleNodeClick(entityId)
      })
    })
  }
}

function handleTypeFilter() { clearSelection(); loadGraphData() }
function toggleTypeFilter(type: string) { filterType.value = filterType.value === type ? '' : type; handleTypeFilter() }
function reloadGraph() { clearSelection(); loadGraphData() }
function fitView() { graph?.fitView(40) }

function clearSelection() {
  selectedEntity.value = null
  entityDetail.value = null
  neighborNodes.value = []
  selectedEdges.value = []
  if (graph) {
    graph.getNodes().forEach((n: any) => graph.clearItemStates(n, ['highlight', 'dim']))
    graph.getEdges().forEach((e: any) => graph.clearItemStates(e, ['highlight', 'dim']))
  }
}
function closeDetail() { clearSelection() }

function handleResize() {
  if (graph && graphContainer.value) {
    graph.changeSize(graphContainer.value.clientWidth, graphContainer.value.clientHeight)
    graph.fitView(40)
  }
}

onMounted(async () => {
  await nextTick()
  await initGraph()
  if (graph) loadGraphData()
})

// 主题切换时更新图谱颜色
watch(isDark, async () => {
  if (!graph) return
  const dark = isDark.value
  // 更新默认配置（影响后续新增节点/边）
  graph.set('defaultNode', {
    ...graph.get('defaultNode'),
    style: { stroke: dark ? '#12151c' : '#fff', lineWidth: 1.5, cursor: 'pointer' },
    labelCfg: { position: 'bottom', offset: 6, style: { fill: dark ? '#e2e4ea' : '#333', fontSize: 11, textBaseline: 'top' } },
  })
  graph.set('defaultEdge', {
    ...graph.get('defaultEdge'),
    style: { stroke: dark ? '#323848' : '#C8CDD4', lineWidth: 1, endArrow: { path: 'M 0,0 L 6,3 L 6,-3 Z', fill: dark ? '#323848' : '#C8CDD4' } },
    labelCfg: { autoRotate: true, style: { fill: dark ? '#8b8fa4' : '#999', fontSize: 9, opacity: 0, background: { fill: dark ? '#12151c' : '#fff', padding: [1, 3, 1, 3], radius: 2 } } },
  })
  // 更新已有节点/边
  graph.getNodes().forEach((node: any) => {
    graph.updateItem(node, {
      style: { stroke: dark ? '#12151c' : '#fff' },
      labelCfg: { style: { fill: dark ? '#e2e4ea' : '#333' } },
    })
  })
  graph.getEdges().forEach((edge: any) => {
    graph.updateItem(edge, {
      style: { stroke: dark ? '#323848' : '#C8CDD4', endArrow: { path: 'M 0,0 L 6,3 L 6,-3 Z', fill: dark ? '#323848' : '#C8CDD4' } },
      labelCfg: { style: { fill: dark ? '#8b8fa4' : '#999', background: { fill: dark ? '#12151c' : '#fff', padding: [1, 3, 1, 3], radius: 2 } } },
    })
  })
  graph.refreshPositions()
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (graph) { graph.destroy(); graph = null }
})
</script>

<style scoped>
.knowledge-graph-page { height: 100%; display: flex; flex-direction: column; background: var(--color-bg); overflow: hidden; }
.graph-toolbar { height: 56px; padding: 0 20px; display: flex; align-items: center; justify-content: space-between; background: var(--color-surface); border-bottom: 1px solid var(--border-default); flex-shrink: 0; gap: 16px; }
.toolbar-left { display: flex; align-items: center; gap: 12px; }
.toolbar-title { font-size: 16px; font-weight: 600; color: var(--text-primary); margin: 0; white-space: nowrap; }
.toolbar-center { position: relative; flex: 0 0 auto; }
.toolbar-right { display: flex; align-items: center; gap: 8px; }
.degree-control { display: flex; align-items: center; gap: 6px; }
.degree-label { font-size: 12px; color: var(--text-muted); white-space: nowrap; }
.filtered-hint { color: #e6a23c; font-size: 11px; }
.search-dropdown { position: absolute; top: 100%; left: 0; right: 0; background: var(--color-surface); border: 1px solid var(--border-default); border-radius: 4px; box-shadow: 0 4px 12px rgba(0,0,0,.1); z-index: 100; max-height: 320px; overflow-y: auto; margin-top: 4px; }
.search-item { padding: 8px 12px; display: flex; align-items: center; gap: 8px; cursor: pointer; transition: background .15s; }
.search-item:hover { background: var(--color-surface-hover); }
.search-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.search-name { flex: 1; font-size: 13px; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.search-count { font-size: 11px; color: var(--text-muted); white-space: nowrap; }
.graph-body { flex: 1; display: flex; overflow: hidden; position: relative; }
.graph-canvas-wrap { flex: 1; position: relative; overflow: hidden; }
.graph-container { width: 100%; height: 100%; }
.graph-loading, .graph-empty { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; z-index: 10; background: rgba(11,13,19,.85); color: var(--text-secondary); font-size: 14px; }
.graph-empty p { margin: 0; font-size: 14px; }
.empty-hint { color: var(--text-muted); font-size: 12px; }
.loading-spin { animation: spin 1s linear infinite; color: #409eff; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
.detail-panel { width: 340px; background: var(--color-surface); border-left: 1px solid var(--border-default); display: flex; flex-direction: column; overflow: hidden; flex-shrink: 0; }
.detail-header { padding: 16px 16px 12px; display: flex; align-items: center; gap: 8px; border-bottom: 1px solid var(--border-default); }
.detail-type-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
.detail-name { flex: 1; font-size: 15px; font-weight: 600; color: var(--text-primary); margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.detail-close { flex-shrink: 0; }
.detail-body { flex: 1; overflow-y: auto; padding: 16px; }
.detail-badges { display: flex; gap: 8px; margin-bottom: 16px; }
.detail-section { margin-bottom: 16px; }
.section-label { font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; margin-bottom: 8px; display: flex; align-items: center; gap: 6px; }
.alias-list { display: flex; flex-wrap: wrap; gap: 4px; }
.neighbor-loading { display: flex; align-items: center; justify-content: center; padding: 16px; }
.neighbor-list { display: flex; flex-direction: column; gap: 2px; }
.neighbor-item { padding: 6px 8px; border-radius: 4px; display: flex; align-items: center; gap: 8px; cursor: pointer; transition: background .15s; }
.neighbor-item:hover { background: var(--color-surface-hover); }
.neighbor-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.neighbor-name { flex: 1; font-size: 13px; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.neighbor-type { font-size: 11px; color: var(--text-muted); }
.neighbor-empty { font-size: 12px; color: var(--text-muted); text-align: center; padding: 12px; }
.relation-list { display: flex; flex-direction: column; gap: 4px; }
.relation-item { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.relation-desc { color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.meta-grid { display: flex; flex-direction: column; gap: 6px; }
.meta-item { display: flex; justify-content: space-between; font-size: 12px; }
.meta-label { color: var(--text-muted); }
.meta-value { color: var(--text-primary); font-weight: 500; }
.detail-actions { padding-top: 12px; border-top: 1px solid var(--border-default); }
.graph-legend { height: 40px; padding: 0 20px; background: var(--color-surface); border-top: 1px solid var(--border-default); display: flex; align-items: center; gap: 16px; flex-shrink: 0; overflow-x: auto; }
.legend-title { font-size: 11px; color: var(--text-muted); white-space: nowrap; font-weight: 600; }
.legend-items { display: flex; gap: 12px; overflow-x: auto; }
.legend-item { display: flex; align-items: center; gap: 4px; cursor: pointer; padding: 2px 6px; border-radius: 4px; transition: all .15s; white-space: nowrap; }
.legend-item:hover { background: var(--color-surface-hover); }
.legend-item.legend-active { background: rgba(91, 141, 239, 0.1); }
.legend-dot { width: 8px; height: 8px; border-radius: 50%; }
.legend-label { font-size: 11px; color: var(--text-secondary); }
.slide-right-enter-active, .slide-right-leave-active { transition: all .25s ease; }
.slide-right-enter-from, .slide-right-leave-to { transform: translateX(100%); opacity: 0; }
</style>
