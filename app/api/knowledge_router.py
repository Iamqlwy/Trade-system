"""
知识库图谱 API —— 为前端知识图谱可视化与知识搜索提供数据

所有端点只读访问知识库 PostgreSQL 数据库。
注意：psycopg2 对 PostgreSQL UUID 列自动返回 Python UUID 对象。
"""
import logging
from datetime import datetime, timezone
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from ..auth.dependencies import require_api_token
from ..config import settings
from ..store.kb_database import kb_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

# ── Elasticsearch 配置 ────────────────────────────────────────────

_ES_PREFIX = "quant_kb"
_ES_TIMEOUT = 10.0   # 秒

# 表名 → ES 索引名（无映射则回退 ILIKE）
_TABLE_ES_INDEX: dict[str, str] = {
    "raw_information": f"{_ES_PREFIX}_raw_info",
    "analyses":        f"{_ES_PREFIX}_analyses",
    "feedbacks":       f"{_ES_PREFIX}_feedbacks",
    "nodes":           f"{_ES_PREFIX}_nodes",
}

# 表名 → ES 可搜索字段
_TABLE_ES_FIELDS: dict[str, list[str]] = {
    "raw_information": ["title", "body", "source"],
    "analyses":        ["title", "content"],
    "feedbacks":       ["title", "lessons_learned", "error_reason", "adjustment_suggestions"],
    "nodes":           ["name", "description"],
}

# 表名 → ES _source 返回字段（用于 snippet / 时间权）
_TABLE_ES_SOURCE: dict[str, list[str]] = {
    "raw_information": ["pg_id", "title", "body", "source", "published_at", "created_at"],
    "analyses":        ["pg_id", "title", "content", "created_at"],
    "feedbacks":       ["pg_id", "title", "lessons_learned", "created_at"],
    "nodes":           ["pg_id", "name", "description"],
}

# ── Embedding 配置 ────────────────────────────────────────────────

_EMBED_BATCH_SIZE = 25   # 每批 25 条（SiliconFlow 限制内）


