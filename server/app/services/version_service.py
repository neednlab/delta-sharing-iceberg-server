"""
Version Service 模块

该模块提供快照版本号的业务逻辑编排。
封装「先查后分配」的版本号获取模式，消除路由层中的代码重复。

Service 职责:
- get_or_allocate_version: 封装「先查后分配」的版本号业务逻辑
- get_version_by_timestamp: 按时间戳查询快照版本信息
"""

from typing import Dict, Any

from app.repositories.version_repository import VersionRepository
from app.core.errors import DeltaSharingError, ErrorCode


class VersionService:
    """版本服务类

    封装版本号查询与分配的编排逻辑。
    不直接访问 Database，通过 VersionRepository 执行数据操作。

    Attributes:
        version_repo: VersionRepository 实例。
    """

    def __init__(self):
        """初始化 VersionService。"""
        self._version_repo = VersionRepository()

    def get_or_allocate_version(
        self,
        share_name: str,
        schema_name: str,
        table_name: str,
        snapshot_id: int,
        timestamp: int,
    ) -> int:
        """获取或分配版本号（幂等操作）。

        先按 snapshot_id 查询已有版本号：
        - 如果找到，检查 timestamp 是否需要修复（timestamp <= 0 时修复）
        - 如果未找到，分配新版本号并返回

        同时修复 timestamp=0 的历史遗留问题：
        当 find_by_snapshot() 命中但 timestamp <= 0 时，
        使用传入的有效 timestamp 更新记录。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            table_name: 表名称。
            snapshot_id: 快照 ID。
            timestamp: Unix 时间戳（毫秒）。

        Returns:
            版本号（已有或新分配的）。
        """
        version = self._version_repo.find_by_snapshot(
            share_name, schema_name, table_name, snapshot_id
        )
        if version is not None:
            # 修复 timestamp=0 的历史遗留问题
            if timestamp > 0:
                self._version_repo.update_timestamp(
                    share_name, schema_name, table_name, snapshot_id, timestamp
                )
            return version

        return self._version_repo.allocate(
            share_name, schema_name, table_name, snapshot_id, timestamp
        )

    def get_by_version(
        self,
        share_name: str,
        schema_name: str,
        table_name: str,
        version: int,
    ) -> Dict[str, Any]:
        """按 delta table version 逆向查询快照信息。

        封装 version → snapshot_id 的逆向查询，
        委托 VersionRepository.find_by_version() 执行。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            table_name: 表名称。
            version: Delta table 版本号。

        Returns:
            包含 snapshot_id、version、timestamp 的字典。

        Raises:
            DeltaSharingError: 当指定版本不存在时抛出 INVALID_REQUEST 错误。
        """
        result = self._version_repo.find_by_version(
            share_name, schema_name, table_name, version
        )
        if result is None:
            raise DeltaSharingError(
                error_code=ErrorCode.INVALID_REQUEST,
                message=f"Version {version} not found for table: {share_name}.{schema_name}.{table_name}",
                status_code=400,
            )
        return result

    def get_version_by_timestamp(
        self,
        share_name: str,
        schema_name: str,
        table_name: str,
        timestamp: int,
    ) -> Dict[str, Any]:
        """按时间戳查找最近的快照版本信息。

        委托 VersionRepository.find_by_timestamp() 执行查询。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            table_name: 表名称。
            timestamp: Unix 时间戳（秒）。

        Returns:
            包含 snapshot_id、version、timestamp 的字典。

        Raises:
            DeltaSharingError: 当指定时间戳下没有快照时抛出 INVALID_REQUEST 错误。
        """
        result = self._version_repo.find_by_timestamp(
            share_name, schema_name, table_name, timestamp
        )
        if result is None:
            raise DeltaSharingError(
                error_code=ErrorCode.INVALID_REQUEST,
                message=f"No snapshot found at or before timestamp {timestamp} "
                f"for table: {share_name}.{schema_name}.{table_name}",
                status_code=400,
            )
        return result
