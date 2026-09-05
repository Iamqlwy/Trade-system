"""Agent REST API

会话列表、创建、删除、重命名等 HTTP 端点。
"""

import io
import logging
import mimetypes
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from starlette.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from ..auth.dependencies import require_agent_access
from ..utils.sanitize import sanitize_str

logger = logging.getLogger(__name__)

agent_api_router = APIRouter(prefix="/api/agent", tags=["agent"])


class RenameRequest(BaseModel):
    title: str = Field(..., max_length=200)

    @field_validator("title")
    @classmethod
    def _sanitize_title(cls, v: str) -> str:
        return sanitize_str(v, max_length=200) or v


@agent_api_router.get("/sessions")
async def list_sessions(user: dict = Depends(require_agent_access)):
    """列出当前用户的所有 Agent 会话"""
    from ..services.agent_manager import agent_manager
    sessions = agent_manager.list_sessions(user_id=user["user_id"])
    return {"sessions": sessions}


@agent_api_router.post("/sessions")
async def create_session(user: dict = Depends(require_agent_access)):
    """创建新会话"""
    from ..services.agent_manager import agent_manager
    session_id = agent_manager.create_session(user_id=user["user_id"])
    return {"session_id": session_id}


@agent_api_router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user: dict = Depends(require_agent_access)):
    """删除指定会话"""
    from ..services.agent_manager import agent_manager
    ok = await agent_manager.delete_session(session_id, user_id=user["user_id"])
    if not ok:
        raise HTTPException(status_code=403, detail="无权删除此会话")
    return {"ok": True}


@agent_api_router.put("/sessions/{session_id}")
async def rename_session(session_id: str, body: RenameRequest, user: dict = Depends(require_agent_access)):
    """重命名指定会话"""
    from ..services.agent_manager import agent_manager
    title = body.title.strip()[:200]
    if not title:
        raise HTTPException(status_code=400, detail="标题不能为空")
    ok = await agent_manager.rename_session(session_id, title, user_id=user["user_id"])
    if not ok:
        raise HTTPException(status_code=403, detail="无权修改此会话")
    return {"ok": True}


# ================================================================
# Agent 工作区文件服务
# ================================================================

_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp'}
_IMAGE_MIME_PREFIX = 'image/'


@agent_api_router.get('/files/{session_id}/{path:path}')
async def serve_session_file(session_id: str, path: str, user: dict = Depends(require_agent_access)):
    """[旧接口，保留兼容] 通过 /api/agent/files/ 提供工作区文件。"""
    from ..agent.config import get_workspace_dir

    if '..' in path or path.startswith('/') or '\\' in path:
        raise HTTPException(status_code=400, detail='Invalid path')

    ext = os.path.splitext(path)[1].lower()
    if ext not in _IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail='File type not allowed')

    workspace_dir = get_workspace_dir(session_id)
    file_path = (workspace_dir / path).resolve()

    if not str(file_path).startswith(str(workspace_dir.resolve())):
        raise HTTPException(status_code=400, detail='Invalid path')

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail='File not found')

    mime_type, _ = mimetypes.guess_type(str(file_path))
    if not mime_type or not mime_type.startswith(_IMAGE_MIME_PREFIX):
        raise HTTPException(status_code=400, detail='File type not allowed')

    return FileResponse(
        file_path,
        media_type=mime_type,
        headers={'Cache-Control': 'public, max-age=3600'},
    )


# ── 工作区直连接口（新） ──────────────────────────────────────────
# 前端图片 src 直接指向 /api/workspace/{session_id}/{path}，
# 后端鉴权后从 agent 工作区返回文件。路径格式与 AI 输出一致。