async def _generate_embedding(text_input: str | list[str]) -> list[float] | list[list[float]]:
    """
    通过 SiliconFlow API 生成文本 embedding。
    传入 str 返回 list[float]；传入 list[str] 返回 list[list[float]]（分批，每批 ≤25）。
    """
    if not settings.embedding_enabled:
        return [] if isinstance(text_input, list) else []

    texts = [text_input] if isinstance(text_input, str) else text_input
    api_key = settings.embedding_api_key
    base_url = settings.embedding_base_url.rstrip("/")
    model = settings.embedding_model

    all_embeddings: list[list[float]] = []

    with httpx.Client(timeout=30.0) as client:
        for i in range(0, len(texts), _EMBED_BATCH_SIZE):
            batch = texts[i:i + _EMBED_BATCH_SIZE]
            try:
                resp = client.post(
                    f"{base_url}/embeddings",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model,
                        "input": batch,
                        "dimensions": settings.embedding_dimension,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                items = sorted(data["data"], key=lambda x: x["index"])
                all_embeddings.extend([it["embedding"] for it in items])
            except Exception as e:
                logger.warning("Embedding API 失败 batch[%d:%d]: %s", i, i + len(batch), e)
                all_embeddings.extend([[] for _ in batch])

    if isinstance(text_input, str):
        return all_embeddings[0] if all_embeddings else []
    return all_embeddings

# ── 搜索：表名 → 可搜索文本字段 ────────────────────────────────

_TABLE_TEXT_FIELDS: dict[str, list[str]] = {
    "raw_information": ["title", "body", "source"],
    "analyses":        ["title", "content"],
    "feedbacks":       ["title", "lessons_learned", "error_reason", "expected_outcome", "actual_outcome"],
    "nodes":           ["name", "description"],
}

_VALID_TABLES = set(_TABLE_TEXT_FIELDS.keys())

# 有 embedding 列、可做向量搜索的表（world_nodes 无 embedding 列）
_HAS_EMBEDDING: set[str] = {"raw_information", "analyses", "feedbacks"}

# 安全表名映射：只允许白名单中的表名，防止 SQL 注入
# key = API 传入的逻辑名, value = 实际 PostgreSQL 表名
_PG_TABLE_MAP: dict[str, str] = {
    "raw_information": "raw_information",
    "analyses": "analyses",
    "feedbacks": "feedbacks",
    "nodes": "world_nodes",
}


def _safe_pg_table(table_name: str) -> str:
    """将逻辑表名映射为实际 PostgreSQL 表名。

    只允许白名单中的表名，非法表名抛出 ValueError。
    返回值直接来自硬编码映射，不存在注入风险。
    """
    pg_table = _PG_TABLE_MAP.get(table_name)
    if pg_table is None:
        raise ValueError(f"非法表名: {table_name}，合法值: {sorted(_PG_TABLE_MAP)}")
    return pg_table

# ── 搜索：各表的 snippet / 标题字段 ─────────────────────────────

_TABLE_SNIPPET_FIELDS: dict[str, list[str]] = {
    "raw_information": ["body", "source", "title"],
    "analyses":        ["content", "title"],
    "feedbacks":       ["lessons_learned", "error_reason", "title"],
    "nodes":           ["description", "name"],
}

_TABLE_TITLE_FIELDS: dict[str, str] = {
    "raw_information": "title",
    "analyses":        "title",
    "feedbacks":       "title",
    "nodes":           "name",
}

# ── 响应模型 ────────────────────────────────

class EntityNode(BaseModel):
    id: str
    name: str
    entity_type: str
    info_count: int = 0
    aliases: list[str] | None = None
    linked_node_id: str | None = None

class EntityEdge(BaseModel):
    source: str
    target: str
    relationship_type: str
    strength: float | None = None
    description: str | None = None

class GraphDataResponse(BaseModel):
    nodes: list[EntityNode]
    edges: list[EntityEdge]
    total_entities: int
    total_edges: int
    filtered_count: int = 0

class EntityDetail(BaseModel):
    id: str
    name: str
    entity_type: str
    normalized_name: str
    aliases: list[str] | None = None
    metadata_: dict | None = None
    linked_node_id: str | None = None
    created_at: str | None = None
    info_count: int = 0
    relationship_count: int = 0

class ExpandResponse(BaseModel):
    center: EntityNode
    neighbors: list[EntityNode]
    edges: list[EntityEdge]

class SearchResult(BaseModel):
    id: str
    name: str
    entity_type: str
    info_count: int
    aliases: list[str] | None = None

class TypeStats(BaseModel):
    entity_type: str
    count: int


class NodeStateData(BaseModel):
    """知识节点的当前状态数据（来自 node_states 表）"""
    core_logic: str | None = None
    state_summary: str | None = None
    primary_drivers: list[dict] | None = None
    risks: list[dict] | None = None
    focus_points: list[dict] | None = None
    recent_changes: str | None = None
    uncertainty_flags: list[dict] | None = None
    key_evidence_ids: list[str] | None = None
    version: int = 0
    effective_from: str | None = None


# ── 辅助：安全转字符串 ─────────────────────

def _s(val) -> str | None:
    """将 UUID / 任意值安全转为字符串，None 返回 None"""
    if val is None:
        return None
    return str(val)


def _get_current_states(session, node_ids: list[str]) -> dict[str, dict]:
    """批量获取节点的当前状态（effective_to IS NULL 即当前版本），返回 {node_id: state_dict}"""
    if not node_ids:
        return {}
    sql = text("""
        SELECT node_id, core_logic, state_summary, primary_drivers,
               risks, focus_points, recent_changes, uncertainty_flags,
               key_evidence_ids, version, effective_from
        FROM node_states
        WHERE node_id = ANY(:ids) AND effective_to IS NULL
    """)
    rows = session.execute(sql, {"ids": [UUID(nid) for nid in node_ids]}).fetchall()
    result = {}
    for row in rows:
        nid = str(row.node_id)
        result[nid] = {
            "core_logic": row.core_logic,
            "state_summary": row.state_summary,
            "primary_drivers": row.primary_drivers or [],
            "risks": row.risks or [],
            "focus_points": row.focus_points or [],
            "recent_changes": row.recent_changes,
            "uncertainty_flags": row.uncertainty_flags or [],
            "key_evidence_ids": [str(e) for e in (row.key_evidence_ids or [])],
            "version": int(row.version or 0),
            "effective_from": _format_dt(row.effective_from),
        }
    return result


# ── 图谱主数据 ─────────────────────────────

@router.get("/graph-data", response_model=GraphDataResponse)
async def get_graph_data(
    limit: int = Query(200, ge=50, le=500, description="加载的实体数量上限"),
    entity_type: str | None = Query(None, description="按实体类型筛选"),
    max_degree: int | None = Query(
        50, ge=1,
        description="最大关系度数，过滤掉连接过多的超级节点（如'中国'）。设为 null 则不过滤",
    ),
    _user: dict = Depends(require_api_token),
):
    """
    获取知识图谱初始数据：按新闻关联数排序的 Top N 实体 + 它们之间的关系。
    可选过滤关系度过高的 hub 节点（类似停用词），让图谱展示更有意义的关联。
    """
    with kb_session() as session:
        type_where = ""
        params: dict = {"limit": limit}
        if entity_type:
            type_where = "WHERE e.entity_type = :entity_type"
            params["entity_type"] = entity_type

        # 按 info_count 排序选取候选实体
        # 子查询计算每个实体的关系度数（degree），HAVING 过滤掉 hub 节点
        degree_having = ""
        if max_degree is not None:
            degree_having = "HAVING (SELECT COUNT(*) FROM entity_relationships er WHERE er.source_entity_id = e.id OR er.target_entity_id = e.id) <= :max_degree"
            params["max_degree"] = max_degree

        entities_sql = text(f"""
            SELECT sub.id, sub.name, sub.entity_type, sub.aliases, sub.linked_node_id,
                   sub.info_count
            FROM (
                SELECT
                    e.id, e.name, e.entity_type, e.aliases, e.linked_node_id,
                    COUNT(ie.id) AS info_count
                FROM entities e
                LEFT JOIN information_entities ie ON ie.entity_id = e.id
                {type_where}
                GROUP BY e.id, e.name, e.entity_type, e.aliases, e.linked_node_id
                {degree_having}
                ORDER BY info_count DESC
                LIMIT :limit
            ) sub
        """)

        rows = session.execute(entities_sql, params).fetchall()

        if not rows:
            return GraphDataResponse(
                nodes=[], edges=[], total_entities=0, total_edges=0, filtered_count=0,
            )

        entity_ids = [row.id for row in rows]

        nodes = [
            EntityNode(
                id=str(row.id),
                name=row.name,
                entity_type=row.entity_type,
                info_count=row.info_count,
                aliases=row.aliases or [],
                linked_node_id=_s(row.linked_node_id),
            )
            for row in rows
        ]

        # 查询这些实体之间的关系（UUID 对象直接传给 ANY）
        # 按 strength 排序并限制数量，防止密集连接导致前端卡顿
        edges_sql = text("""
            SELECT er.source_entity_id, er.target_entity_id,
                   er.relationship_type, er.strength, er.description
            FROM entity_relationships er
            WHERE er.source_entity_id = ANY(:entity_ids)
              AND er.target_entity_id = ANY(:entity_ids)
            ORDER BY er.strength DESC NULLS LAST
            LIMIT 1500
        """)

        edge_rows = session.execute(edges_sql, {"entity_ids": entity_ids}).fetchall()
        edges = [
            EntityEdge(
                source=str(er.source_entity_id),
                target=str(er.target_entity_id),
                relationship_type=er.relationship_type,
                strength=er.strength,
                description=er.description,
            )
            for er in edge_rows
        ]

        # 统计总数（同样应用 degree 过滤，使 "节点 X / Y" 准确）
        total_sql = text(f"""
            SELECT COUNT(*) FROM (
                SELECT e.id
                FROM entities e
                LEFT JOIN information_entities ie ON ie.entity_id = e.id
                {type_where}
                GROUP BY e.id, e.name, e.entity_type, e.aliases, e.linked_node_id
                {degree_having}
            ) sub
        """)
        total_entities = int(session.execute(total_sql, params).scalar() or 0)

        # 计算被过滤的 hub 节点数量
        filtered_count = 0
        if max_degree is not None:
            all_count_sql = text(f"""
                SELECT COUNT(*) FROM (
                    SELECT e.id
                    FROM entities e
                    LEFT JOIN information_entities ie ON ie.entity_id = e.id
                    {type_where}
                    GROUP BY e.id, e.name, e.entity_type, e.aliases, e.linked_node_id
                ) sub
            """)
            all_count = int(session.execute(all_count_sql, params).scalar() or 0)
            filtered_count = all_count - total_entities

        return GraphDataResponse(
            nodes=nodes, edges=edges,
            total_entities=total_entities, total_edges=len(edges),
            filtered_count=filtered_count,
        )


# ── 点击展开 ───────────────────────────────

@router.get("/entity/{entity_id}/expand", response_model=ExpandResponse)
async def expand_entity(
    entity_id: str,
    max_degree: int | None = Query(
        50, ge=1,
        description="最大关系度数，过滤掉 hub 邻居节点",
    ),
    _user: dict = Depends(require_api_token),
):
    """展开实体：返回该实体的直接邻居（一度关系）。"""
    with kb_session() as session:
        # 1. 中心实体
        center_sql = text("""
            SELECT e.id, e.name, e.entity_type, e.aliases, e.linked_node_id,
                   COUNT(ie.id) AS info_count
            FROM entities e
            LEFT JOIN information_entities ie ON ie.entity_id = e.id
            WHERE e.id = :entity_id
            GROUP BY e.id, e.name, e.entity_type, e.aliases, e.linked_node_id
        """)
        center_row = session.execute(center_sql, {"entity_id": entity_id}).fetchone()
        if not center_row:
            raise HTTPException(404, f"实体 {entity_id} 不存在")

        center = EntityNode(
            id=str(center_row.id),
            name=center_row.name,
            entity_type=center_row.entity_type,
            info_count=center_row.info_count,
            aliases=center_row.aliases or [],
            linked_node_id=_s(center_row.linked_node_id),
        )

        # 2. 所有关系（限制数量防止单个 hub 节点展开导致卡顿）
        rels_sql = text("""
            SELECT er.source_entity_id, er.target_entity_id,
                   er.relationship_type, er.strength, er.description
            FROM entity_relationships er
            WHERE er.source_entity_id = :entity_id
               OR er.target_entity_id = :entity_id
            ORDER BY er.strength DESC NULLS LAST
            LIMIT 100
        """)
        rel_rows = session.execute(rels_sql, {"entity_id": entity_id}).fetchall()

        if not rel_rows:
            return ExpandResponse(center=center, neighbors=[], edges=[])

        # 3. 收集邻居 UUID（排除 hub 节点）
        neighbor_ids = []
        seen = {entity_id}
        for r in rel_rows:
            for raw_id in (r.source_entity_id, r.target_entity_id):
                uid_str = str(raw_id)
                if uid_str != entity_id and uid_str not in seen:
                    neighbor_ids.append(raw_id)  # 保持 UUID 对象
                    seen.add(uid_str)

        # 4. 批量获取邻居实体 + 度数，过滤掉 hub 节点
        if not neighbor_ids:
            return ExpandResponse(center=center, neighbors=[], edges=[])

        neighbors_sql = text("""
            SELECT e.id, e.name, e.entity_type, e.aliases, e.linked_node_id,
                   COUNT(ie.id) AS info_count,
                   (SELECT COUNT(*) FROM entity_relationships er2
                    WHERE er2.source_entity_id = e.id OR er2.target_entity_id = e.id
                   ) AS degree
            FROM entities e
            LEFT JOIN information_entities ie ON ie.entity_id = e.id
            WHERE e.id = ANY(:neighbor_ids)
            GROUP BY e.id, e.name, e.entity_type, e.aliases, e.linked_node_id
        """)
        neighbor_rows = session.execute(
            neighbors_sql, {"neighbor_ids": neighbor_ids}
        ).fetchall()

        neighbors = [
            EntityNode(
                id=str(nr.id),
                name=nr.name,
                entity_type=nr.entity_type,
                info_count=nr.info_count,
                aliases=nr.aliases or [],
                linked_node_id=_s(nr.linked_node_id),
            )
            for nr in neighbor_rows
            if max_degree is None or nr.degree <= max_degree
        ]

        # 只保留连接到非 hub 邻居的边
        kept_ids = {n.id for n in neighbors}
        edges = [
            EntityEdge(
                source=str(r.source_entity_id),
                target=str(r.target_entity_id),
                relationship_type=r.relationship_type,
                strength=r.strength,
                description=r.description,
            )
            for r in rel_rows
            # 保留：源或目标是中心节点，且另一端是保留的邻居
            if (str(r.source_entity_id) == entity_id and str(r.target_entity_id) in kept_ids)
            or (str(r.target_entity_id) == entity_id and str(r.source_entity_id) in kept_ids)
        ]

        return ExpandResponse(center=center, neighbors=neighbors, edges=edges)


# ── 实体详情 ───────────────────────────────

@router.get("/entity/{entity_id}/detail", response_model=EntityDetail)
async def get_entity_detail(
    entity_id: str,
    _user: dict = Depends(require_api_token),
):
    """获取单个实体的详细信息"""
    with kb_session() as session:
        detail_sql = text("""
            SELECT e.id, e.name, e.entity_type, e.normalized_name,
                   e.aliases, e.metadata, e.linked_node_id, e.created_at,
                   COUNT(DISTINCT ie.id) AS info_count,
                   (SELECT COUNT(*) FROM entity_relationships er
                    WHERE er.source_entity_id = e.id OR er.target_entity_id = e.id
                   ) AS relationship_count
            FROM entities e
            LEFT JOIN information_entities ie ON ie.entity_id = e.id
            WHERE e.id = :entity_id
            GROUP BY e.id, e.name, e.entity_type, e.normalized_name,
                     e.aliases, e.metadata, e.linked_node_id, e.created_at
        """)
        row = session.execute(detail_sql, {"entity_id": entity_id}).fetchone()
        if not row:
            raise HTTPException(404, f"实体 {entity_id} 不存在")

        return EntityDetail(
            id=str(row.id),
            name=row.name,
            entity_type=row.entity_type,
            normalized_name=row.normalized_name,
            aliases=row.aliases or [],
            metadata_=row.metadata,
            linked_node_id=_s(row.linked_node_id),
            created_at=_s(row.created_at),
            info_count=row.info_count,
            relationship_count=int(row.relationship_count),
        )


# ── 搜索实体 ───────────────────────────────

@router.get("/entity/search", response_model=list[SearchResult])
async def search_entities(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    limit: int = Query(20, ge=1, le=100),
    _user: dict = Depends(require_api_token),
):
    """模糊搜索实体（按名称/别名匹配）"""
    with kb_session() as session:
        search_sql = text("""
            SELECT e.id, e.name, e.entity_type, e.aliases,
                   COUNT(DISTINCT ie.id) AS info_count
            FROM entities e
            LEFT JOIN information_entities ie ON ie.entity_id = e.id
            WHERE e.name ILIKE :pattern
               OR e.normalized_name ILIKE :pattern
               OR e.aliases::text ILIKE :pattern
            GROUP BY e.id, e.name, e.entity_type, e.aliases
            ORDER BY info_count DESC
            LIMIT :limit
        """)
        pattern = f"%{q}%"
        rows = session.execute(search_sql, {"pattern": pattern, "limit": limit}).fetchall()

        return [
            SearchResult(
                id=str(r.id),
                name=r.name,
                entity_type=r.entity_type,
                info_count=r.info_count,
                aliases=r.aliases or [],
            )
            for r in rows
        ]


# ── 实体类型统计 ────────────────────────────

@router.get("/type-stats", response_model=list[TypeStats])
async def get_type_stats(
    _user: dict = Depends(require_api_token),
):
    """获取各实体类型的数量统计"""
    with kb_session() as session:
        sql = text("""
            SELECT entity_type, COUNT(*) AS count
            FROM entities GROUP BY entity_type ORDER BY count DESC
        """)
        rows = session.execute(sql).fetchall()
        return [TypeStats(entity_type=r.entity_type, count=int(r.count)) for r in rows]


# ── 健康检查 ────────────────────────────────

@router.get("/health")
async def knowledge_health(
    _user: dict = Depends(require_api_token),
):
    """检查知识库数据库连接状态"""
    from ..store.kb_database import check_kb_health
    pg_ok = check_kb_health()

    es_ok = False
    try:
        with httpx.Client(timeout=3.0) as client:
            r = client.get(f"{settings.es_url}/_cluster/health")
            es_ok = r.status_code == 200
    except Exception:
        pass

    return {
        "kb_database": "connected" if pg_ok else "disconnected",
        "elasticsearch": "connected" if es_ok else "disconnected",
    }


# ── 知识库搜索 ────────────────────────────────

class KBSearchRequest(BaseModel):
    query: str
    tables: list[str] = ["raw_information", "analyses", "feedbacks", "nodes"]
    limit: int = 100
    embedding: list[float] | None = None


class KBSearchResultItem(BaseModel):
    id: str
    title: str
    snippet: str | None = None
    time: str | None = None
    score: float
    extra: dict = {}


def _extract_str(row, names: list[str]) -> str:
    """从 row 中按字段名顺序拼接所有非空字符串（取前 2000 字符供 snippet 截取）"""
    parts = []
    for name in names:
        val = getattr(row, name, None)
        if val:
            parts.append(str(val))
    combined = "\n".join(parts)
    return combined[:2000] if combined else ""


def _extract_time(row) -> str | None:
    """从 row 中提取时间字段并格式化为 ISO 字符串"""
    for name in ("published_at", "created_at", "updated_at"):
        val = getattr(row, name, None)
        if val is not None and isinstance(val, datetime):
            return val.astimezone(timezone.utc).isoformat()
    return None


import re as _re


def _extract_snippet(text: str, query: str, ctx: int = 140) -> str:
    """从文本中找到 query 关键词位置，截取前后各 ctx 字符作为摘要。
    找不到则返回前 300 字符。总长度不超过 300 字符。"""
    if not text:
        return ""
    words = query.strip().split()
    if not words:
        return text[:300] + ("..." if len(text) > 300 else "")

    lower_text = text.lower()
    best_pos = -1
    for w in words:
        pos = lower_text.find(w.lower())
        if pos >= 0 and (best_pos < 0 or pos < best_pos):
            best_pos = pos

    if best_pos < 0:
        return text[:300] + ("..." if len(text) > 300 else "")

    start = max(0, best_pos - ctx)
    end = min(len(text), best_pos + len(words[0]) + ctx)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


# 各表是否有 published_at 列
_HAS_PUBLISHED_AT = {"raw_information"}

# ── 时间衰减（弱权）─────────────────────────────────────────────
# 衰减因子 0.002：30天 ≈ 0.94，90天 ≈ 0.83，180天 ≈ 0.70，1年 ≈ 0.48
_TIME_DECAY = 0.002


def _time_weight(row) -> float:
    """根据记录时间计算弱时间权重（0~1，越新越高）—— 用于 PG row 对象"""
    for name in ("published_at", "created_at"):
        val = getattr(row, name, None)
        if val is not None and isinstance(val, datetime):
            age_days = max(0.0, (datetime.now(timezone.utc) - val).total_seconds() / 86400)
            return max(0.3, 1.0 - _TIME_DECAY * age_days)
    return 0.7   # 无时间字段时给一个中性值


def _time_weight_from_iso(time_str: str | None) -> float:
    """根据 ISO 时间字符串计算弱时间权重 —— 用于 ES doc"""
    if not time_str:
        return 0.7
    try:
        t = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (datetime.now(timezone.utc) - t).total_seconds() / 86400)
        return max(0.3, 1.0 - _TIME_DECAY * age_days)
    except Exception:
        return 0.7


