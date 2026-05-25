"""
腾讯云 COS 客户端模块

该模块封装了腾讯云对象存储（COS）的操作，包括：
- 预签名 URL 生成
- 对象元数据查询
- 对象内容读取
- 对象列表查询

使用单例模式确保全局只有一个 COS 客户端实例。

所有公开方法已添加结构化日志支持，覆盖 INFO（正常流程）、
DEBUG（调试细节）、WARNING（可降级异常）、ERROR（操作失败）四个级别。
"""

import time
from typing import Optional, Dict, Any
from qcloud_cos import CosConfig, CosS3Client
from loguru import logger

from app.core.config import get_config


class COSClient:
    """腾讯云 COS 客户端类

    该类封装了与腾讯云 COS 存储服务交互的所有功能。
    使用单例模式确保全局只有一个客户端实例。

    Attributes:
        _instance: 单例实例。
        _client: COS 客户端实例。
    """

    _instance: Optional["COSClient"] = None
    _client: Optional[CosS3Client] = None

    def __new__(cls):
        """获取或创建单例实例。"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def initialize(self, config: Optional[Dict[str, Any]] = None) -> None:
        """初始化 COS 客户端。

        Args:
            config: 配置字典，如果为 None 则使用全局配置。
        """
        if config is None:
            config = get_config()

        cos_config = CosConfig(
            Region=config.cos.region,
            SecretId=config.cos.secret_id,
            SecretKey=config.cos.secret_key,
            Endpoint=config.cos.endpoint if config.cos.endpoint else None,
            Timeout=30,
        )

        self._client = CosS3Client(cos_config)

    def get_client(self) -> CosS3Client:
        """获取 COS 客户端实例。

        如果客户端尚未初始化，则先进行初始化。

        Returns:
            COS 客户端实例。
        """
        if self._client is None:
            self.initialize()
        return self._client

    def generate_presigned_url(
        self, bucket: str, key: str, method: str = "GET", expiration_hours: Optional[int] = None
    ) -> str:
        """生成预签名 URL。

        预签名 URL 允许用户在不携带访问密钥的情况下临时访问 COS 对象。

        Args:
            bucket: 存储桶名称。
            key: 对象键。
            method: HTTP 方法，默认为 "GET"。
            expiration_hours: 过期小时数，如果为 None 则使用配置默认值。

        Returns:
            生成的预签名 URL。
        """
        client = self.get_client()

        if expiration_hours is None:
            expiration_hours = get_config().presigned_url.expiration_hours

        expiration_seconds = expiration_hours * 3600

        start_time = time.time()
        url = client.get_presigned_url(
            Method=method, Bucket=bucket, Key=key, Expired=expiration_seconds
        )
        elapsed_ms = int((time.time() - start_time) * 1000)

        # DEBUG 级别：记录预签名 URL 生成摘要
        # key 截断至 80 字符防止日志过长
        logger.debug(
            "COS presigned_url: bucket={} key={} method={} expires_in={}h duration={}ms",
            bucket,
            key[:80] if len(key) > 80 else key,
            method,
            expiration_hours,
            elapsed_ms,
        )

        return url

    def head_object(self, bucket: str, key: str) -> Optional[Dict[str, Any]]:
        """获取对象元数据。

        Args:
            bucket: 存储桶名称。
            key: 对象键。

        Returns:
            包含对象元数据的字典，如果查询失败则返回 None。
        """
        try:
            client = self.get_client()
            start_time = time.time()
            response = client.head_object(Bucket=bucket, Key=key)
            elapsed_ms = int((time.time() - start_time) * 1000)

            # INFO 级别：记录对象元数据查询成功
            content_length = response.get("Content-Length", "unknown")
            content_type = response.get("Content-Type", "unknown")
            logger.info(
                "COS head_object: bucket={} key={} size={} content_type={} duration={}ms",
                bucket,
                key[:80] if len(key) > 80 else key,
                content_length,
                content_type,
                elapsed_ms,
            )

            return response
        except Exception as e:
            error_msg = str(e)
            # 区分 404 与其他错误
            if "404" in error_msg or "NoSuchKey" in error_msg or "NoSuchBucket" in error_msg:
                logger.warning(
                    "COS head_object not found: bucket={} key={} error={}",
                    bucket,
                    key[:80] if len(key) > 80 else key,
                    error_msg,
                )
            else:
                # 尝试提取 COS 错误码和请求 ID
                error_code = None
                request_id = None
                try:
                    if hasattr(e, "get_origin_msg"):
                        error_code = getattr(e, "get_error_code", lambda: None)()
                    if hasattr(e, "get_request_id"):
                        request_id = e.get_request_id()
                except Exception:
                    pass
                logger.error(
                    "COS head_object failed: bucket={} key={} error_code={} error={} request_id={}",
                    bucket,
                    key[:80] if len(key) > 80 else key,
                    error_code,
                    error_msg,
                    request_id,
                )
            return None

    def get_object(self, bucket: str, key: str, start: int = 0, end: int = 0) -> Optional[bytes]:
        """读取对象内容。

        支持指定字节范围的部分读取。

        Args:
            bucket: 存储桶名称。
            key: 对象键。
            start: 起始字节位置，默认为 0。
            end: 结束字节位置，默认为 0 表示读取全部。

        Returns:
            对象内容的字节数据，如果读取失败则抛出 DeltaSharingError。
        """
        try:
            client = self.get_client()
            req_start_time = time.time()
            if end > start:
                response = client.get_object(Bucket=bucket, Key=key, Range=f"bytes={start}-{end}")
            else:
                response = client.get_object(Bucket=bucket, Key=key)
            elapsed_ms = int((time.time() - req_start_time) * 1000)

            body = response["Body"].get_raw_stream().read()
            content_length = len(body)

            # INFO 级别：记录成功获取对象
            logger.info(
                "COS get_object: bucket={} key={} size={} duration={}ms",
                bucket,
                key[:80] if len(key) > 80 else key,
                content_length,
                elapsed_ms,
            )

            return body
        except Exception as e:
            from app.core.errors import DeltaSharingError, ErrorCode

            error_msg = str(e)

            # 提取 COS 错误码和请求 ID
            cos_error_code = None
            cos_request_id = None
            try:
                if hasattr(e, "get_origin_msg"):
                    cos_error_code = getattr(e, "get_error_code", lambda: None)()
                if hasattr(e, "get_request_id"):
                    cos_request_id = e.get_request_id()
            except Exception:
                pass

            # ERROR 级别：记录 COS API 调用失败
            logger.error(
                "COS get_object failed: bucket={} key={} error_code={} error={} cos_request_id={}",
                bucket,
                key[:80] if len(key) > 80 else key,
                cos_error_code,
                error_msg,
                cos_request_id,
            )

            if (
                "403" in error_msg
                or "身份验证" in error_msg
                or "签名" in error_msg
                or "SecretId" in error_msg
                or "SecretKey" in error_msg
            ):
                raise DeltaSharingError(
                    error_code=ErrorCode.COS_ACCESS_ERROR,
                    message=f"COS认证失败: {error_msg}",
                    status_code=403,
                    details={
                        "bucket": bucket,
                        "key": key,
                        "hint": "请检查COS_SECRET_ID和COS_SECRET_KEY环境变量是否正确配置",
                    },
                )
            elif "404" in error_msg or "NoSuchKey" in error_msg:
                raise DeltaSharingError(
                    error_code=ErrorCode.COS_ACCESS_ERROR,
                    message=f"COS对象不存在: {error_msg}",
                    status_code=404,
                    details={"bucket": bucket, "key": key},
                )
            else:
                raise DeltaSharingError(
                    error_code=ErrorCode.COS_ACCESS_ERROR,
                    message=f"COS读取对象错误: {error_msg}",
                    status_code=500,
                    details={"bucket": bucket, "key": key},
                )

    def list_objects(self, bucket: str, prefix: str = "", MaxKeys: int = 100) -> Dict[str, Any]:
        """列出存储桶中的对象。

        Args:
            bucket: 存储桶名称。
            prefix: 对象键前缀过滤。
            MaxKeys: 最大返回对象数量。

        Returns:
            包含对象列表的响应字典。
        """
        try:
            client = self.get_client()
            start_time_req = time.time()
            response = client.list_objects(Bucket=bucket, Prefix=prefix, MaxKeys=MaxKeys)
            elapsed_ms = int((time.time() - start_time_req) * 1000)

            # INFO 级别：记录对象列表查询结果
            contents = response.get("Contents", [])
            key_count = len(contents) if isinstance(contents, list) else 0
            logger.info(
                "COS list_objects: bucket={} prefix={} max_keys={} returned={} duration={}ms",
                bucket,
                prefix[:80] if len(prefix) > 80 else prefix,
                MaxKeys,
                key_count,
                elapsed_ms,
            )

            return response
        except Exception as e:
            from app.core.errors import DeltaSharingError, ErrorCode

            error_msg = str(e)

            # 提取 COS 错误码和请求 ID
            cos_error_code = None
            cos_request_id = None
            try:
                if hasattr(e, "get_origin_msg"):
                    cos_error_code = getattr(e, "get_error_code", lambda: None)()
                if hasattr(e, "get_request_id"):
                    cos_request_id = e.get_request_id()
            except Exception:
                pass

            # ERROR 级别：记录对象列表查询失败
            logger.error(
                "COS list_objects failed: bucket={} prefix={} error_code={} "
                "error={} cos_request_id={}",
                bucket,
                prefix[:80] if len(prefix) > 80 else prefix,
                cos_error_code,
                error_msg,
                cos_request_id,
            )

            if (
                "403" in error_msg
                or "身份验证" in error_msg
                or "签名" in error_msg
                or "SecretId" in error_msg
                or "SecretKey" in error_msg
            ):
                raise DeltaSharingError(
                    error_code=ErrorCode.COS_ACCESS_ERROR,
                    message=f"COS认证失败: {error_msg}",
                    status_code=403,
                    details={
                        "bucket": bucket,
                        "prefix": prefix,
                        "hint": "请检查COS_SECRET_ID和COS_SECRET_KEY环境变量是否正确配置",
                    },
                )
            elif "404" in error_msg or "NoSuchBucket" in error_msg:
                raise DeltaSharingError(
                    error_code=ErrorCode.COS_ACCESS_ERROR,
                    message=f"COS bucket或路径不存在: {error_msg}",
                    status_code=404,
                    details={"bucket": bucket, "prefix": prefix},
                )
            else:
                raise DeltaSharingError(
                    error_code=ErrorCode.COS_ACCESS_ERROR,
                    message=f"COS访问错误: {error_msg}",
                    status_code=500,
                    details={"bucket": bucket, "prefix": prefix},
                )


_global_cos_client: Optional[COSClient] = None


def get_cos_client() -> COSClient:
    """获取全局 COS 客户端实例。

    如果客户端尚未初始化，则先进行初始化。

    Returns:
        全局 COSClient 实例。
    """
    global _global_cos_client
    if _global_cos_client is None:
        _global_cos_client = COSClient()
        _global_cos_client.initialize()
    return _global_cos_client


def init_cos_client(config: Optional[Dict[str, Any]] = None) -> COSClient:
    """初始化全局 COS 客户端。

    Args:
        config: 配置字典，如果为 None 则使用全局配置。

    Returns:
        初始化的 COSClient 实例。
    """
    global _global_cos_client
    _global_cos_client = COSClient()
    _global_cos_client.initialize(config)
    return _global_cos_client
