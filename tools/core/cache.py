"""通用文件缓存层 — 零外部依赖。

三级取数策略：TTL 内缓存 → 网络（成功回写）→ 过期缓存兜底。
从 ashare_data.py 提取，供全工具层复用。

用法：
    from core.cache import cached_fetch

    payload, note = cached_fetch(
        cache_dir="/path/to/cache",
        kind="quote",
        key="sh600519",
        ttl=900,
        fetch_fn=lambda: fetch_from_network(),
    )
"""

import json
import os
import time


def cache_path(cache_dir: str, kind: str, key: str) -> str:
    """构造缓存文件路径（key 中非法字符替换为安全字符）。

    Args:
        cache_dir: 缓存根目录
        kind: 数据类型前缀（如 "quote"、"financials"、"kline"）
        key: 唯一标识（如股票代码）

    Returns:
        缓存文件绝对路径
    """
    safe = "".join(ch for ch in key if ch.isalnum() or ch in "._-")
    return os.path.join(cache_dir, f"{kind}-{safe}.json")


def cache_read(cache_dir: str, kind: str, key: str) -> dict | None:
    """读缓存条目。

    Args:
        cache_dir: 缓存根目录
        kind: 数据类型前缀
        key: 唯一标识

    Returns:
        缓存条目 dict（含 fetched_at / fetched_date / payload），不存在或损坏返回 None。
    """
    try:
        with open(cache_path(cache_dir, kind, key), encoding="utf-8") as f:
            entry = json.load(f)
        if "fetched_at" in entry and "payload" in entry:
            return entry
    except (OSError, json.JSONDecodeError):
        pass
    return None


def cache_write(cache_dir: str, kind: str, key: str, payload) -> None:
    """写缓存条目；缓存不可写不影响主流程（静默忽略 OSError）。

    Args:
        cache_dir: 缓存根目录
        kind: 数据类型前缀
        key: 唯一标识
        payload: 可 JSON 序列化的数据
    """
    try:
        os.makedirs(cache_dir, exist_ok=True)
        entry = {
            "fetched_at": time.time(),
            "fetched_date": time.strftime("%Y-%m-%d %H:%M"),
            "payload": payload,
        }
        with open(cache_path(cache_dir, kind, key), "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False)
    except OSError:  # 缓存不可写不阻断主流程
        pass


def cached_fetch(
    cache_dir: str,
    kind: str,
    key: str,
    ttl: int,
    fetch_fn,
    no_cache: bool = False,
) -> tuple:
    """三级取数：TTL 内缓存 → 网络（成功回写缓存）→ 过期缓存兜底。

    Args:
        cache_dir: 缓存根目录
        kind: 数据类型前缀
        key: 唯一标识
        ttl: 缓存有效期（秒）
        fetch_fn: 无参可调用对象，从网络获取数据（失败应抛异常）
        no_cache: True 时跳过缓存直连

    Returns:
        (payload, note) 二元组：
        - payload: 数据本体
        - note: 非 None 时须在输出中展示缓存来源标注

    Raises:
        Exception: 网络失败且无可用缓存时，透传 fetch_fn 的异常。
    """
    entry = None if no_cache else cache_read(cache_dir, kind, key)
    if entry and time.time() - entry["fetched_at"] <= ttl:
        return entry["payload"], f"[缓存数据 抓取于{entry['fetched_date']}]（TTL内复用）"
    try:
        payload = fetch_fn()
        if not no_cache:
            cache_write(cache_dir, kind, key, payload)
        return payload, None
    except Exception:
        if entry:
            return entry["payload"], (
                f"[缓存数据 抓取于{entry['fetched_date']}]（网络失败回退，可能过期）"
            )
        raise
