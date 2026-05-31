"""
腾讯云 DLC 客户端模块

该模块封装了腾讯云数据湖计算（DLC）服务的 API 调用。
DLC API 用于获取 Iceberg 表的元数据位置信息。

DLC (Data Lake Computing) 是腾讯云提供的数据湖分析服务，
可与 COS 存储配合使用来管理 Iceberg 表。
"""

from typing import Optional, Dict, Any
import json

from tencentcloud.dlc.v20210125.dlc_client import DlcClient as DLCClient
from tencentcloud.dlc.v20210125.models import (
    DescribeTableRequest,
    DescribeTablesRequest,
)
from tencentcloud.common import credential as tc_credential
from tencentcloud.common.profile import client_profile
from tencentcloud.common.profile.http_profile import HttpProfile

from app.core.config import DLCConfig


class DLCError(Exception):
    """DLC 相关错误基类。"""

    pass


class DLCConfigError(DLCError):
    """DLC 配置错误，当凭证未配置时抛出。"""

    pass


class DLCAPIError(DLCError):
    """DLC API 调用错误。"""

    def __init__(self, message: str, code: Optional[str] = None):
        super().__init__(message)
        self.code = code


class DLCClientWrapper:
    """腾讯云 DLC 客户端封装类

    该类封装了与腾讯云 DLC 服务交互的功能，
    主要用于获取 Iceberg 表的元数据位置。

    Attributes:
        config: DLC 配置实例。
        _client: DLC 客户端实例。
    """

    def __init__(self, config: DLCConfig):
        """初始化 DLC 客户端。

        Args:
            config: DLC 配置实例。
        """
        self.config = config
        self._client: Optional[DLCClient] = None

    def _get_client(self) -> DLCClient:
        """获取或创建 DLC 客户端实例。

        Returns:
            DLC 客户端实例。
        """
        if self._client is None:
            cred = tc_credential.Credential(
                self.config.secret_id,
                self.config.secret_key,
            )
            http_profile = HttpProfile()
            http_profile.endpoint = self.config.endpoint or "dlc.tencentcloudapi.com"
            http_profile.reqTimeout = 30

            client_profile_cfg = client_profile.ClientProfile()
            client_profile_cfg.httpProfile = http_profile

            self._client = DLCClient(
                cred,
                self.config.region,
                client_profile_cfg,
            )
        return self._client

    def describe_table(self, database_name: str, table_name: str) -> Dict[str, Any]:
        """查询表详情。

        调用 DLC DescribeTable API 获取指定表的详细信息。

        Args:
            database_name: 数据库名称。
            table_name: 表名称。

        Returns:
            包含 API 响应原始数据和解析后数据的字典。
        """
        if not self.config.secret_id or not self.config.secret_key:
            raise DLCConfigError(
                "DLC credentials not configured. Set DLC_SECRET_ID and DLC_SECRET_KEY."
            )

        client = self._get_client()
        request = DescribeTableRequest()
        request.DatabaseName = database_name
        request.TableName = table_name

        try:
            response = client.DescribeTable(request)
            response_str = (
                response.to_json_string()
                if hasattr(response, "to_json_string")
                else str(response)
            )
            return {
                "raw_response": response_str,
                "parsed": json.loads(response_str) if response_str else {},
            }
        except Exception as e:
            raise DLCAPIError(f"Failed to describe table: {str(e)}")

    def describe_tables(self, database_name: str) -> Dict[str, Any]:
        """查询数据库下的所有表。

        调用 DLC DescribeTables API 获取指定数据库下的所有表信息（全量返回）。

        Args:
            database_name: 数据库名称。

        Returns:
            包含 TableList、TotalCount 和原始响应的字典。

        Raises:
            DLCConfigError: 当 DLC 凭证未配置时。
            DLCAPIError: 当 API 调用失败时。
        """
        if not self.config.secret_id or not self.config.secret_key:
            raise DLCConfigError(
                "DLC credentials not configured. Set DLC_SECRET_ID and DLC_SECRET_KEY."
            )

        client = self._get_client()
        request = DescribeTablesRequest()
        request.DatabaseName = database_name
        request.TableType = "EXTERNAL_TABLE"
        request.TableFormat = "ICEBERG"
        request.Limit = 1000
        request.Offset = 0

        try:
            response = client.DescribeTables(request)
            response_str = (
                response.to_json_string()
                if hasattr(response, "to_json_string")
                else str(response)
            )
            parsed = json.loads(response_str) if response_str else {}

            table_list = []
            if "TableList" in parsed:
                for table_info in parsed["TableList"]:
                    table_base_info = table_info.get("TableBaseInfo", {})
                    table_name = table_base_info.get("TableName")
                    if not table_name:
                        continue
                    table_list.append(
                        {
                            "name": table_name,
                            "location": table_info.get("Location"),
                            "properties": table_info.get("Properties"),
                            "partitions": table_info.get("Partitions"),
                        }
                    )

            return {
                "table_list": table_list,
                "total_count": parsed.get("TotalCount", len(table_list)),
                "raw_response": response_str,
            }
        except DLCConfigError:
            raise
        except Exception as e:
            raise DLCAPIError(f"Failed to describe tables: {str(e)}")

    @staticmethod
    def extract_table_info(api_response: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """从 DLC DescribeTables 响应中提取表信息列表。

        Args:
            api_response: DLC DescribeTables API 的响应字典。

        Returns:
            包含表名、位置、属性和分区信息的字典列表。
        """
        table_list = []
        parsed = api_response.get("parsed", api_response)

        if isinstance(parsed, dict) and "TableList" in parsed:
            for table_info in parsed["TableList"]:
                table_base_info = table_info.get("TableBaseInfo", {})
                table_name = table_base_info.get("TableName")
                if not table_name:
                    continue
                table_list.append(
                    {
                        "name": table_name,
                        "location": table_info.get("Location"),
                        "properties": table_info.get("Properties"),
                        "partitions": table_info.get("Partitions"),
                    }
                )

        return table_list if table_list else None

    @staticmethod
    def extract_metadata_location(api_response: Dict[str, Any]) -> Optional[str]:
        """从 DLC API 响应中提取元数据位置。

        DLC API 返回的表属性中包含 metadata_location 字段，
        该函数负责从各种可能的响应格式中提取该字段。

        Args:
            api_response: DLC API 的响应字典。

        Returns:
            元数据位置 URL 字符串，如果未找到则返回 None。
        """
        parsed = api_response.get("parsed", api_response)

        if isinstance(parsed, dict):
            if "Properties" in parsed:
                properties = parsed["Properties"]
                if isinstance(properties, list):
                    for prop in properties:
                        if prop.get("Key") == "metadata_location":
                            return prop.get("Value")
                elif isinstance(properties, dict):
                    return properties.get("metadata_location")

            if "Table" in parsed:
                table_info = parsed["Table"]
                if isinstance(table_info, dict):
                    properties = table_info.get("Properties")
                    if isinstance(properties, list):
                        for prop in properties:
                            if prop.get("Key") == "metadata_location":
                                return prop.get("Value")
                    elif isinstance(properties, dict):
                        return properties.get("metadata_location")

        return None


_global_dlc_client: Optional[DLCClientWrapper] = None


def init_dlc_client(config: DLCConfig) -> DLCClientWrapper:
    """初始化全局 DLC 客户端实例。

    Args:
        config: DLC 配置实例。

    Returns:
        DLCClientWrapper 实例。
    """
    global _global_dlc_client
    _global_dlc_client = DLCClientWrapper(config)
    return _global_dlc_client


def get_dlc_client() -> Optional[DLCClientWrapper]:
    """获取全局 DLC 客户端实例。

    Returns:
        DLCClientWrapper 实例，如果未初始化则返回 None。
    """
    return _global_dlc_client
