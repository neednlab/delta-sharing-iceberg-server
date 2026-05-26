"""
RequestCacheManager 和 CacheMiddleware 单元测试

覆盖范围：
- RequestCacheManager.get: 命中、未命中、未初始化
- RequestCacheManager.set: 写入新键、覆盖已有键
- RequestCacheManager.initialize: 初始化空字典
- RequestCacheManager.clear: 清理后不可用
- CacheMiddleware 生命周期: 正常/异常路径
- 请求级缓存隔离
"""

import pytest
from unittest.mock import MagicMock
from contextvars import copy_context

from app.core.cache import RequestCacheManager, CacheMiddleware


@pytest.fixture
def cache_mgr():
    """创建独立的 RequestCacheManager 实例。"""
    return RequestCacheManager("test_cache")


class TestRequestCacheManagerGet:
    def test_hit_returns_value(self, cache_mgr):
        cache_mgr.set("key1", "value1")
        assert cache_mgr.get("key1") == "value1"

    def test_miss_returns_none(self, cache_mgr):
        cache_mgr.initialize()
        assert cache_mgr.get("missing_key") is None

    def test_uninitialized_returns_none(self, cache_mgr):
        assert cache_mgr.get("any_key") is None


class TestRequestCacheManagerSet:
    def test_set_new_key(self, cache_mgr):
        cache_mgr.set("key1", {"data": [1, 2, 3]})
        assert cache_mgr.get("key1") == {"data": [1, 2, 3]}

    def test_overwrite_existing_key(self, cache_mgr):
        cache_mgr.set("key1", "old")
        cache_mgr.set("key1", "new")
        assert cache_mgr.get("key1") == "new"


class TestRequestCacheManagerInitialize:
    def test_initialize_creates_empty_dict(self, cache_mgr):
        cache_mgr.initialize()
        assert cache_mgr.get("any_key") is None


class TestRequestCacheManagerClear:
    def test_clear_makes_cache_unavailable(self, cache_mgr):
        cache_mgr.set("key1", "value1")
        cache_mgr.clear()
        assert cache_mgr.get("key1") is None


class TestCacheMiddlewareLifecycle:
    @pytest.mark.asyncio
    async def test_normal_path_initialize_and_clear(self):
        mgr = RequestCacheManager("mw_test")
        app = MagicMock()
        middleware = CacheMiddleware(app, managers=[mgr])

        async def mock_call_next(request):
            return MagicMock(status_code=200)

        request = MagicMock()
        await middleware.dispatch(request, mock_call_next)

        assert mgr.get("any") is None

    @pytest.mark.asyncio
    async def test_exception_path_still_clears(self):
        mgr = RequestCacheManager("mw_test_exc")
        app = MagicMock()
        middleware = CacheMiddleware(app, managers=[mgr])

        async def mock_call_next(request):
            mgr.set("key", "set_before_exception")
            raise ValueError("test error")

        request = MagicMock()
        with pytest.raises(ValueError, match="test error"):
            await middleware.dispatch(request, mock_call_next)

        assert mgr.get("key") is None


class TestCacheIsolation:
    def test_different_contexts_isolated(self):
        mgr = RequestCacheManager("iso_test")

        ctx1 = copy_context()
        ctx2 = copy_context()

        ctx1.run(mgr.set, "key", "A")
        ctx2.run(mgr.set, "key", "B")

        val1 = ctx1.run(mgr.get, "key")
        val2 = ctx2.run(mgr.get, "key")

        assert val1 == "A"
        assert val2 == "B"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
