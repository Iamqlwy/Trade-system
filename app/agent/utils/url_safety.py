"""URL 安全检查 — 防止 SSRF 攻击

合并自：
  - simple-agent/tools/web.py: _is_safe_url()
  - search_agent/search/scraper.py: _is_safe_url() + _BLOCKED_NETWORKS
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# 内网地址段（SSRF 防护）
# ---------------------------------------------------------------------------

blocked_networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

blocked_hosts: frozenset[str] = frozenset({
    "localhost",
    "metadata.google.internal",
    "169.254.169.254",  # AWS/GCP metadata
})


# ---------------------------------------------------------------------------
# 国内域名（直连，不走代理）
# ---------------------------------------------------------------------------

domestic_suffixes: tuple[str, ...] = (
    ".cn", ".com.cn", ".org.cn", ".net.cn", ".edu.cn", ".gov.cn", ".mil.cn",
    ".中国", ".公司", ".网络",
)

# 使用国际域名的国内常见网站（直连）
domestic_com_domains: frozenset[str] = frozenset({
    "eastmoney.com", "yicai.com", "aliyuncs.com", "alibaba.com",
    "baidu.com", "zhihu.com", "csdn.net", "juejin.cn",
    "qq.com", "tencent.com", "sina.com.cn", "sina.com",
    "sohu.com", "163.com", "jd.com", "taobao.com",
    "bilibili.com", "douyin.com", "toutiao.com", "weibo.com",
    "ctrip.com", "meituan.com", "didiglobal.com",
    # 财经类
    "xueqiu.com", "jiemian.com", "hexun.com", "10jqka.com",
    "stcn.com", "cls.cn", "p5w.net", "cninfo.com.cn",
    "nbd.com.cn", "caixin.com", "caijing.com.cn",
})


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------

def is_safe_url(url: str) -> tuple[bool, str]:
    """检查 URL 是否安全。

    返回 (safe, error_message)。
    - 仅允许 http/https 协议
    - 阻止内网地址、回环地址、链路本地地址
    - 阻止已知危险主机名
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL."

    if parsed.scheme not in ("http", "https"):
        return False, f"Blocked: unsupported scheme '{parsed.scheme}'."

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False, "Blocked: empty hostname."

    # 阻止已知危险主机
    if hostname in blocked_hosts:
        return False, f"Blocked: dangerous host '{hostname}'."

    # 阻止内网域名后缀
    if hostname.endswith(".local") or hostname.endswith(".internal"):
        return False, "Blocked: internal domain."

    # 尝试将 hostname 解析为 IP 地址进行检查
    try:
        addr = ipaddress.ip_address(hostname)
        if addr.is_private or addr.is_loopback or addr.is_link_local:
            return False, f"Blocked: private/internal IP ({addr})."
        # 检查是否在更严格的阻止列表中
        if any(addr in net for net in blocked_networks):
            return False, f"Blocked: IP in blocked range ({addr})."
    except ValueError:
        pass  # hostname 不是 IP 地址格式，跳过 IP 检查

    return True, ""


def is_domestic_url(url: str) -> bool:
    """判断 URL 是否指向国内网站（用于代理分流）"""
    try:
        hostname = urlparse(url).hostname
        if not hostname:
            return False
        hostname = hostname.lower()

        # 精确匹配已知国内域名
        if hostname in domestic_com_domains:
            return True
        # 子域名匹配
        parts = hostname.split(".")
        for i in range(1, len(parts)):
            candidate = ".".join(parts[i:])
            if candidate in domestic_com_domains:
                return True
        # 匹配国内域名后缀
        return hostname.endswith(domestic_suffixes)
    except Exception:
        return False