def _search_table_es(table: str, query: str, limit: int) -> list[dict] | None:
    """Elasticsearch BM25 搜索（IK 分词），用于有 ES 索引的表。
    返回 None 表示 ES 不可用，调用方应回退到 ILIKE。"""
    index = _TABLE_ES_INDEX[table]
    fields = _TABLE_ES_FIELDS[table]
    source_fields = _TABLE_ES_SOURCE[table]

    body = {
        "query": {
            "multi_match": {
                "query": query,
                "fields": fields,
                "type": "best_fields",
                "fuzziness": "AUTO",
            }
        },
        "size": limit,
        "_source": source_fields,
        "highlight": {
            "fields": {f: {"fragment_size": 800, "number_of_fragments": 1} for f in fields},
            "pre_tags": [""],
            "post_tags": [""],
        },
    }

    try:
        with httpx.Client(timeout=_ES_TIMEOUT) as client:
            resp = client.post(f"{settings.es_url}/{index}/_search", json=body)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("ES 搜索失败 index=%s: %s → 回退 ILIKE", index, e)
        return None   # 返回 None 表示调用方需回退到 ILIKE

    hits = data.get("hits", {}).get("hits", [])
    highlights = {}  # pg_id → highlighted snippet
    results = []
    for hit in hits:
        src = hit.get("_source", {})
        pg_id = src.get("pg_id")
        if not pg_id:
            continue

        # 提取标题
        title_field = _TABLE_TITLE_FIELDS[table]
        title = str(src.get(title_field, ""))[:200]

        # 提取 snippet：从 source 字段智能截取（不依赖 ES highlight，避免命中 title 字段导致 snippet 过短）
        parts = []
        for key in ("body", "content", "lessons_learned", "description", "source", "state_summary", "core_logic"):
            val = src.get(key)
            if val:
                parts.append(str(val))
        snippet = _extract_snippet("\n".join(parts), query) if parts else ""

        # 时间
        time_str = src.get("published_at") or src.get("created_at")

        # 分数 + 时间权
        es_score = float(hit.get("_score", 0))
        norm_score = es_score / (es_score + 10.0)   # 归一化到 0~1
        tw = _time_weight_from_iso(time_str)

        results.append({
            "id": str(pg_id),
            "title": title,
            "snippet": snippet,
            "time": time_str,
            "score": round(norm_score * tw, 4),
            "_tw": tw,
        })

    return results


