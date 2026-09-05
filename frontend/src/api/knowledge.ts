import api from './index'
import type {
  GraphDataResponse,
  ExpandResponse,
  EntityDetail,
  EntitySearchResult,
  TypeStats,
  KBSearchResponse,
  KBRecordsResponse,
  KBTableName,
  MarketCognition,
  IndustryCognition,
  MacroReportSummary,
  MacroReport,
} from '@/types/knowledge'

/** 获取图谱初始数据 */
export function fetchGraphData(params?: {
  limit?: number
  entity_type?: string
  max_degree?: number | null
}): Promise<GraphDataResponse> {
  return api.get('/knowledge/graph-data', { params }).then(r => r.data)
}

/** 展开实体（获取邻居节点） */
export function expandEntity(entityId: string, maxDegree?: number | null): Promise<ExpandResponse> {
  return api.get(`/knowledge/entity/${entityId}/expand`, {
    params: maxDegree != null ? { max_degree: maxDegree } : undefined,
  }).then(r => r.data)
}

/** 获取实体详情 */
export function fetchEntityDetail(entityId: string): Promise<EntityDetail> {
  return api.get(`/knowledge/entity/${entityId}/detail`).then(r => r.data)
}

/** 搜索实体 */
export function searchEntities(q: string, limit = 20): Promise<EntitySearchResult[]> {
  return api.get('/knowledge/entity/search', { params: { q, limit } }).then(r => r.data)
}

/** 获取实体类型统计 */
export function fetchTypeStats(): Promise<TypeStats[]> {
  return api.get('/knowledge/type-stats').then(r => r.data)
}

/** 知识库健康检查 */
export function checkKnowledgeHealth(): Promise<{ kb_database: string }> {
  return api.get('/knowledge/health').then(r => r.data)
}

/** 知识库混合搜索（ILIKE + pgvector） */
export function searchKnowledge(params: {
  query: string
  tables?: KBTableName[]
  limit?: number
  embedding?: number[]
}): Promise<KBSearchResponse> {
  return api.post('/knowledge/search', params).then(r => r.data)
}

/** 按时间倒序浏览指定表的记录 */
export function fetchKBRecords(
  table: string,
  params?: { limit?: number; offset?: number }
): Promise<KBRecordsResponse> {
  return api.get(`/knowledge/records/${table}`, { params }).then(r => r.data)
}

/** 获取单条记录完整内容 */
export function fetchArticle(
  table: string,
  articleId: string
): Promise<Record<string, unknown>> {
  return api.get(`/knowledge/article/${table}/${articleId}`).then(r => r.data)
}

/** ── 经验沉淀 ── */

export function fetchMarketCognition(): Promise<MarketCognition> {
  return api.get('/knowledge/cognitions/market').then(r => r.data)
}

export function fetchIndustryCognitions(): Promise<IndustryCognition[]> {
  return api.get('/knowledge/cognitions/industries').then(r => r.data)
}

export function fetchIndustryCognition(sector: string): Promise<IndustryCognition> {
  return api.get(`/knowledge/cognitions/industry/${encodeURIComponent(sector)}`).then(r => r.data)
}

export function fetchMacroReports(limit = 20): Promise<MacroReportSummary[]> {
  return api.get('/knowledge/macro-reports', { params: { limit } }).then(r => r.data)
}

export function fetchMacroReport(version: number): Promise<MacroReport> {
  return api.get(`/knowledge/macro-reports/${version}`).then(r => r.data)
}
