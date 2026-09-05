"""OSS 图片上传工具 — PNG bytes/本地路径 → 公网 URL。

用法:
    from app.agent.utils.oss import upload_bytes, upload_image, ensure_public_url

    url = upload_bytes(png_bytes, "agent_images/chart_20260601.png")
    # → "https://xxx.oss-cn-beijing.aliyuncs.com/agent_images/chart_20260601.jpg"

    url = ensure_public_url("/path/to/chart.png")
    # 自动上传并返回公网 URL；已是公网 URL 则原样返回
"""

from __future__ import annotations

import io
import os
import tempfile
import threading
import time
import uuid
import logging

logger = logging.getLogger(__name__)

_COMPRESS_MAX_WIDTH = 1200
_COMPRESS_JPEG_QUALITY = 90


def _is_oss_available() -> bool:
    """检查 OSS 配置是否可用"""
    try:
        from app.config import settings
        return settings.oss_enabled
    except Exception:
        return False


def _compress_to_jpeg(data: bytes, max_width: int = _COMPRESS_MAX_WIDTH, quality: int = _COMPRESS_JPEG_QUALITY) -> bytes:
    """将图片压缩为 JPEG，保持宽高比，限制最大宽度。"""
    from PIL import Image

    img = Image.open(io.BytesIO(data))

    # RGBA 转 RGB（JPEG 不支持透明通道）
    # P（调色板）模式必须先转 RGBA 再转 RGB，否则丢失调色板信息导致全白
    if img.mode == "P":
        img = img.convert("RGBA").convert("RGB")
    elif img.mode in ("RGBA", "LA"):
        img = img.convert("RGB")

    # 等比缩放
    if img.width > max_width:
        ratio = max_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


_client = None
_client_lock = threading.Lock()


def _get_client():
    """获取 OSS 客户端（线程安全单例）"""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                import alibabacloud_oss_v2 as oss
                from app.config import settings

                credentials_provider = oss.credentials.StaticCredentialsProvider(
                    access_key_id=settings.oss_access_key_id,
                    access_key_secret=settings.oss_access_key_secret,
                )
                cfg = oss.config.load_default()
                cfg.credentials_provider = credentials_provider
                cfg.region = settings.oss_region
                cfg.endpoint = settings.oss_endpoint
                _client = oss.Client(cfg)
    return _client


def upload_bytes(png_bytes: bytes, remote_key: str | None = None, compress: bool = True) -> str:
    """将内存中的图片上传到 OSS，返回公网 URL。

    compress=True（默认）：压缩为 JPEG 1200px 宽，减少 token 消耗。
    remote_key 为 None 时自动生成唯一路径。
    """
    from app.config import settings

    if not settings.oss_enabled:
        raise RuntimeError("OSS 未配置，无法上传图片")

    if remote_key is None:
        ext = ".jpg" if compress else ".png"
        remote_key = f"agent_images/{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}{ext}"

    if compress:
        png_bytes = _compress_to_jpeg(png_bytes)
        if remote_key.lower().endswith(".png"):
            remote_key = remote_key[:-4] + ".jpg"

    fd, tmp_path = tempfile.mkstemp(suffix=".jpg" if compress else ".png", prefix="agent_upload_")
    try:
        offset = 0
        while offset < len(png_bytes):
            written = os.write(fd, png_bytes[offset:])
            if written == 0:
                raise RuntimeError("写入临时文件失败")
            offset += written
        os.close(fd)
        return upload_image(tmp_path, remote_key, compress=False)
    finally:
        if os.path.isfile(tmp_path):
            os.unlink(tmp_path)


def upload_image(local_path: str, remote_key: str | None = None, compress: bool = True) -> str:
    """上传本地图片到 OSS，返回公网访问 URL。

    compress=True（默认）：压缩为 JPEG 1200px 宽。
    remote_key 为 None 时自动生成。
    """
    import alibabacloud_oss_v2 as oss
    from app.config import settings

    if not settings.oss_enabled:
        raise RuntimeError("OSS 未配置，无法上传图片")

    if not os.path.isfile(local_path):
        raise FileNotFoundError(f"图片文件不存在: {local_path}")

    if remote_key is None:
        base = os.path.basename(local_path)
        name, ext = os.path.splitext(base)
        ext = ".jpg" if compress else ext
        remote_key = f"agent_images/{name}_{int(time.time() * 1000)}{ext}"

    file_size = os.path.getsize(local_path)
    logger.debug("OSS 上传开始: key=%s, size=%dB, compress=%s", remote_key, file_size, compress)

    if compress:
        with open(local_path, "rb") as f:
            compressed = _compress_to_jpeg(f.read())
        if remote_key.lower().endswith(".png"):
            remote_key = remote_key[:-4] + ".jpg"
        fd, tmp_path = tempfile.mkstemp(suffix=".jpg", prefix="agent_upload_")
        offset = 0
        while offset < len(compressed):
            written = os.write(fd, compressed[offset:])
            if written == 0:
                raise RuntimeError("写入临时文件失败")
            offset += written
        os.close(fd)
        client = _get_client()
        try:
            result = client.put_object_from_file(
                oss.PutObjectRequest(bucket=settings.oss_bucket, key=remote_key),
                tmp_path,
            )
            if result.status_code != 200:
                raise RuntimeError(f"OSS 上传失败 (HTTP {result.status_code})")
        finally:
            if os.path.isfile(tmp_path):
                os.unlink(tmp_path)
    else:
        client = _get_client()
        result = client.put_object_from_file(
            oss.PutObjectRequest(bucket=settings.oss_bucket, key=remote_key),
            local_path,
        )
        if result.status_code != 200:
            raise RuntimeError(f"OSS 上传失败 (HTTP {result.status_code})")

    url = f"{settings.oss_base_url.rstrip('/')}/{remote_key}"
    logger.debug("OSS 上传成功: %s", url)
    return url


def ensure_public_url(path_or_url: str, remote_key: str | None = None, compress: bool = True) -> str:
    """将本地路径转为 OSS 公网 URL；已是 HTTP(S) URL 则原样返回。"""
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    return upload_image(path_or_url, remote_key, compress=compress)
