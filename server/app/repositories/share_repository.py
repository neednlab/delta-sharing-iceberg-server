"""
Share Repository 模块

该模块提供 Share、Schema 和 Table 实体的数据库 CRUD 操作。
封装所有 shares、schemas、tables 表的数据库操作。

Repository 职责:
- create_share: 创建 Share 实体
- get_share: 获取单个 Share
- list_shares: 列出所有 Share
- update_share: 更新 Share
- delete_share: 删除 Share
- rename_share: 重命名 Share
- create_schema: 创建 Schema
- update_schema: 更新 Schema
- delete_schema: 删除 Schema
- create_table: 创建 Table
- update_table: 更新 Table
- delete_table: 删除 Table
- list_share_objects: 列出 Share 下的所有 Schema 和 Table
"""

import json
import uuid
from typing import Dict, List, Optional, Any

from sqlalchemy import and_, or_, case, func, Connection
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.database import get_database, shares, shared_schemas, shared_tables
from app.core.errors import DeltaSharingError, ErrorCode
from app.utils.time_utils import now_ts


class ShareRepository:
    """Share Repository 类

    封装所有 Share、Schema 和 Table 的数据库操作。
    使用 SQLAlchemy Core API 执行数据库操作，
    通过 Engine 上下文管理器管理事务边界。
    """

    def __init__(self):
        """初始化 ShareRepository。"""
        self._db = get_database()
        self._sh = shares
        self._ss = shared_schemas
        self._st = shared_tables

    # ------------------------------------------------------------------
    # 私有辅助方法：ID 查找
    # ------------------------------------------------------------------

    @staticmethod
    def _get_share_id(conn: Connection, share_name: str) -> Optional[str]:
        """根据 share_name 查找 share_id（不区分大小写）。

        Args:
            conn: SQLAlchemy Connection 对象。
            share_name: Share 名称。

        Returns:
            share_id 字符串，未找到返回 None。
        """
        sh = shares
        result = conn.execute(
            sh.select()
            .with_only_columns(sh.c.share_id)
            .where(sh.c.share_name == share_name.lower())
        )
        row = result.fetchone()
        return row.share_id if row else None

    @staticmethod
    def _get_schema_id(
        conn: Connection, share_id: str, schema_name: str
    ) -> Optional[str]:
        """根据 share_id 和 schema_name 查找 schema_id（不区分大小写）。

        Args:
            conn: SQLAlchemy Connection 对象。
            share_id: Share UUID。
            schema_name: Schema 名称。

        Returns:
            schema_id 字符串，未找到返回 None。
        """
        ss = shared_schemas
        result = conn.execute(
            ss.select()
            .with_only_columns(ss.c.schema_id)
            .where(
                ss.c.share_id == share_id,
                ss.c.schema_name == schema_name.lower(),
            )
        )
        row = result.fetchone()
        return row.schema_id if row else None

    # ------------------------------------------------------------------
    # 私有辅助方法：行数据 → 字典转换
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_share_dict(row) -> Dict[str, Any]:
        """将 shares 表行数据转换为字典。

        Args:
            row: SQLAlchemy Row 对象，包含 shares 表的所有列。

        Returns:
            标准化的 Share 字典。
        """
        properties = json.loads(row.properties) if row.properties else None
        return {
            "share_id": row.share_id,
            "share_name": row.share_name,
            "display_name": row.display_name,
            "comment": row.comment,
            "properties": properties,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    @staticmethod
    def _row_to_schema_dict(row, share_name: str = "") -> Dict[str, Any]:
        """将 shared_schemas 表行数据转换为字典。

        Args:
            row: SQLAlchemy Row 对象，包含 shared_schemas 表的所有列（可能 JOIN 了 shares）。
            share_name: Share 名称（可选，当 row 中不含 share_name 时通过参数传入）。

        Returns:
            标准化的 Schema 字典。
        """
        result_share_name = (
            row.share_name
            if hasattr(row, "share_name") and row.share_name
            else share_name
        )
        return {
            "schema_id": row.schema_id,
            "share_id": getattr(row, "share_id", ""),
            "share_name": result_share_name,
            "schema_name": row.schema_name,
            "metastore_db": row.metastore_db,
            "created_at": getattr(row, "created_at", None),
            "updated_at": getattr(row, "updated_at", None),
        }

    @staticmethod
    def _row_to_table_dict(row, schema_name: str = "") -> Dict[str, Any]:
        """将 shared_tables 表行数据转换为字典。

        Args:
            row: SQLAlchemy Row 对象，包含 shared_tables 表的所有列（可能 JOIN 了 shares/schemas）。
            schema_name: Schema 名称（可选，当 row 中不含 schema_name 时通过参数传入）。

        Returns:
            标准化的 Table 字典。
        """
        auxiliary_locations = (
            json.loads(row.auxiliary_locations) if row.auxiliary_locations else None
        )
        result_schema_name = getattr(row, "schema_name", schema_name)
        return {
            "table_id": row.table_id,
            "share_id": getattr(row, "share_id", ""),
            "share_name": getattr(row, "share_name", ""),
            "linked_schema_id": getattr(row, "linked_schema_id", None),
            "schema_name": result_schema_name or "",
            "table_name": row.table_name,
            "location": row.location,
            "metastore_db": row.metastore_db,
            "metastore_table": row.metastore_table,
            "auxiliary_locations": auxiliary_locations,
            "created_at": getattr(row, "created_at", None),
            "updated_at": getattr(row, "updated_at", None),
        }

    # ------------------------------------------------------------------
    # 公共轻量查询方法
    # ------------------------------------------------------------------

    def get_share_id(self, share_name: str) -> Optional[str]:
        """根据 share_name 获取 share_id（公共方法，供外部服务调用）。

        Args:
            share_name: Share 名称。

        Returns:
            share_id 字符串，未找到返回 None。
        """
        with self._db.get_engine().connect() as conn:
            return self._get_share_id(conn, share_name)

    # ------------------------------------------------------------------
    # Share CRUD 操作
    # ------------------------------------------------------------------

    def create_share(
        self,
        name: str,
        display_name: Optional[str] = None,
        comment: Optional[str] = None,
        properties: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """创建新的 Share 实体。

        Args:
            name: Share 名称。
            display_name: 显示名称（可选）。
            comment: 描述说明（可选）。
            properties: 键值对属性（可选）。

        Returns:
            创建的 Share 字典，包含 id、name、display_name、comment、properties。

        Raises:
            DeltaSharingError: 如果 Share 名称已存在 (SHARE_ALREADY_EXISTS)。
        """
        share_id = str(uuid.uuid4())
        current_ts = now_ts()
        properties_json = json.dumps(properties) if properties else None
        sh = self._sh

        with self._db.get_engine().begin() as conn:
            if self._get_share_id(conn, name):
                raise DeltaSharingError(
                    ErrorCode.SHARE_ALREADY_EXISTS,
                    f"Share '{name}' already exists",
                    status_code=409,
                )

            try:
                conn.execute(
                    sh.insert().values(
                        share_id=share_id,
                        share_name=name.lower(),
                        display_name=display_name,
                        comment=comment,
                        properties=properties_json,
                        created_at=current_ts,
                        updated_at=current_ts,
                    )
                )
            except IntegrityError as e:
                raise DeltaSharingError(
                    ErrorCode.SHARE_ALREADY_EXISTS,
                    f"Share '{name}' already exists",
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

        return {
            "share_id": share_id,
            "share_name": name.lower(),
            "display_name": display_name,
            "comment": comment,
            "properties": properties,
        }

    def get_share(self, share_name: str) -> Optional[Dict[str, Any]]:
        """获取单个 Share 实体。

        Args:
            share_name: Share 名称。

        Returns:
            Share 字典，如果不存在则返回 None。
        """
        sh = self._sh
        with self._db.get_engine().connect() as conn:
            result = conn.execute(
                sh.select().where(sh.c.share_name == share_name.lower())
            )
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_share_dict(row)

    def list_shares(self) -> List[Dict[str, Any]]:
        """列出所有 Share 实体。

        Returns:
            Share 字典列表。
        """
        sh = self._sh
        with self._db.get_engine().connect() as conn:
            result = conn.execute(sh.select().order_by(sh.c.share_name))
            return [self._row_to_share_dict(row) for row in result.fetchall()]

    def update_share(
        self,
        share_name: str,
        display_name: Optional[str] = None,
        comment: Optional[str] = None,
        properties: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """更新 Share 实体。

        Args:
            share_name: Share 名称。
            display_name: 显示名称（可选）。
            comment: 描述说明（可选）。
            properties: 键值对属性（可选）。

        Returns:
            更新后的 Share 字典，如果不存在则返回 None。
        """
        sh = self._sh
        current_ts = now_ts()

        with self._db.get_engine().begin() as conn:
            if not self._get_share_id(conn, share_name):
                return None

            update_values = {"updated_at": current_ts}

            if display_name is not None:
                update_values["display_name"] = display_name
            if comment is not None:
                update_values["comment"] = comment
            if properties is not None:
                update_values["properties"] = json.dumps(properties)

            try:
                conn.execute(
                    sh.update()
                    .values(**update_values)
                    .where(sh.c.share_name == share_name.lower())
                )
            except IntegrityError as e:
                raise DeltaSharingError(
                    ErrorCode.INTERNAL_ERROR,
                    f"Failed to update share '{share_name}'",
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

        return self.get_share(share_name)

    def delete_share(self, share_name: str) -> bool:
        """删除 Share 实体及其所有关联的 Schema 和 Table。

        Args:
            share_name: Share 名称。

        Returns:
            如果成功删除返回 True，否则返回 False。
        """
        sh = self._sh
        st = self._st
        ss = self._ss

        with self._db.get_engine().begin() as conn:
            share_id = self._get_share_id(conn, share_name)
            if not share_id:
                return False

            # 级联删除关联数据
            try:
                conn.execute(st.delete().where(st.c.share_id == share_id))
                conn.execute(ss.delete().where(ss.c.share_id == share_id))
                conn.execute(sh.delete().where(sh.c.share_id == share_id))
            except IntegrityError as e:
                raise DeltaSharingError(
                    ErrorCode.INTERNAL_ERROR,
                    f"Failed to delete share '{share_name}'",
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
            return True

    def rename_share(self, share_name: str, new_name: str) -> Optional[Dict[str, Any]]:
        """重命名 Share 实体。

        Args:
            share_name: 当前 Share 名称。
            new_name: 新名称。

        Returns:
            更新后的 Share 字典，如果不存在则返回 None。

        Raises:
            DeltaSharingError: 如果新名称已存在 (SHARE_ALREADY_EXISTS)。
        """
        sh = self._sh
        current_ts = now_ts()

        with self._db.get_engine().begin() as conn:
            share_id = self._get_share_id(conn, share_name)
            if not share_id:
                return None

            # 检查新名称是否被其他 share 占用（排除自身）
            result = conn.execute(
                sh.select()
                .with_only_columns(sh.c.share_id)
                .where(
                    sh.c.share_name == new_name.lower(),
                    sh.c.share_name != share_name.lower(),
                )
            )
            if result.fetchone():
                raise DeltaSharingError(
                    ErrorCode.SHARE_ALREADY_EXISTS,
                    f"Share '{new_name}' already exists",
                    status_code=409,
                )

            try:
                conn.execute(
                    sh.update()
                    .values(share_name=new_name.lower(), updated_at=current_ts)
                    .where(sh.c.share_id == share_id)
                )
            except IntegrityError as e:
                raise DeltaSharingError(
                    ErrorCode.SHARE_ALREADY_EXISTS,
                    f"Share '{new_name}' already exists",
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

        return self.get_share(new_name)

    # ------------------------------------------------------------------
    # Schema CRUD 操作
    # ------------------------------------------------------------------

    def create_schema(
        self,
        share_name: str,
        schema_name: str,
        metastore_db: str = "",
    ) -> Dict[str, Any]:
        """创建新的 Schema 实体。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            metastore_db: Metastore 数据库名称。

        Returns:
            创建的 Schema 字典。

        Raises:
            DeltaSharingError: 如果 Share 不存在 (SHARE_NOT_FOUND)
                或 Schema 已存在 (SCHEMA_ALREADY_EXISTS)。
        """
        ss = self._ss
        current_ts = now_ts()
        schema_id = str(uuid.uuid4())

        with self._db.get_engine().begin() as conn:
            share_id = self._get_share_id(conn, share_name)
            if not share_id:
                raise DeltaSharingError(
                    ErrorCode.SHARE_NOT_FOUND,
                    f"Share '{share_name}' not found",
                    status_code=404,
                )

            if self._get_schema_id(conn, share_id, schema_name):
                raise DeltaSharingError(
                    ErrorCode.SCHEMA_ALREADY_EXISTS,
                    f"Schema '{schema_name}' already exists in share '{share_name}'",
                    status_code=409,
                )

            try:
                conn.execute(
                    ss.insert().values(
                        schema_id=schema_id,
                        share_id=share_id,
                        schema_name=schema_name.lower(),
                        metastore_db=metastore_db,
                        created_at=current_ts,
                        updated_at=current_ts,
                    )
                )
            except IntegrityError as e:
                raise DeltaSharingError(
                    ErrorCode.SCHEMA_ALREADY_EXISTS,
                    f"Schema '{schema_name}' already exists in share '{share_name}'",
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

        return {
            "schema_id": schema_id,
            "share_name": share_name.lower(),
            "schema_name": schema_name.lower(),
            "metastore_db": metastore_db,
        }

    def update_schema(
        self,
        share_name: str,
        schema_name: str,
        metastore_db: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """更新 Schema 实体。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            metastore_db: Metastore 数据库名称（可选）。

        Returns:
            更新后的 Schema 字典，如果不存在则返回 None。
        """
        ss = self._ss
        current_ts = now_ts()

        with self._db.get_engine().begin() as conn:
            share_id = self._get_share_id(conn, share_name)
            if not share_id:
                return None

            if not self._get_schema_id(conn, share_id, schema_name):
                return None

            update_values = {"updated_at": current_ts}
            if metastore_db is not None:
                update_values["metastore_db"] = metastore_db

            try:
                conn.execute(
                    ss.update()
                    .values(**update_values)
                    .where(
                        ss.c.share_id == share_id,
                        ss.c.schema_name == schema_name.lower(),
                    )
                )
            except IntegrityError as e:
                raise DeltaSharingError(
                    ErrorCode.INTERNAL_ERROR,
                    f"Failed to update schema '{schema_name}' in share '{share_name}'",
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

        return self.get_schema(share_name, schema_name)

    def get_schema(self, share_name: str, schema_name: str) -> Optional[Dict[str, Any]]:
        """获取 Schema 实体。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。

        Returns:
            Schema 字典，如果不存在则返回 None。
        """
        sh = self._sh
        ss = self._ss

        with self._db.get_engine().connect() as conn:
            j = ss.join(sh, ss.c.share_id == sh.c.share_id)
            result = conn.execute(
                ss.select()
                .with_only_columns(
                    ss.c.schema_id,
                    ss.c.share_id,
                    sh.c.share_name,
                    ss.c.schema_name,
                    ss.c.metastore_db,
                    ss.c.created_at,
                    ss.c.updated_at,
                )
                .select_from(j)
                .where(
                    sh.c.share_name == share_name.lower(),
                    ss.c.schema_name == schema_name.lower(),
                )
            )
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_schema_dict(row)

    def delete_schema(self, share_name: str, schema_name: str) -> bool:
        """删除 Schema 实体及其所有关联的 Table。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。

        Returns:
            如果成功删除返回 True，否则返回 False。
        """
        ss = self._ss
        st = self._st

        with self._db.get_engine().begin() as conn:
            share_id = self._get_share_id(conn, share_name)
            if not share_id:
                return False

            schema_id = self._get_schema_id(conn, share_id, schema_name)
            if not schema_id:
                return False

            # 级联删除关联表
            try:
                conn.execute(st.delete().where(st.c.linked_schema_id == schema_id))
                conn.execute(ss.delete().where(ss.c.schema_id == schema_id))
            except IntegrityError as e:
                raise DeltaSharingError(
                    ErrorCode.INTERNAL_ERROR,
                    f"Failed to delete schema '{schema_name}' from share '{share_name}'",
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
            return True

    # ------------------------------------------------------------------
    # Table CRUD 操作
    # ------------------------------------------------------------------

    def create_table(
        self,
        share_name: str,
        schema_name: str,
        table_name: str,
        location: str = "",
        metastore_db: str = "",
        metastore_table: Optional[str] = None,
        auxiliary_locations: Optional[List[str]] = None,
        linked_schema_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """创建新的 Table 实体。

        Args:
            share_name: Share 名称。
            schema_name: Delta Sharing 协议中的 Schema 名称。
                当 linked_schema_id IS NOT NULL 时可为空字符串（从 shared_schemas 继承）。
                当 linked_schema_id IS NULL（直绑 Share）时必填。
            table_name: Table 名称。
            location: 表的存储位置路径。
            metastore_db: Metastore 数据库名称。
            metastore_table: Metastore 表名称。
            auxiliary_locations: 辅助存储位置列表。
            linked_schema_id: 关联的 schema ID，如果为 None 表示直接绑定到 share。

        Returns:
            创建的 Table 字典。

        Raises:
            DeltaSharingError: 如果 Share 不存在、Schema 不存在、缺少必要参数
                或 Table 已存在。
        """
        st = self._st

        with self._db.get_engine().begin() as conn:
            share_id = self._get_share_id(conn, share_name)
            if not share_id:
                raise DeltaSharingError(
                    ErrorCode.SHARE_NOT_FOUND,
                    f"Share '{share_name}' not found",
                    status_code=404,
                )

            if linked_schema_id is not None:
                schema_id = self._get_schema_id(conn, share_id, schema_name)
                if not schema_id:
                    raise DeltaSharingError(
                        ErrorCode.SCHEMA_NOT_FOUND,
                        f"Schema '{schema_name}' not found in share '{share_name}'",
                        status_code=404,
                    )
                linked_schema_id = schema_id
                # 关联 Schema 的 Table，shared_tables.schema_name 存空字符串
                db_schema_name = ""
            else:
                linked_schema_id = None
                # 直绑 Share 的 Table，schema_name 必填
                db_schema_name = schema_name
                if not db_schema_name:
                    raise DeltaSharingError(
                        ErrorCode.INVALID_REQUEST,
                        f"schema_name is required when table is directly bound to "
                        f"share '{share_name}'",
                        status_code=400,
                    )
                # metastore_db 为空时默认取 schema_name
                if not metastore_db:
                    metastore_db = db_schema_name

            # 检查 Table 是否已存在
            result = conn.execute(
                st.select()
                .with_only_columns(st.c.table_id)
                .where(
                    st.c.share_id == share_id,
                    st.c.linked_schema_id == linked_schema_id,
                    st.c.metastore_table == metastore_table,
                )
            )
            if result.fetchone():
                raise DeltaSharingError(
                    ErrorCode.TABLE_ALREADY_EXISTS,
                    f"Table '{table_name}' already exists in share '{share_name}'",
                    status_code=409,
                )

            current_ts = now_ts()
            auxiliary_locations_json = (
                json.dumps(auxiliary_locations) if auxiliary_locations else None
            )
            table_id = str(uuid.uuid4())

            try:
                conn.execute(
                    st.insert().values(
                        table_id=table_id,
                        share_id=share_id,
                        linked_schema_id=linked_schema_id,
                        table_name=table_name.lower(),
                        location=location,
                        metastore_db=metastore_db,
                        metastore_table=metastore_table,
                        schema_name=db_schema_name.lower() if db_schema_name else "",
                        auxiliary_locations=auxiliary_locations_json,
                        created_at=current_ts,
                        updated_at=current_ts,
                    )
                )
            except IntegrityError as e:
                raise DeltaSharingError(
                    ErrorCode.TABLE_ALREADY_EXISTS,
                    f"Table '{table_name}' already exists in share '{share_name}'",
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

        return {
            "table_id": table_id,
            "share_name": share_name.lower(),
            "linked_schema_id": linked_schema_id,
            "schema_name": schema_name.lower(),
            "table_name": table_name.lower(),
            "location": location,
            "metastore_db": metastore_db,
            "metastore_table": metastore_table,
            "auxiliary_locations": auxiliary_locations,
        }

    def update_table(
        self,
        share_name: str,
        schema_name: str = "",
        table_name: str = "",
        location: Optional[str] = None,
        metastore_db: Optional[str] = None,
        metastore_table: Optional[str] = None,
        auxiliary_locations: Optional[List[str]] = None,
        new_schema_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """更新 Table 实体。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称（可选，为空时匹配所有 schema）。
            table_name: Table 名称。
            location: 表的存储位置路径（可选）。
            metastore_db: Metastore 数据库名称（可选）。
            metastore_table: Metastore 表名称（可选）。
            auxiliary_locations: 辅助存储位置列表（可选）。
            new_schema_name: 新的 Schema 名称（仅当 linked_schema_id IS NULL 时生效）。

        Returns:
            更新后的 Table 字典，如果不存在则返回 None。
        """
        st = self._st

        with self._db.get_engine().begin() as conn:
            share_id = self._get_share_id(conn, share_name)
            if not share_id:
                return None

            # 查找 table 记录
            table_row = self._find_table_row(conn, share_id, table_name, schema_name)
            if not table_row:
                return None

            current_ts = now_ts()
            update_values = {"updated_at": current_ts}

            if location is not None:
                update_values["location"] = location
            if metastore_db is not None:
                update_values["metastore_db"] = metastore_db
            if metastore_table is not None:
                update_values["metastore_table"] = metastore_table
            if auxiliary_locations is not None:
                update_values["auxiliary_locations"] = json.dumps(auxiliary_locations)
            if new_schema_name is not None:
                update_values["schema_name"] = new_schema_name.lower()

            try:
                conn.execute(
                    st.update()
                    .values(**update_values)
                    .where(st.c.table_id == table_row.table_id)
                )
            except IntegrityError as e:
                raise DeltaSharingError(
                    ErrorCode.INTERNAL_ERROR,
                    f"Failed to update table '{table_name}' in share '{share_name}'",
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

        return self.get_table(share_name, schema_name, table_name)

    @staticmethod
    def _find_table_row(
        conn: Connection, share_id: str, table_name: str, schema_name: str
    ):
        """查找 shared_tables 记录（支持 schema_name 过滤）。

        Args:
            conn: SQLAlchemy Connection 对象。
            share_id: Share UUID。
            table_name: Table 名称。
            schema_name: Schema 名称（可选）。

        Returns:
            匹配的 Row 对象，未找到返回 None。
        """
        st = shared_tables
        ss = shared_schemas

        if schema_name:
            j = st.outerjoin(ss, st.c.linked_schema_id == ss.c.schema_id)
            result = conn.execute(
                st.select()
                .with_only_columns(st.c.table_id)
                .select_from(j)
                .where(
                    st.c.share_id == share_id,
                    st.c.table_name == table_name.lower(),
                    or_(
                        ss.c.schema_name == schema_name.lower(),
                        and_(
                            st.c.linked_schema_id == None,  # noqa: E711
                            st.c.schema_name == schema_name.lower(),
                        ),
                    ),
                )
            )
        else:
            result = conn.execute(
                st.select()
                .with_only_columns(st.c.table_id)
                .where(
                    st.c.share_id == share_id,
                    st.c.table_name == table_name.lower(),
                )
            )

        return result.fetchone()

    def get_table(
        self, share_name: str, schema_name: str, table_name: str
    ) -> Optional[Dict[str, Any]]:
        """获取 Table 实体。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            table_name: Table 名称。

        Returns:
            Table 字典，如果不存在则返回 None。
        """
        sh = self._sh
        ss = self._ss
        st = self._st

        with self._db.get_engine().connect() as conn:
            share_id = self._get_share_id(conn, share_name)
            if not share_id:
                return None

            # CASE WHEN ... ELSE COALESCE(...) 处理 schema_name
            schema_name_expr = case(
                (st.c.linked_schema_id == None, st.c.schema_name),  # noqa: E711
                else_=func.coalesce(ss.c.schema_name, ""),
            ).label("schema_name")

            j1 = st.join(sh, st.c.share_id == sh.c.share_id)
            j2 = j1.join(ss, st.c.linked_schema_id == ss.c.schema_id, isouter=True)

            result = conn.execute(
                st.select()
                .with_only_columns(
                    st.c.table_id,
                    st.c.share_id,
                    sh.c.share_name,
                    st.c.linked_schema_id,
                    schema_name_expr,
                    st.c.table_name,
                    st.c.location,
                    st.c.metastore_db,
                    st.c.metastore_table,
                    st.c.auxiliary_locations,
                    st.c.created_at,
                    st.c.updated_at,
                )
                .select_from(j2)
                .where(
                    st.c.share_id == share_id,
                    st.c.table_name == table_name.lower(),
                    or_(
                        ss.c.schema_name == schema_name.lower(),
                        and_(
                            st.c.linked_schema_id == None,  # noqa: E711
                            st.c.schema_name == schema_name.lower(),
                        ),
                    ),
                )
            )

            row = result.fetchone()
            if not row:
                return None
            return self._row_to_table_dict(row)

    def delete_table(
        self, share_name: str, schema_name: str = "", table_name: str = ""
    ) -> bool:
        """删除 Table 实体。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称（可选，为空时匹配所有 schema）。
            table_name: Table 名称。

        Returns:
            如果成功删除返回 True，否则返回 False。
        """
        st = self._st

        with self._db.get_engine().begin() as conn:
            share_id = self._get_share_id(conn, share_name)
            if not share_id:
                return False

            table_row = self._find_table_row(conn, share_id, table_name, schema_name)
            if not table_row:
                return False

            try:
                conn.execute(st.delete().where(st.c.table_id == table_row.table_id))
            except IntegrityError as e:
                raise DeltaSharingError(
                    ErrorCode.INTERNAL_ERROR,
                    f"Failed to delete table '{table_name}' from share '{share_name}'",
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
            return True

    # ------------------------------------------------------------------
    # 列表查询操作
    # ------------------------------------------------------------------

    def list_share_objects(self, share_name: str) -> Dict[str, List[Dict[str, Any]]]:
        """列出 Share 下的所有 Schema 和 Table。

        Args:
            share_name: Share 名称。

        Returns:
            包含 'schemas' 和 'tables' 列表的字典。
        """
        sh = self._sh
        ss = self._ss
        st = self._st

        with self._db.get_engine().connect() as conn:
            share_id = self._get_share_id(conn, share_name)
            if not share_id:
                return {"schemas": [], "tables": []}

            # 查询 schemas
            j_schema = ss.join(sh, ss.c.share_id == sh.c.share_id)
            result_schemas = conn.execute(
                ss.select()
                .with_only_columns(
                    ss.c.schema_id,
                    sh.c.share_name,
                    ss.c.schema_name,
                    ss.c.metastore_db,
                )
                .select_from(j_schema)
                .where(ss.c.share_id == share_id)
                .order_by(ss.c.schema_name)
            )
            schemas = [
                {
                    "schema_id": row.schema_id,
                    "share_name": row.share_name,
                    "schema_name": row.schema_name,
                    "metastore_db": row.metastore_db,
                }
                for row in result_schemas.fetchall()
            ]

            # 查询 tables
            schema_name_expr = case(
                (st.c.linked_schema_id == None, st.c.schema_name),  # noqa: E711
                else_=func.coalesce(ss.c.schema_name, ""),
            ).label("schema_name")

            j_table1 = st.join(sh, st.c.share_id == sh.c.share_id)
            j_table2 = j_table1.join(
                ss, st.c.linked_schema_id == ss.c.schema_id, isouter=True
            )

            result_tables = conn.execute(
                st.select()
                .with_only_columns(
                    st.c.table_id,
                    st.c.share_id,
                    sh.c.share_name,
                    st.c.linked_schema_id,
                    schema_name_expr,
                    st.c.table_name,
                    st.c.location,
                    st.c.metastore_db,
                    st.c.metastore_table,
                    st.c.auxiliary_locations,
                )
                .select_from(j_table2)
                .where(st.c.share_id == share_id)
                .order_by("schema_name", st.c.table_name)
            )
            tables = [self._row_to_table_dict(row) for row in result_tables.fetchall()]

            return {"schemas": schemas, "tables": tables}

    def get_direct_bound_tables(self, share_name: str) -> List[Dict[str, Any]]:
        """获取直接绑定到 Share 的 Table 列表（linked_schema_id 为 NULL）。

        Args:
            share_name: Share 名称。

        Returns:
            直接绑定到 Share 的 Table 字典列表。
        """
        sh = self._sh
        st = self._st

        with self._db.get_engine().connect() as conn:
            share_id = self._get_share_id(conn, share_name)
            if not share_id:
                return []

            j = st.join(sh, st.c.share_id == sh.c.share_id)
            result = conn.execute(
                st.select()
                .with_only_columns(
                    st.c.table_id,
                    st.c.share_id,
                    sh.c.share_name,
                    st.c.linked_schema_id,
                    st.c.schema_name,
                    st.c.table_name,
                    st.c.location,
                    st.c.metastore_db,
                    st.c.metastore_table,
                    st.c.auxiliary_locations,
                    st.c.created_at,
                    st.c.updated_at,
                )
                .select_from(j)
                .where(
                    st.c.share_id == share_id,
                    st.c.linked_schema_id == None,  # noqa: E711
                )
                .order_by(st.c.table_name)
            )

            return [self._row_to_table_dict(row) for row in result.fetchall()]

    def get_share_schemas_from_db(self, share_name: str) -> Dict[str, Dict[str, Any]]:
        """从数据库获取指定 Share 下的所有 Schema 配置。

        Args:
            share_name: Share 名称。

        Returns:
            包含所有 Schema 配置的字典，键为 Schema 名（转小写）。
        """
        ss = self._ss

        with self._db.get_engine().connect() as conn:
            share_id = self._get_share_id(conn, share_name)
            if not share_id:
                return {}

            result = conn.execute(
                ss.select()
                .with_only_columns(ss.c.schema_name, ss.c.metastore_db)
                .where(ss.c.share_id == share_id)
                .order_by(ss.c.schema_name)
            )

            return {
                row.schema_name.lower(): {
                    "schema_name": row.schema_name,
                    "metastore_db": row.metastore_db,
                    "tables": {},
                }
                for row in result.fetchall()
            }

    def get_schema_tables_from_db(
        self, share_name: str, schema_name: str
    ) -> Dict[str, Dict[str, Any]]:
        """从数据库获取指定 Schema 下的所有 Table 配置。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。

        Returns:
            包含所有 Table 配置的字典，键为表名（转小写）。
        """
        st = self._st

        with self._db.get_engine().connect() as conn:
            share_id = self._get_share_id(conn, share_name)
            if not share_id:
                return {}

            schema_id = self._get_schema_id(conn, share_id, schema_name)
            if not schema_id:
                return {}

            result = conn.execute(
                st.select()
                .with_only_columns(
                    st.c.table_id,
                    st.c.table_name,
                    st.c.location,
                    st.c.metastore_db,
                    st.c.metastore_table,
                    st.c.auxiliary_locations,
                )
                .where(st.c.linked_schema_id == schema_id)
                .order_by(st.c.table_name)
            )

            output = {}
            for row in result.fetchall():
                auxiliary_locations = (
                    json.loads(row.auxiliary_locations)
                    if row.auxiliary_locations
                    else None
                )
                output[row.table_name.lower()] = {
                    "table_id": row.table_id,
                    "table_name": row.table_name,
                    "location": row.location,
                    "metastore_db": row.metastore_db,
                    "metastore_table": row.metastore_table,
                    "auxiliary_locations": auxiliary_locations,
                }
            return output

    def get_all_tables_for_share(self, share_name: str) -> Dict[str, Dict[str, Any]]:
        """获取指定 Share 下的所有 Table（包含直绑表和关联表）。

        与 get_schema_tables_from_db() 不同，本方法一次性返回该 Share 下的
        全部 Table，既包括通过 linked_schema_id 关联到 shared_schemas 实体的表，
        也包括 linked_schema_id 为 NULL 的直绑表。

        直绑表的 schema_name 取自 shared_tables.schema_name 字段，
        关联表的 schema_name 取自 shared_schemas.schema_name 字段。

        返回结构为嵌套字典：{schema_name: {table_name: {字段...}}}。

        Args:
            share_name: Share 名称。

        Returns:
            嵌套字典，外层键为 schema_name（小写），内层键为 table_name（小写），
            值为包含 table_id、table_name、location、metastore_db、
            metastore_table、auxiliary_locations、schema_name 的字典。
        """
        sh = self._sh
        ss = self._ss
        st = self._st

        with self._db.get_engine().connect() as conn:
            share_id = self._get_share_id(conn, share_name)
            if not share_id:
                return {}

            schema_name_expr = case(
                (st.c.linked_schema_id == None, st.c.schema_name),  # noqa: E711
                else_=func.coalesce(ss.c.schema_name, ""),
            ).label("schema_name")

            j1 = st.join(sh, st.c.share_id == sh.c.share_id)
            j2 = j1.join(ss, st.c.linked_schema_id == ss.c.schema_id, isouter=True)

            result = conn.execute(
                st.select()
                .with_only_columns(
                    st.c.table_id,
                    st.c.table_name,
                    st.c.location,
                    st.c.metastore_db,
                    st.c.metastore_table,
                    st.c.auxiliary_locations,
                    schema_name_expr,
                )
                .select_from(j2)
                .where(st.c.share_id == share_id)
                .order_by("schema_name", st.c.table_name)
            )

            output: Dict[str, Dict[str, Any]] = {}
            for row in result.fetchall():
                s_name = (row.schema_name or "").lower()
                t_name = (row.table_name or "").lower()
                if not s_name or not t_name:
                    continue
                auxiliary_locations = (
                    json.loads(row.auxiliary_locations)
                    if row.auxiliary_locations
                    else None
                )
                if s_name not in output:
                    output[s_name] = {}
                output[s_name][t_name] = {
                    "table_id": row.table_id,
                    "table_name": row.table_name,
                    "location": row.location,
                    "metastore_db": row.metastore_db,
                    "metastore_table": row.metastore_table,
                    "auxiliary_locations": auxiliary_locations,
                    "schema_name": row.schema_name,
                }
            return output

    # ------------------------------------------------------------------
    # 批量操作
    # ------------------------------------------------------------------

    def create_tables_batch(
        self,
        share_name: str,
        schema_name: str,
        tables: List[Dict[str, Any]],
    ) -> Dict[str, int]:
        """批量创建 Table 实体。

        使用检查机制避免重复插入已有 Table。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            tables: Table 信息列表，每个字典包含:
                - name: 表名称
                - location: 表的存储位置路径（可选）
                - metastore_db: Metastore 数据库名称（可选）
                - metastore_table: Metastore 表名称（可选）
                - auxiliary_locations: 辅助存储位置列表（可选）

        Returns:
            包含 inserted_count（插入数量）和 skipped_count（跳过数量）的字典。
        """
        st = self._st

        with self._db.get_engine().begin() as conn:
            share_id = self._get_share_id(conn, share_name)
            if not share_id:
                raise DeltaSharingError(
                    ErrorCode.SHARE_NOT_FOUND,
                    f"Share '{share_name}' not found",
                    status_code=404,
                )

            schema_id = self._get_schema_id(conn, share_id, schema_name)
            if not schema_id:
                raise DeltaSharingError(
                    ErrorCode.SCHEMA_NOT_FOUND,
                    f"Schema '{schema_name}' not found in share '{share_name}'",
                    status_code=404,
                )

            current_ts = now_ts()
            inserted_count = 0
            skipped_count = 0

            for table_info in tables:
                t_name = table_info.get("name", "").lower()
                if not t_name:
                    continue

                # 检查是否已存在
                result = conn.execute(
                    st.select()
                    .with_only_columns(st.c.table_id)
                    .where(
                        st.c.share_id == share_id,
                        st.c.linked_schema_id == schema_id,
                        st.c.table_name == t_name,
                    )
                )
                if result.fetchone():
                    skipped_count += 1
                    continue

                table_id = str(uuid.uuid4())
                try:
                    conn.execute(
                        st.insert().values(
                            table_id=table_id,
                            share_id=share_id,
                            linked_schema_id=schema_id,
                            table_name=t_name,
                            location=table_info.get("location"),
                            metastore_db=table_info.get("metastore_db"),
                            metastore_table=table_info.get("metastore_table"),
                            schema_name="",  # 关联 Schema 的 Table，schema_name 为空字符串
                            auxiliary_locations=(
                                json.dumps(table_info.get("auxiliary_locations"))
                                if table_info.get("auxiliary_locations")
                                else None
                            ),
                            created_at=current_ts,
                            updated_at=current_ts,
                        )
                    )
                except IntegrityError:
                    skipped_count += 1
                    continue
                except OperationalError as e:
                    raise DeltaSharingError(
                        ErrorCode.INTERNAL_ERROR,
                        "Database operation failed during batch insert",
                        status_code=500,
                        details={"db_error": str(e)},
                    )
                inserted_count += 1

        return {"inserted_count": inserted_count, "skipped_count": skipped_count}

    def delete_schema_tables(self, share_name: str, schema_name: str) -> int:
        """删除指定 Schema 下的所有 Table。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。

        Returns:
            删除的 Table 数量。
        """
        st = self._st

        with self._db.get_engine().begin() as conn:
            share_id = self._get_share_id(conn, share_name)
            if not share_id:
                raise DeltaSharingError(
                    ErrorCode.SHARE_NOT_FOUND,
                    f"Share '{share_name}' not found",
                    status_code=404,
                )

            schema_id = self._get_schema_id(conn, share_id, schema_name)
            if not schema_id:
                raise DeltaSharingError(
                    ErrorCode.SCHEMA_NOT_FOUND,
                    f"Schema '{schema_name}' not found in share '{share_name}'",
                    status_code=404,
                )

            try:
                result = conn.execute(
                    st.delete().where(st.c.linked_schema_id == schema_id)
                )
            except IntegrityError as e:
                raise DeltaSharingError(
                    ErrorCode.INTERNAL_ERROR,
                    f"Failed to delete tables from schema '{schema_name}' in share '{share_name}'",
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
            return result.rowcount

    def delete_stale_schema_tables(
        self,
        share_name: str,
        schema_name: str,
        dlc_table_names: List[str],
    ) -> int:
        """删除 DLC 中已不存在的过期 Table 记录。

        对比 DLC 当前表列表与本地 shared_tables 记录，
        删除本地存在但 DLC 中已删除的过期表。

        Args:
            share_name: Share 名称。
            schema_name: Schema 名称。
            dlc_table_names: DLC 中当前存在的表名列表。

        Returns:
            删除的过期 Table 数量。
        """
        st = self._st

        with self._db.get_engine().begin() as conn:
            share_id = self._get_share_id(conn, share_name)
            if not share_id:
                raise DeltaSharingError(
                    ErrorCode.SHARE_NOT_FOUND,
                    f"Share '{share_name}' not found",
                    status_code=404,
                )

            schema_id = self._get_schema_id(conn, share_id, schema_name)
            if not schema_id:
                raise DeltaSharingError(
                    ErrorCode.SCHEMA_NOT_FOUND,
                    f"Schema '{schema_name}' not found in share '{share_name}'",
                    status_code=404,
                )

            # 将 DLC 表名统一转为小写用于比较
            dlc_names_lower = {name.lower() for name in dlc_table_names if name}

            # 查询当前 Schema 下所有已有的 shared_tables 记录
            result = conn.execute(
                st.select()
                .with_only_columns(st.c.table_id, st.c.table_name)
                .where(st.c.linked_schema_id == schema_id)
            )
            existing_tables = result.fetchall()

            stale_ids = [
                row.table_id
                for row in existing_tables
                if row.table_name.lower() not in dlc_names_lower
            ]

            if stale_ids:
                try:
                    delete_result = conn.execute(
                        st.delete().where(st.c.table_id.in_(stale_ids))
                    )
                except IntegrityError as e:
                    raise DeltaSharingError(
                        ErrorCode.INTERNAL_ERROR,
                        f"Failed to delete stale tables from schema '{schema_name}'",
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
                return delete_result.rowcount
            return 0