@agent_api_router.get('/workspace/{session_id}/{path:path}')
async def serve_workspace_file(session_id: str, path: str, user: dict = Depends(require_agent_access)):
    """从 Agent 工作区直接返回文件（鉴权）。

    请求路径: GET /api/agent/workspace/{session_id}/{relative_path}
    实际文件: {agent_home}/workspaces/{session_id}/{relative_path}
    """
    from ..agent.config import get_workspace_dir

    # 路径安全检查
    if '..' in path or path.startswith('/') or '\\' in path:
        raise HTTPException(status_code=400, detail='Invalid path')

    workspace_dir = get_workspace_dir(session_id)
    file_path = (workspace_dir / path).resolve()

    if not str(file_path).startswith(str(workspace_dir.resolve())):
        raise HTTPException(status_code=400, detail='Invalid path')

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail='File not found')

    mime_type, _ = mimetypes.guess_type(str(file_path))

    # 图片类型直接返回
    if mime_type and mime_type.startswith(_IMAGE_MIME_PREFIX):
        return FileResponse(
            file_path,
            media_type=mime_type,
            headers={'Cache-Control': 'public, max-age=3600'},
        )

    # 非图片类型：仅允许安全文本类型（禁止 text/html 和 text/javascript 防止 XSS）
    _SAFE_TEXT_MIME = {'text/plain', 'text/csv', 'application/json'}
    if mime_type in _SAFE_TEXT_MIME:
        return FileResponse(
            file_path,
            media_type=mime_type,
            headers={'Cache-Control': 'no-cache'},
        )

    raise HTTPException(status_code=400, detail='File type not allowed')


# ================================================================
# 图片上传 → OSS
# ================================================================

_UPLOAD_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}
_MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB


@agent_api_router.post("/upload-image")
async def upload_image(file: UploadFile = File(...), user: dict = Depends(require_agent_access)):
    """上传图片到 OSS，返回公网 URL。

    接受 multipart/form-data 格式的图片文件。
    返回: {"url": "https://xxx.oss-cn-beijing.aliyuncs.com/...", "name": "原始文件名"}
    """
    from ..config import settings

    if not settings.oss_enabled:
        raise HTTPException(status_code=503, detail="OSS 未配置，无法上传图片")

    # 校验文件扩展名
    original_name = file.filename or "upload.png"
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in _UPLOAD_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的图片格式: {ext}")

    # 读取文件内容
    content = await file.read()
    if len(content) > _MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail=f"图片过大，最大 10MB（当前 {len(content) / 1024 / 1024:.1f}MB）")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="空文件")

    # 校验是否为真实图片（防止伪装扩展名的非图片文件）
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(content))
        img.verify()  # 验证文件完整性
        # verify() 之后需要重新打开才能读取尺寸
        img = Image.open(io.BytesIO(content))
        w, h = img.size
    except Exception:
        raise HTTPException(status_code=400, detail="文件不是有效的图片")

    # 校验像素尺寸（防止超大图片消耗过多资源）
    _MAX_IMAGE_PIXELS = 8000
    if w > _MAX_IMAGE_PIXELS or h > _MAX_IMAGE_PIXELS:
        raise HTTPException(status_code=400, detail=f"图片尺寸 {w}×{h} 超过上限（最大 {_MAX_IMAGE_PIXELS}px）")

    # 保存到临时文件后上传 OSS
    fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="agent_upload_")
    try:
        # os.write 不保证一次写完，必须循环直到全部写入
        offset = 0
        while offset < len(content):
            written = os.write(fd, content[offset:])
            if written == 0:
                raise RuntimeError("写入临时文件失败")
            offset += written
        os.close(fd)

        from ..agent.utils.oss import upload_image as oss_upload
        import uuid, time
        remote_key = f"agent_images/{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}{ext}"
        url = oss_upload(tmp_path, remote_key=remote_key, compress=False)

        return {"url": url, "name": original_name}
    except Exception as e:
        logger.exception("图片上传到 OSS 失败")
        raise HTTPException(status_code=500, detail=f"图片上传失败: {e}")
    finally:
        if os.path.isfile(tmp_path):
            os.unlink(tmp_path)
