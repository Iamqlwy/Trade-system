"""
量化交易系统 v2.0 - 入口

启动 FastAPI 服务器。需要 xtquant SDK 环境时，在启动前配置 xtdata 路径。
"""
import logging
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent))

# 加载 .env 文件
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

logger = logging.getLogger(__name__)


def main():
    import uvicorn
    from app.config import settings

    # xtquant SDK 初始化已移入 app/main.py 的 lifespan 中
    # （reload=True 时父进程的 global 注入对 worker 子进程无效）

    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
        reload=True,
        # 只监听源码文件变更，防止 logs/ 写入触发无限重启循环
        reload_includes=["*.py"],
        reload_dirs=[str(Path(__file__).parent / "app")],
    )


if __name__ == "__main__":
    main()
