"""
Profile 模型模块

该模块定义了 Delta Sharing Profile 的数据模型。
Profile 是客户端用于连接服务器的配置文件格式。
"""

from typing import Optional
from pydantic import BaseModel


class Profile(BaseModel):
    """Delta Sharing Profile 模型

    Profile 文件包含客户端连接服务器所需的所有信息，
    包括服务端点、Bearer Token 和过期时间。

    Attributes:
        shareCredentialsVersion: 共享凭证版本号，默认为 1。
        endpoint: 服务端点 URL。
        bearerToken: Bearer 认证 Token。
        expirationTime: Token 过期时间（可选）。
    """

    shareCredentialsVersion: int = 1
    endpoint: str
    bearerToken: str
    expirationTime: Optional[str] = None

    def to_dict(self) -> dict:
        """转换为字典格式。

        Returns:
            包含 Profile 所有字段的字典。
        """
        result = {
            "shareCredentialsVersion": self.shareCredentialsVersion,
            "endpoint": self.endpoint,
            "bearerToken": self.bearerToken,
        }
        if self.expirationTime:
            result["expirationTime"] = self.expirationTime
        return result
