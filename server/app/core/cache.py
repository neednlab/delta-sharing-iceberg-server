"""
请求级缓存管理模块

提供基于 ContextVar 的请求级缓存工具，确保同一 HTTP 请求内
避免对同一 COS 对象的重复下载。通过 ASGI 中间件实现
请求边界内的缓存自动初始化和清理。

使用方式:
    # 在模块级别创建缓存管理器
    my_cache = RequestCacheManager("my_cache")

    # 在 service 层读写缓存
    cached = my_cache.get("key")
    if cached is not None:
        return cached
    value = download_from_cos(...)
    my_cache.set("key", value)
    return value

    # 在 main.py 中注册清理中间件
    app.add_middleware(CacheMiddleware, managers=[my_cache])
"""

from contextvars import ContextVar
from typing import Any, Dict, List, Optional

from starlette.types import ASGIApp, Scope, Receive, Send


class RequestCacheManager:
    """请求级缓存管理器

    封装 ContextVar 读写和重置操作，提供 get/set/clear 通用方法。
    每个实例管理一个独立的缓存命名空间，利用 ContextVar 在 asyncio
    环境中实现的请求级隔离特性。

    Attributes:
        _var: 内部 ContextVar，存储 Optional[Dict[str, Any]] 类型的缓存字典。
    """

    def __init__(self, name: str):
        """初始化缓存管理器。

        Args:
            name: 缓存命名空间名称，用于 ContextVar 标识和调试。
        """
        self._var: ContextVar[Optional[Dict[str, Any]]] = ContextVar(name, default=None)

    def get(self, key: str) -> Optional[Any]:
        """从缓存中获取指定键的值。

        先从 ContextVar 获取缓存字典，若缓存字典不存在则返回 None。
        若缓存字典存在但键不存在也返回 None。

        Args:
            key: 缓存键。

        Returns:
            缓存值，如果未命中则返回 None。
        """
        cache = self._var.get()
        if cache is None:
            return None
        return cache.get(key)

    def set(self, key: str, value: Any) -> None:
        """将键值对存入缓存。

        若缓存字典尚未初始化（为 None），则先创建空字典再写入。
        该方法不返回任何值，调用后键值对即存在于当前请求的缓存中。

        Args:
            key: 缓存键。
            value: 缓存值（任意 Python 对象）。
        """
        cache = self._var.get()
        if cache is None:
            cache = {}
            self._var.set(cache)
        cache[key] = value

    def initialize(self) -> None:
        """初始化缓存字典（设为空 dict）。

        在请求处理开始前调用，为当前请求创建一个空的缓存字典，
        确保后续 get/set 操作都有合法的缓存容器。
        """
        self._var.set({})

    def clear(self) -> None:
        """清空缓存，释放内存。

        将 ContextVar 重置为 None，使当前请求的缓存引用被释放，
        由 Python GC 在适当时机回收内存。
        """
        self._var.set(None)


# 请求级 DLC metadata_location 缓存
# 缓存键: "share.schema.table"  →  缓存值: str（DLC API 返回的 metadata_location）
_metadata_location_cache = RequestCacheManager("metadata_location_cache")

# 请求级 metadata JSON 内容缓存
# 缓存键: "{bucket}/{key}"  →  缓存值: Dict[str, Any]（已解析的 JSON）
_metadata_content_cache = RequestCacheManager("metadata_content_cache")

# 请求级 manifest-list 内容缓存
# 缓存键: "{bucket}/{key}"  →  缓存值: List[str]（manifest 文件路径列表）
_manifest_list_cache = RequestCacheManager("manifest_list_cache")

# 请求级 manifest 文件内容缓存
# 缓存键: "{bucket}/{key}"  →  缓存值: List[Dict[str, Any]]（解析后的 manifest 条目列表）
_manifest_cache = RequestCacheManager("manifest_cache")

# 请求级 snapshot 同步标记缓存
# 缓存键: "share.schema.table"  →  缓存值: True（标记该表在当前请求内已完成同步）
_sync_flag_cache = RequestCacheManager("sync_flag_cache")

# 所有请求级缓存管理器列表，供 CacheMiddleware 管理和清理
_request_cache_managers: List[RequestCacheManager] = [
    _metadata_location_cache,
    _metadata_content_cache,
    _manifest_list_cache,
    _manifest_cache,
    _sync_flag_cache,
]


class CacheMiddleware:
    """请求级缓存清理中间件（纯 ASGI 实现）

    在每个 HTTP 请求处理前初始化所有已注册的 RequestCacheManager 为空的缓存字典，
    在请求处理后（无论成功或异常）通过 try/finally 清理所有缓存，
    防止跨请求内存泄漏。

    使用纯 ASGI 中间件而非 BaseHTTPMiddleware，避免后者已知的
    请求体消费和异常处理问题。

    Attributes:
        app: 内层 ASGI 应用实例。
        _managers: 已注册的 RequestCacheManager 实例列表。
    """

    def __init__(self, app: ASGIApp, managers: List[RequestCacheManager]):
        """初始化缓存中间件。

        Args:
            app: FastAPI/Starlette 应用实例。
            managers: 需要在请求边界内管理生命周期的缓存管理器列表。
        """
        self.app = app
        self._managers = managers

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI 入口点。

        仅处理 HTTP 请求：请求前初始化缓存字典，请求后清理。
        非 HTTP 请求直接透传给内层应用。

        Args:
            scope: ASGI scope 字典。
            receive: ASGI receive callable。
            send: ASGI send callable。
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 请求前：初始化所有缓存为空字典
        for manager in self._managers:
            manager.initialize()

        try:
            await self.app(scope, receive, send)
        finally:
            # 请求后：清理所有缓存（保证异常路径也能清理）
            for manager in self._managers:
                manager.clear()
