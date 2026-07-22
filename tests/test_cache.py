"""core/cache.py 单元测试 — 三级取数策略全覆盖。

运行：python3 -m pytest tests/test_cache.py -q
"""

import json
import time

from core.cache import cache_path, cache_read, cache_write, cached_fetch

# ---------------------------------------------------------------------------
# cache_path
# ---------------------------------------------------------------------------


class TestCachePath:
    def test_basic(self, tmp_path):
        p = cache_path(str(tmp_path), "quote", "sh600519")
        assert p.endswith("quote-sh600519.json")

    def test_special_chars_sanitized(self, tmp_path):
        p = cache_path(str(tmp_path), "kline", "usAAPL-120")
        assert "usAAPL-120" in p
        # 非法字符被过滤
        p2 = cache_path(str(tmp_path), "quote", "code/with:bad*chars")
        assert "/" not in p2.split("quote-")[1]


# ---------------------------------------------------------------------------
# cache_read / cache_write
# ---------------------------------------------------------------------------


class TestCacheReadWrite:
    def test_write_then_read(self, tmp_path):
        cache_write(str(tmp_path), "quote", "sh600519", {"price": "100"})
        entry = cache_read(str(tmp_path), "quote", "sh600519")
        assert entry is not None
        assert entry["payload"] == {"price": "100"}
        assert "fetched_at" in entry
        assert "fetched_date" in entry

    def test_read_nonexistent_returns_none(self, tmp_path):
        assert cache_read(str(tmp_path), "quote", "nonexistent") is None

    def test_read_corrupted_returns_none(self, tmp_path):
        # 写入损坏的 JSON
        p = cache_path(str(tmp_path), "quote", "bad")
        with open(p, "w") as f:
            f.write("not-json{{{")
        assert cache_read(str(tmp_path), "quote", "bad") is None

    def test_read_missing_fields_returns_none(self, tmp_path):
        # 缺少 fetched_at / payload 字段
        p = cache_path(str(tmp_path), "quote", "incomplete")
        with open(p, "w") as f:
            json.dump({"foo": "bar"}, f)
        assert cache_read(str(tmp_path), "quote", "incomplete") is None

    def test_write_creates_directory(self, tmp_path):
        nested = str(tmp_path / "a" / "b" / "c")
        cache_write(nested, "test", "key1", [1, 2, 3])
        entry = cache_read(nested, "test", "key1")
        assert entry["payload"] == [1, 2, 3]


# ---------------------------------------------------------------------------
# cached_fetch — 三级取数策略
# ---------------------------------------------------------------------------


class TestCachedFetch:
    def test_fresh_cache_hit(self, tmp_path):
        """TTL 内直接返回缓存，不调用 fetch_fn。"""
        cache_write(str(tmp_path), "quote", "sh600519", {"price": "100"})
        call_count = [0]

        def fetcher():
            call_count[0] += 1
            return {"price": "200"}

        payload, note = cached_fetch(str(tmp_path), "quote", "sh600519", 900, fetcher)
        assert payload == {"price": "100"}  # 返回缓存数据
        assert "TTL内复用" in note
        assert call_count[0] == 0  # 未调用网络

    def test_expired_cache_refetch(self, tmp_path):
        """TTL 过期后重新获取并回写缓存。"""
        # 手动写入过期缓存
        p = cache_path(str(tmp_path), "quote", "sh600519")
        entry = {
            "fetched_at": time.time() - 2000,  # 远超 TTL
            "fetched_date": "2020-01-01 00:00",
            "payload": {"price": "old"},
        }
        with open(p, "w") as f:
            json.dump(entry, f)

        payload, note = cached_fetch(
            str(tmp_path), "quote", "sh600519", 900, lambda: {"price": "new"}
        )
        assert payload == {"price": "new"}
        assert note is None  # 网络成功无标注

        # 验证回写
        refreshed = cache_read(str(tmp_path), "quote", "sh600519")
        assert refreshed["payload"] == {"price": "new"}

    def test_network_fail_fallback_to_stale_cache(self, tmp_path):
        """网络失败时回退过期缓存。"""
        p = cache_path(str(tmp_path), "quote", "sh600519")
        entry = {
            "fetched_at": time.time() - 2000,
            "fetched_date": "2020-01-01 00:00",
            "payload": {"price": "stale"},
        }
        with open(p, "w") as f:
            json.dump(entry, f)

        def failing_fetcher():
            raise ConnectionError("network down")

        payload, note = cached_fetch(
            str(tmp_path), "quote", "sh600519", 900, failing_fetcher
        )
        assert payload == {"price": "stale"}
        assert "网络失败回退" in note

    def test_network_fail_no_cache_raises(self, tmp_path):
        """网络失败且无缓存时透传异常。"""
        import pytest

        def failing_fetcher():
            raise ConnectionError("network down")

        with pytest.raises(ConnectionError):
            cached_fetch(str(tmp_path), "quote", "nocode", 900, failing_fetcher)

    def test_no_cache_flag_skips_cache(self, tmp_path):
        """no_cache=True 时跳过缓存直连。"""
        cache_write(str(tmp_path), "quote", "sh600519", {"price": "cached"})
        call_count = [0]

        def fetcher():
            call_count[0] += 1
            return {"price": "fresh"}

        payload, note = cached_fetch(
            str(tmp_path), "quote", "sh600519", 900, fetcher, no_cache=True
        )
        assert payload == {"price": "fresh"}
        assert note is None
        assert call_count[0] == 1