def _search_table_ilike(session, table: str, query: str, limit: int) -> list[dict]:
    """ILIKE 全文搜索，返回 [{id, title, snippet, time, score}]"""
    fields = _TABLE_TEXT_FIELDS[table]
    title_field = _TABLE_TITLE_FIELDS[table]
    snippet_fields = _TABLE_SNIPPET_FIELDS[table]
    pg_table = _safe_pg_table(table)

    pub_col = "published_at" if table in _HAS_PUBLISHED_AT else "NULL::timestamptz AS published_at"
    or_clause = " OR ".join(f"{f} ILIKE :pattern" for f in fields)
    sql = text(f"""
        SELECT id, {", ".join(fields)}, created_at,
               {title_field} AS _title,
               {pub_col}
        FROM {pg_table}
        WHERE {or_clause}
        ORDER BY created_at DESC
        LIMIT :limit
    """)

    rows = session.execute(sql, {"pattern": f"%{query}%", "limit": limit}).fetchall()

    results = []
    for i, row in enumerate(rows):
        # 智能 snippet：找 query 关键词在正文中的位置，截取前后 200 字
        raw_text = _extract_str(row, snippet_fields)
        snippet = _extract_snippet(raw_text, query)
        title = getattr(row, "_title", None) or ""
        base_score = 1.0 - i * 0.005
        tw = _time_weight(row)
        results.append({
            "id": str(row.id),
            "title": str(title)[:200],
            "snippet": snippet,
            "time": _extract_time(row),
            "score": round(base_score * tw, 4),
            "_tw": tw,
        })
    return results


