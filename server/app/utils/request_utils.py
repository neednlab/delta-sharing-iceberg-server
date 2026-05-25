"""
请求工具函数模块

该模块提供与 HTTP 请求相关的公共工具函数，统一实现以避免路由文件中的代码重复。
"""

from fastapi import Request


def get_client_ip(request: Request) -> str:
    """从 HTTP 请求中提取客户端真实 IP 地址。

    支持代理转发场景，优先从 X-Forwarded-For header 获取最左侧的客户端 IP。
    直连场景下从 request.client.host 获取。

    Args:
        request: FastAPI Request 对象。

    Returns:
        客户端 IP 地址字符串。无法获取时返回 "unknown"。
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # 代理转发场景：X-Forwarded-For 格式为 "client, proxy1, proxy2"
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
