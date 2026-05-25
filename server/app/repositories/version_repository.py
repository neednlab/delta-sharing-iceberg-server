"""
Version Repository 模块

该模块提供快照版本追踪的数据库 CRUD 操作。
封装所有 snapshot_version 表的数据库操作。

Repository 职责:
- find_by_snapshot: 按快照 ID 查询已分配的版本号
- find_by_version: 按 delta table version 逆向查询快照信息
- find_by_timestamp: 按时间戳查找最近的快照信息
- allocate: 为快照分配新的递增版本号
- update_timestamp: 按主键更新已有记录的 timestamp 字段
"""

from typing import Dict, Optional, Any

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.database import get_database, snapshot_version
from app.core.errors import DeltaSharingError, ErrorCode
from app.utils.time_utils import now_ts
from loguru import logger


class VersionRepository:
    """Version Repository 类

    封装所有 snapshot_version 表的数据库操作。
    使用 SQLAlchemy Core API 执行数据库操作，
    通过 Engine 上下文管理器管理事务边界。
    """

    def __init__(self):
        """初始化 VersionRepository。"""
        self._db = get_database()
        self._table = snapshot_version

    # ------------------------------------------------------------------
    # 公共方法：按快照 ID 查找版本号
    # ------------------------------------------------------------------

    def find_by_snapshot(
        self, share_name: str, schema_name: str, table_name: str, snapshot_id: int
    ) -> Optional[int]:
        """根据快照 ID 查询已分配的版本号。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            table_name: 表名称。
            snapshot_id: 快照 ID。

        Returns:
            如果找到则返回版本号，否则返回 None。
        """
        t = self._table
        with self._db.get_engine().connect() as conn:
            result = conn.execute(
                t.select().where(
                    t.c.share_name == share_name.lower(),
                    t.c.schema_name == schema_name.lower(),
                    t.c.table_name == table_name.lower(),
                    t.c.snapshot_id == snapshot_id,
                )
            )
            row = result.fetchone()
            return row.version if row else None

    # ------------------------------------------------------------------
    # 公共方法：按 delta table version 逆向查询快照信息
    # ------------------------------------------------------------------

    def find_by_version(
        self, share_name: str, schema_name: str, table_name: str, version: int
    ) -> Optional[Dict[str, Any]]:
        """按 delta table version 逆向查询 (snapshot_id, version, timestamp)。

        用于时间旅行查询：客户端指定 version 参数时，
        需要通过此方法反向查出对应的 iceberg snapshot_id。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            table_name: 表名称。
            version: Delta table 版本号。

        Returns:
            包含 snapshot_id、version、timestamp 的字典，如果未找到则返回 None。
        """
        t = self._table
        with self._db.get_engine().connect() as conn:
            result = conn.execute(
                t.select()
                .where(
                    t.c.share_name == share_name.lower(),
                    t.c.schema_name == schema_name.lower(),
                    t.c.table_name == table_name.lower(),
                    t.c.version == version,
                )
                .limit(1)
            )
            row = result.fetchone()
            if row:
                return {
                    "snapshot_id": row.snapshot_id,
                    "version": row.version,
                    "timestamp": row.timestamp,
                }
            return None

    # ------------------------------------------------------------------
    # 公共方法：按时间戳查找快照
    # ------------------------------------------------------------------

    def find_by_timestamp(
        self, share_name: str, schema_name: str, table_name: str, timestamp: int
    ) -> Optional[Dict[str, Any]]:
        """根据时间戳查找不晚于指定时间戳的最新快照。

        按 timestamp DESC, version DESC 排序，取第一条。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            table_name: 表名称。
            timestamp: Unix 时间戳（秒）。

        Returns:
            包含 snapshot_id、version、timestamp 的字典，如果未找到则返回 None。
        """
        t = self._table
        with self._db.get_engine().connect() as conn:
            result = conn.execute(
                t.select()
                .where(
                    t.c.share_name == share_name.lower(),
                    t.c.schema_name == schema_name.lower(),
                    t.c.table_name == table_name.lower(),
                    t.c.timestamp <= timestamp,
                )
                .order_by(t.c.timestamp.desc(), t.c.version.desc())
                .limit(1)
            )
            row = result.fetchone()
            if row:
                return {
                    "snapshot_id": row.snapshot_id,
                    "version": row.version,
                    "timestamp": row.timestamp,
                }
            return None

    # ------------------------------------------------------------------
    # 公共方法：分配新版本号
    # ------------------------------------------------------------------

    def allocate(
        self,
        share_name: str,
        schema_name: str,
        table_name: str,
        snapshot_id: int,
        timestamp: int,
    ) -> int:
        """为指定快照分配新的递增版本号。

        分配逻辑：
        - 查询该表当前最大版本号，新版本号为 max_version + 1
        - 如果无现有记录，从 1 开始
        - 所有名称字段以小写形式存储
        - 如果传入的 timestamp 无效（≤ 0），使用当前时间作为默认值，
          防止 timestamp=0 污染 find_by_timestamp 查询

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            table_name: 表名称。
            snapshot_id: 快照 ID。
            timestamp: Unix 时间戳（毫秒）。

        Returns:
            新分配的版本号。

        Raises:
            sqlalchemy.exc.IntegrityError: 如果同一快照重复分配（UNIQUE 约束冲突）。
        """
        # 防止 timestamp=0/负值 污染 find_by_timestamp 查询
        if timestamp <= 0:
            fallback = now_ts() * 1000
            logger.warning(
                f"Invalid timestamp ({timestamp}) for snapshot_id={snapshot_id}, "
                f"using current time as fallback: {fallback}"
            )
            timestamp = fallback

        t = self._table
        with self._db.get_engine().begin() as conn:
            # 查询当前最大版本号
            result = conn.execute(
                t.select()
                .with_only_columns(func.max(t.c.version).label("max_version"))
                .where(
                    t.c.share_name == share_name.lower(),
                    t.c.schema_name == schema_name.lower(),
                    t.c.table_name == table_name.lower(),
                )
            )
            row = result.fetchone()
            max_version = row.max_version if row and row.max_version is not None else 0
            new_version = max_version + 1

            # 插入新版本记录
            try:
                conn.execute(
                    t.insert().values(
                        share_name=share_name.lower(),
                        schema_name=schema_name.lower(),
                        table_name=table_name.lower(),
                        snapshot_id=snapshot_id,
                        version=new_version,
                        timestamp=timestamp,
                        created_at=now_ts(),
                    )
                )
            except IntegrityError as e:
                raise DeltaSharingError(
                    ErrorCode.INTERNAL_ERROR,
                    f"Snapshot version already allocated for "
                    f"{share_name}.{schema_name}.{table_name} snapshot_id={snapshot_id}",
                    status_code=409,
                    details={"db_error": str(e.orig) if e.orig else str(e)},
                )
            except OperationalError as e:
                raise DeltaSharingError(
                    ErrorCode.INTERNAL_ERROR,
                    "Database operation failed",
                    status_code=500,
                    details={"db_error": str(e)},
                )

        return new_version

    # ------------------------------------------------------------------
    # 公共方法：更新已有记录的时间戳
    # ------------------------------------------------------------------

    def update_timestamp(
        self,
        share_name: str,
        schema_name: str,
        table_name: str,
        snapshot_id: int,
        timestamp: int,
    ) -> bool:
        """按主键更新已有 snapshot_version 记录的 timestamp 字段。

        用于修复 timestamp=0 的历史遗留问题。
        利用 UNIQUE(share_name, schema_name, table_name, snapshot_id) 约束定位记录。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            table_name: 表名称。
            snapshot_id: 快照 ID。
            timestamp: 正确的 Unix 时间戳（毫秒）。

        Returns:
            True 如果更新了至少一行，False 如果没有匹配记录。
        """
        t = self._table
        with self._db.get_engine().begin() as conn:
            try:
                result = conn.execute(
                    t.update()
                    .values(timestamp=timestamp)
                    .where(
                        t.c.share_name == share_name.lower(),
                        t.c.schema_name == schema_name.lower(),
                        t.c.table_name == table_name.lower(),
                        t.c.snapshot_id == snapshot_id,
                        t.c.timestamp <= 0,
                    )
                )
            except IntegrityError as e:
                raise DeltaSharingError(
                    ErrorCode.INTERNAL_ERROR,
                    f"Failed to update timestamp for "
                    f"{share_name}.{schema_name}.{table_name} snapshot_id={snapshot_id}",
                    status_code=500,
                    details={"db_error": str(e.orig) if e.orig else str(e)},
                )
            except OperationalError as e:
                raise DeltaSharingError(
                    ErrorCode.INTERNAL_ERROR,
                    "Database operation failed",
                    status_code=500,
                    details={"db_error": str(e)},
                )
            updated = result.rowcount > 0
            if updated:
                logger.info(
                    f"已修复 snapshot_version timestamp: "
                    f"{share_name}.{schema_name}.{table_name} "
                    f"snapshot_id={snapshot_id} → timestamp={timestamp}"
                )
            return updated
