"""
Table 服务模块

该模块提供表的配置查询功能。
"""

from typing import Optional, Dict, Any
from app.core.config import get_table_config, get_config


class TableService:
    """Table 服务类

    该类提供表配置信息的查询功能。

    Methods:
        get_table_config: 获取表的详细配置信息。
        table_exists: 检查表是否存在。
    """

    def get_table_config(
        self, share_name: str, schema_name: str, table_name: str
    ) -> Optional[Dict[str, Any]]:
        """获取表的详细配置信息。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            table_name: 表名称。

        Returns:
            包含 location、bucket、region 的字典，如果表不存在则返回 None。
        """
        from app.core.config import get_table_config

        config = get_table_config(share_name, schema_name, table_name)
        if config:
            location = getattr(config, "cos_path", None) or config.location
            # 内联 COS 路径解析（cosn://bucket/key → bucket），
            # 避免引入 IcebergService 重量级依赖（其 __init__ 会初始化 DLC/COS/DB）
            bucket = ""
            if location and location.startswith("cosn://"):
                path_part = location[len("cosn://") :]
                parts = path_part.split("/", 1)
                bucket = parts[0]
            return {
                "location": location,
                "bucket": bucket,
                "region": get_config().cos.region,
            }
        return None

    def table_exists(self, share_name: str, schema_name: str, table_name: str) -> bool:
        """检查表是否存在。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            table_name: 表名称。

        Returns:
            如果表存在返回 True，否则返回 False。
        """
        return get_table_config(share_name, schema_name, table_name) is not None