def _search_table_vector(
    session, table: str, embedding: list[float], query: str, limit: int
) -> list[dict]:
    """pgvector 向量搜索，返回 [{id, title, snippet, time, score}]"""
    title_field = _TABLE_TITLE_FIELDS[table]
    snippet_fields = _TABLE_SNIPPET_FIELDS[table]
    pg_table = _safe_pg_table(table)

    pub_col = "published_at" if table in _HAS_PUBLISHED_AT else "NULL::timestamptz AS published_at"
    # pgvector 要求传入字符串格式 '[0.1, 0.2, ...]'，再 CAST 为 vector
    emb_str = "[" + ",".join(str(v) for v in embedding) + "]"
    sql = text(f"""
        SELECT id, {title_field} AS _title,
               {", ".join(snippet_fields)},
               created_at, {pub_col},
               embedding <=> CAST(:emb AS vector) AS distance
        FROM {pg_table}
        WHERE embedding IS NOT NULL
        ORDER BY distance ASC
        LIMIT :limit
    """)

    rows = session.execute(sql, {"emb": emb_str, "limit": limit}).fetchall()

    results = []
    for i, row in enumerate(rows):
        raw_text = _extract_str(row, snippet_fields)
        snippet = _extract_snippet(raw_text, query)
        title = getattr(row, "_title", None) or ""
        base_score = 1.0 / (1.0 + float(row.distance))
        tw = _time_weight(row)
        results.append({
            "id": str(row.id),
            "title": str(title)[:200],
            "snippet": snippet,
            "time": _extract_time(row),
            "score": round(base_score * tw, 4),
            "_tw": tw,
        })
    return results


