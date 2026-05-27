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
        """测试正常请求路径：缓存应在请求前初始化，请求后清空。"""
        mgr = RequestCacheManager("mw_test")
        app = MagicMock()
        # app 是内层 ASGI 应用，需要是一个 async callable
        app_called = False

        async def mock_app(scope, receive, send):
            nonlocal app_called
            app_called = True
            # 模拟发送响应
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": b"{}"})

        middleware = CacheMiddleware(app=mock_app, managers=[mgr])

        # 构建 ASGI scope / receive / send
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
        }

        async def receive():
            return {"type": "http.request", "body": b""}

        send_messages = []

        async def send(message):
            send_messages.append(message)

        await middleware(scope, receive, send)

        assert app_called, "内层 app 应被调用"
        assert mgr.get("any") is None, "缓存应在请求后被清空"

    @pytest.mark.asyncio
    async def test_exception_path_still_clears(self):
        """测试异常路径：即使内层 app 抛出异常，缓存也应被清空。"""
        mgr = RequestCacheManager("mw_test_exc")
        app = MagicMock()

        async def mock_app(scope, receive, send):
            # 在异常前设置缓存值
            mgr.set("key", "set_before_exception")
            # 先尝试发送响应（部分 app 可能在抛异常前已开始发送）
            await send(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": b'{"error": "test"}'})
            raise ValueError("test error")

        middleware = CacheMiddleware(app=mock_app, managers=[mgr])

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
        }

        async def receive():
            return {"type": "http.request", "body": b""}

        send_messages = []

        async def send(message):
            send_messages.append(message)

        with pytest.raises(ValueError, match="test error"):
            await middleware(scope, receive, send)

        # 即使发生异常，finally 块也会清理缓存
        assert mgr.get("key") is None, "缓存应在异常发生后被清空"


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
