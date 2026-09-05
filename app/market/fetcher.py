"""
量化交易系统 - xtquant 行情拉取

后台 asyncio task，定时从 xtquant SDK 拉取全量 tick 数据。
xtquant 的 API 是同步的，用 asyncio.to_thread() 包装以避免阻塞事件循环。

⚠️ xtquant tick 数据结构约定：
  - xtdata.get_full_tick() 返回 dict[code → tick] 或 list，两种格式都需兼容
  - askPrice/bidPrice 可能是嵌套列表 [[a,b,c], ...] 需展平处理
  - xtquant 的回调线程非 asyncio，MarketData.update_ticks 内部用 threading.Lock 保护
"""
import asyncio
import logging

from ..config import settings

logger = logging.getLogger(__name__)

# xtquant SDK 引用（运行时注入）
xtdata = None


def init_xtdata(xtdata_module) -> None:
    """注入 xtquant SDK 模块"""
    global xtdata
    xtdata = xtdata_module


async def run_tick_loop(market_data, stock_codes: set[str], interval: float = 0) -> None:
    """后台 tick 拉取循环"""
    if xtdata is None:
        logger.warning("xtdata 未初始化，跳过行情拉取")
        return

    from .trading_hours import is_continuous_auction

    freq = interval or settings.tick_fetch_interval
    logger.info("行情拉取启动: 间隔=%.1fs, 股票数=%d", freq, len(stock_codes))

    while True:
        try:
            codes = list(stock_codes)
            if not codes:
                await asyncio.sleep(freq)
                continue

            if not is_continuous_auction():
                await asyncio.sleep(freq)
                continue

            # xtquant API 是同步阻塞的，丢到线程池执行
            raw = await asyncio.to_thread(xtdata.get_full_tick, codes)
            ticks = _parse_xt_tick(raw, codes)
            if ticks:
                market_data.update_ticks(ticks)

            await asyncio.sleep(freq)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("行情拉取异常")
            await asyncio.sleep(freq)


def _parse_xt_tick(raw, codes: list[str]) -> list[dict]:
    """将 xtquant 返回的原始 tick 转换为内部格式"""
    if not raw:
        return []
    result = []
    is_dict = isinstance(raw, dict)
    for idx, code in enumerate(codes):
        try:
            d = raw.get(code) if is_dict else (raw[idx] if idx < len(raw) else None)
            if not d:
                continue

            def _get_side(index: int, prices_raw, vols_raw):
                price_list = prices_raw if isinstance(prices_raw, list) else []
                vol_list = vols_raw if isinstance(vols_raw, list) else []
                # Flatten if nested [[a,b,c], ...]
                if price_list and isinstance(price_list[0], list):
                    price_list = price_list[0]
                if vol_list and isinstance(vol_list[0], list):
                    vol_list = vol_list[0]
                return (
                    price_list[index] if index < len(price_list) else 0,
                    int(vol_list[index]) if index < len(vol_list) else 0,
                )

            ask_prices = d.get("askPrice", [])
            ask_vols = d.get("askVol", [])
            bid_prices = d.get("bidPrice", [])
            bid_vols = d.get("bidVol", [])

            def _to_decimal(val) -> str:
                """Preserve precision by passing raw value through str() without float intermediate."""
                if val is None:
                    return "0"
                return str(val)

            result.append({
                "stock_code": code,
                "lastPrice": _to_decimal(d.get("lastPrice", 0) or 0),
                "open": _to_decimal(d.get("open", 0) or 0),
                "high": _to_decimal(d.get("high", 0) or 0),
                "low": _to_decimal(d.get("low", 0) or 0),
                "amount": _to_decimal(d.get("amount", 0) or 0),
                "volume": int(d.get("volume", 0) or 0),
                "time": int(d.get("time", 0) or 0),
                "ask1": _to_decimal(_get_side(0, ask_prices, ask_vols)[0]),
                "ask2": _to_decimal(_get_side(1, ask_prices, ask_vols)[0]),
                "ask3": _to_decimal(_get_side(2, ask_prices, ask_vols)[0]),
                "ask4": _to_decimal(_get_side(3, ask_prices, ask_vols)[0]),
                "ask5": _to_decimal(_get_side(4, ask_prices, ask_vols)[0]),
                "bid1": _to_decimal(_get_side(0, bid_prices, bid_vols)[0]),
                "bid2": _to_decimal(_get_side(1, bid_prices, bid_vols)[0]),
                "bid3": _to_decimal(_get_side(2, bid_prices, bid_vols)[0]),
                "bid4": _to_decimal(_get_side(3, bid_prices, bid_vols)[0]),
                "bid5": _to_decimal(_get_side(4, bid_prices, bid_vols)[0]),
                "ask_volumes": [
                    _get_side(0, ask_prices, ask_vols)[1],
                    _get_side(1, ask_prices, ask_vols)[1],
                    _get_side(2, ask_prices, ask_vols)[1],
                    _get_side(3, ask_prices, ask_vols)[1],
                    _get_side(4, ask_prices, ask_vols)[1],
                ],
                "bid_volumes": [
                    _get_side(0, bid_prices, bid_vols)[1],
                    _get_side(1, bid_prices, bid_vols)[1],
                    _get_side(2, bid_prices, bid_vols)[1],
                    _get_side(3, bid_prices, bid_vols)[1],
                    _get_side(4, bid_prices, bid_vols)[1],
                ],
            })
        except Exception:
            logger.exception("解析 tick 失败: %s", code)
    return result