def _rrf_merge(
    ilike_results: list[dict], vector_results: list[dict], limit: int, k: int = 60
) -> list[dict]:
    """Reciprocal Rank Fusion 合并两路搜索结果，最终乘以时间权"""
    scores: dict[str, float] = {}
    id_to_item: dict[str, dict] = {}

    for rank, item in enumerate(ilike_results):
        rid = item["id"]
        scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + rank)
        id_to_item[rid] = item

    for rank, item in enumerate(vector_results):
        rid = item["id"]
        scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + rank)
        if rid not in id_to_item:
            id_to_item[rid] = item

    merged = []
    for rid, rrf_score in sorted(scores.items(), key=lambda x: -x[1])[:limit]:
        tw = id_to_item[rid].get("_tw", 0.7)
        final_score = round(rrf_score * tw, 4)
        item = {k: v for k, v in id_to_item[rid].items() if k != "_tw"}
        item["score"] = final_score
        merged.append(item)
    return merged


# ── 低分淘汰 ──────────────────────────────────────────────────────
# 自适应阈值：保留 score >= max(最高分×15%, 0.005) 的结果
_SCORE_RATIO = 0.15
_SCORE_FLOOR = 0.005


def _filter_by_score(items: list[dict]) -> list[dict]:
    """淘汰分数过低的结果。阈值为最高分的 15%，最低不低于 0.005"""
    if not items:
        return items
    top = max(it["score"] for it in items)
    threshold = max(top * _SCORE_RATIO, _SCORE_FLOOR)
    return [it for it in items if it["score"] >= threshold]


