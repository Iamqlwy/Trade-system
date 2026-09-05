/** 知识图谱 - 实体节点 */
export interface EntityNode {
  id: string
  name: string
  entity_type: string
  info_count: number
  aliases: string[] | null
  linked_node_id: string | null
}

/** 知识图谱 - 实体关系边 */
export interface EntityEdge {
  source: string
  target: string
  relationship_type: string
  strength: number | null
  description: string | null
}

/** 图谱数据响应 */
export interface GraphDataResponse {
  nodes: EntityNode[]
  edges: EntityEdge[]
  total_entities: number
  total_edges: number
  filtered_count: number
}

/** 展开实体响应 */
export interface ExpandResponse {
  center: EntityNode
  neighbors: EntityNode[]
  edges: EntityEdge[]
}

/** 实体详情 */
export interface EntityDetail {
  id: string
  name: string
  entity_type: string
  normalized_name: string
  aliases: string[] | null
  metadata_: Record<string, unknown> | null
  linked_node_id: string | null
  created_at: string | null
  info_count: number
  relationship_count: number
}

/** 搜索结果 */
export interface EntitySearchResult {
  id: string
  name: string
  entity_type: string
  info_count: number
  aliases: string[] | null
}

/** 实体类型统计 */
export interface TypeStats {
  entity_type: string
  count: number
}

/** ──────────────────────────────────────────────
 *  知识库搜索
 * ────────────────────────────────────────────── */

export type KBTableName =
  | 'raw_information'
  | 'analyses'
  | 'feedbacks'
  | 'nodes'

/** 节点状态数据（来自 node_states 表，搜索节点时附带在 extra.node_state 中） */
export interface NodeStateData {
  core_logic: string | null
  state_summary: string | null
  primary_drivers: Array<{ driver: string; strength: number; evidence_ids?: string[]; valid_until?: string | null }>
  risks: Array<{ risk: string; severity: string; evidence_ids?: string[]; valid_until?: string | null }>
  focus_points: Array<{ point: string; priority: string; evidence_ids?: string[] }>
  recent_changes: string | null
  uncertainty_flags: Array<Record<string, unknown>>
  key_evidence_ids: string[]
  version: number
  effective_from: string | null
}

/** 单条搜索结果 */
export interface KBSearchResultItem {
  id: string
  title: string
  snippet: string | null
  time: string | null
  score: number
  extra: Record<string, unknown>
}

/** 搜索响应 */
export interface KBSearchResponse {
  query: string
  results: Record<string, KBSearchResultItem[]>
  counts: Record<string, number>
}

/** 记录列表响应 */
export interface KBRecordsResponse {
  items: KBSearchResultItem[]
  total: number
  limit: number
  offset: number
}

/** Tab 配置 */
export interface KBTabConfig {
  key: KBTableName | 'all'
  label: string
  icon: string
  color: string
}

/** 实体类型颜色映射 */
export const ENTITY_TYPE_COLORS: Record<string, string> = {
  company: '#e74c3c',      // 公司 - 红色
  stock_code: '#e67e22',   // 股票代码 - 橙色
  sector: '#3498db',       // 行业 - 蓝色
  concept: '#9b59b6',      // 概念 - 紫色
  product: '#1abc9c',      // 产品 - 青绿
  policy: '#f39c12',       // 政策 - 金黄
  institution: '#2ecc71',  // 机构 - 绿色
  region: '#34495e',       // 地区 - 深灰
  person: '#e91e63',       // 人物 - 粉红
  upstream: '#00bcd4',     // 上游 - 青色
  downstream: '#ff5722',   // 下游 - 深橙
}

/** 实体类型中文名映射 */
export const ENTITY_TYPE_LABELS: Record<string, string> = {
  company: '公司',
  stock_code: '股票代码',
  sector: '行业',
  concept: '概念',
  product: '产品',
  policy: '政策',
  institution: '机构',
  region: '地区',
  person: '人物',
  upstream: '上游',
  downstream: '下游',
}

/** 关系类型中文名映射 */
export const RELATIONSHIP_TYPE_LABELS: Record<string, string> = {
  impacts: '影响',
  regulates: '监管',
  sanctions: '制裁',
  holds: '持有',
  part_of: '属于',
  supplies: '供应',
  competes_with: '竞争',
  substitutes: '替代',
  correlated_with: '相关',
  same_as: '同义',
}

/** 知识库搜索 Tab 配置 */
export const KB_TABS: KBTabConfig[] = [
  { key: 'all',              label: '全部',     icon: 'Grid',         color: '#409eff' },
  { key: 'raw_information',  label: '原始信息', icon: 'Document',     color: '#e74c3c' },
  { key: 'analyses',         label: '分析报告', icon: 'DataAnalysis', color: '#e67e22' },
  { key: 'feedbacks',        label: '复盘',     icon: 'ChatDotRound', color: '#9b59b6' },
  { key: 'nodes',            label: '知识节点', icon: 'Share',        color: '#3498db' },
]

/** 表名 → 中文标签 */
export const KB_TABLE_LABELS: Record<KBTableName, string> = {
  raw_information: '原始信息',
  analyses:        '分析报告',
  feedbacks:       '复盘',
  nodes:           '知识节点',
}

/** 表名 → 主题色 */
export const KB_TABLE_COLORS: Record<KBTableName, string> = {
  raw_information: '#e74c3c',
  analyses:        '#e67e22',
  feedbacks:       '#9b59b6',
  nodes:           '#3498db',
}

/** ──────────────────────────────────────────────
 *  经验沉淀
 * ────────────────────────────────────────────── */

export interface MarketCognition {
  id: string | null
  cognition_text: string
  append_count: number
  created_at: string | null
  updated_at: string | null
}

export interface IndustryCognition {
  id: string
  sector: string
  cognition_text: string
  append_count: number
  created_at: string | null
  updated_at: string | null
}

export interface MacroReportSummary {
  id: string
  version: number
  summary: string
  changed_sections: string[]
  created_at: string | null
  updated_at: string | null
}

export interface MacroReport extends MacroReportSummary {
  content: string
}