@router.post("/search")
async def knowledge_search(
    req: KBSearchRequest,
    _user: dict = Depends(require_api_token),
):
    """
    知识库全文 + 向量混合搜索。

    每张表独立搜索，结果按表分组返回，前端用 Tab 分别展示。
    前端一次获取所有结果（每表最多 limit 条），本地翻页无需重复搜索。

    向量搜索：
      - 前端直接传 embedding → 使用前端传入的向量
      - 前端未传 embedding → 后端自动调 SiliconFlow API 生成 query embedding
      - embedding API 未配置 → 跳过向量搜索，仅用 BM25
    """
    invalid = [t for t in req.tables if t not in _VALID_TABLES]
    if invalid:
        raise HTTPException(400, f"非法表名: {invalid}，合法值: {sorted(_VALID_TABLES)}")

    # ── 自动生成 query embedding（若前端未提供且 API 已配置）──
    query_embedding: list[float] | None = req.embedding or None
    if not query_embedding and settings.embedding_enabled:
        emb = await _generate_embedding(req.query)
        # 单条文本输入 → emb 为 list[float]；运行时保证类型正确
        if isinstance(emb, list) and emb and isinstance(emb[0], float):
            query_embedding = emb  # type: ignore[assignment]
        else:
            logger.warning("Query embedding 生成失败或维度不符，跳过向量搜索")

    results_by_table: dict[str, list[KBSearchResultItem]] = {}

    with kb_session() as session:
        for table in req.tables:

            # ── 全文搜索：优先 ES，无 ES 索引或 ES 失败则回退 ILIKE ──
            if table in _TABLE_ES_INDEX:
                text_results = _search_table_es(table, req.query, req.limit)
                if text_results is None:
                    # ES 不可用，回退
                    text_results = _search_table_ilike(session, table, req.query, req.limit)
            else:
                text_results = _search_table_ilike(session, table, req.query, req.limit)

            # ── 向量搜索（仅对有 embedding 列的表）──
            if query_embedding and table in _HAS_EMBEDDING:
                try:
                    vec_results = _search_table_vector(session, table, query_embedding, req.query, req.limit)
                    if vec_results:
                        merged = _rrf_merge(text_results, vec_results, req.limit)
                    else:
                        merged = text_results
                except Exception as e:
                    logger.warning("向量搜索失败 table=%s: %s", table, e)
                    session.rollback()  # 回退失败的事务，避免后续查询 InFailedSqlTransaction
                    merged = text_results
            else:
                merged = text_results

            # ── 低分淘汰：自适应阈值 ──
            merged = _filter_by_score(merged)

            # ── 节点搜索：附带完整状态数据 ──
            if table == "nodes" and merged:
                node_ids = [item["id"] for item in merged]
                states = _get_current_states(session, node_ids)
                for item in merged:
                    state = states.get(item["id"])
                    if state:
                        item.setdefault("extra", {})["node_state"] = state

            results_by_table[table] = [
                KBSearchResultItem(**{k: v for k, v in item.items() if k != "_tw"})
                for item in merged
            ]

    return {
        "query": req.query,
        "results": results_by_table,
        "counts": {t: len(items) for t, items in results_by_table.items()},
    }


# ── 记录列表（无搜索词时按时间排序浏览）────────────────────────

@router.get("/records/{table_name}")
async def list_records(
    table_name: str,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: dict = Depends(require_api_token),
):
    """按时间倒序浏览指定表的记录（无需搜索词）"""
    if table_name not in _VALID_TABLES:
        raise HTTPException(400, f"非法表名: {table_name}")

    pg_table = "world_nodes" if table_name == "nodes" else table_name
    title_field = _TABLE_TITLE_FIELDS[table_name]
    snippet_fields = _TABLE_SNIPPET_FIELDS[table_name]

    pub_col = "published_at" if table_name in _HAS_PUBLISHED_AT else "NULL::timestamptz AS published_at"
    # 构造 snippet 字段列表（排除已在 title_field 中使用的）
    extra_fields = [f for f in snippet_fields if f != title_field]
    select_fields = f"{title_field} AS _title"
    if extra_fields:
        select_fields += ", " + ", ".join(extra_fields)

    # node_states 需要 JOIN world_nodes 获取节点名称
    sql = text(f"""
        SELECT id, {select_fields}, created_at, {pub_col}
        FROM {pg_table}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """)
    count_sql = text(f"SELECT COUNT(*) FROM {pg_table}")

    with kb_session() as session:
        rows = session.execute(sql, {"limit": limit, "offset": offset}).fetchall()
        total = int(session.execute(count_sql).scalar() or 0)

        items = []
        for row in rows:
            title = getattr(row, "_title", None) or ""
            raw_snippet = _extract_str(row, [f for f in snippet_fields if f != title_field])
            snippet = raw_snippet[:300] + ("..." if len(raw_snippet) > 300 else "")
            items.append({
                "id": str(row.id),
                "title": str(title)[:200],
                "snippet": snippet,
                "time": _extract_time(row),
            })

    return {"items": items, "total": total, "limit": limit, "offset": offset}


# ── 获取完整文章 ──────────────────────────────────────────────────

# 各表返回全文时需要的所有字段
_ARTICLE_FIELDS: dict[str, list[str]] = {
    "raw_information": [
        "title", "body", "source", "source_url", "info_type",
        "published_at", "importance_score", "processing_status", "created_at",
    ],
    "analyses": [
        "title", "content", "analysis_type", "confidence",
        "time_horizon", "agent_id", "created_at",
    ],
    "feedbacks": [
        "title", "lessons_learned", "expected_outcome", "actual_outcome",
        "error_reason", "missed_factors", "adjustment_suggestions",
        "judgment_correct", "created_at",
    ],
    "nodes": [
        "name", "description", "node_type", "ticker", "aliases",
        "is_active", "created_at",
    ],
}


@router.get("/article/{table_name}/{article_id}")
async def get_article(
    table_name: str,
    article_id: str,
    _user: dict = Depends(require_api_token),
):
    """获取单条记录的完整内容。
    当 table_name=nodes 时，额外返回当前节点状态 (node_state)。
    """
    if table_name not in _VALID_TABLES:
        raise HTTPException(400, f"非法表名: {table_name}")

    pg_table = "world_nodes" if table_name == "nodes" else table_name
    fields = _ARTICLE_FIELDS.get(table_name, [])

    if not fields:
        raise HTTPException(400, f"表 {table_name} 无字段定义")

    sql = text(f"""
        SELECT {", ".join(fields)}
        FROM {pg_table}
        WHERE id = :id
    """)

    with kb_session() as session:
        row = session.execute(sql, {"id": article_id}).fetchone()
        if not row:
            raise HTTPException(404, f"记录 {article_id} 不存在")

        result = {}
        for f in fields:
            val = getattr(row, f, None)
            if isinstance(val, datetime):
                result[f] = val.astimezone(timezone.utc).isoformat()
            elif val is not None and hasattr(val, "__iter__") and not isinstance(val, (str, bytes, dict)):
                result[f] = [str(v) for v in val]
            else:
                result[f] = val

        # ── nodes 表：附带当前状态数据 ──
        if table_name == "nodes":
            states = _get_current_states(session, [article_id])
            if states:
                result["node_state"] = states[article_id]
            else:
                result["node_state"] = None

    return result


# ── 经验沉淀：市场认知 / 行业认知 / 宏观报告 ─────────────────────

@router.get("/cognitions/market")
async def get_market_cognition(
    _user: dict = Depends(require_api_token),
):
    """获取市场全局认知（单例）"""
    sql = text("""
        SELECT id, cognition_text, append_count, created_at, updated_at
        FROM market_cognitions
        ORDER BY updated_at DESC
        LIMIT 1
    """)
    with kb_session() as session:
        row = session.execute(sql).fetchone()
        if not row:
            return {"id": None, "cognition_text": "", "append_count": 0, "updated_at": None}
        return {
            "id": str(row.id),
            "cognition_text": row.cognition_text or "",
            "append_count": int(row.append_count or 0),
            "created_at": _format_dt(row.created_at),
            "updated_at": _format_dt(row.updated_at),
        }


@router.get("/cognitions/industries")
async def list_industry_cognitions(
    _user: dict = Depends(require_api_token),
):
    """获取所有行业认知列表（摘要）"""
    sql = text("""
        SELECT id, sector, cognition_text, append_count, created_at, updated_at
        FROM industry_cognitions
        ORDER BY append_count DESC, sector ASC
    """)
    with kb_session() as session:
        rows = session.execute(sql).fetchall()
        return [
            {
                "id": str(r.id),
                "sector": r.sector,
                "cognition_text": r.cognition_text or "",
                "append_count": int(r.append_count or 0),
                "created_at": _format_dt(r.created_at),
                "updated_at": _format_dt(r.updated_at),
            }
            for r in rows
        ]


@router.get("/cognitions/industry/{sector}")
async def get_industry_cognition(
    sector: str,
    _user: dict = Depends(require_api_token),
):
    """获取单个行业认知"""
    sql = text("""
        SELECT id, sector, cognition_text, append_count, created_at, updated_at
        FROM industry_cognitions
        WHERE sector = :sector
    """)
    with kb_session() as session:
        row = session.execute(sql, {"sector": sector}).fetchone()
        if not row:
            raise HTTPException(404, f"行业 {sector} 不存在")
        return {
            "id": str(row.id),
            "sector": row.sector,
            "cognition_text": row.cognition_text or "",
            "append_count": int(row.append_count or 0),
            "created_at": _format_dt(row.created_at),
            "updated_at": _format_dt(row.updated_at),
        }


@router.get("/macro-reports")
async def list_macro_reports(
    limit: int = Query(20, ge=1, le=100),
    _user: dict = Depends(require_api_token),
):
    """获取宏观报告列表（按版本倒序）"""
    sql = text("""
        SELECT id, version, summary, changed_sections, created_at, updated_at
        FROM macro_reports
        ORDER BY version DESC
        LIMIT :limit
    """)
    with kb_session() as session:
        rows = session.execute(sql, {"limit": limit}).fetchall()
        return [
            {
                "id": str(r.id),
                "version": int(r.version),
                "summary": r.summary or "",
                "changed_sections": list(r.changed_sections or []),
                "created_at": _format_dt(r.created_at),
                "updated_at": _format_dt(r.updated_at),
            }
            for r in rows
        ]


@router.get("/macro-reports/{version}")
async def get_macro_report(
    version: int,
    _user: dict = Depends(require_api_token),
):
    """获取指定版本的宏观报告全文"""
    sql = text("""
        SELECT id, version, content, summary, changed_sections, created_at, updated_at
        FROM macro_reports
        WHERE version = :version
    """)
    with kb_session() as session:
        row = session.execute(sql, {"version": version}).fetchone()
        if not row:
            raise HTTPException(404, f"宏观报告 v{version} 不存在")
        return {
            "id": str(row.id),
            "version": int(row.version),
            "content": row.content or "",
            "summary": row.summary or "",
            "changed_sections": list(row.changed_sections or []),
            "created_at": _format_dt(row.created_at),
            "updated_at": _format_dt(row.updated_at),
        }


def _format_dt(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.astimezone(timezone.utc).isoformat()
    return str(val)
