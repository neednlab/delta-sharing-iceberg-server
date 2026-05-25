"""
数据库种子数据初始化脚本

该脚本基于当前 server/data/server.db 数据库中现存的数据，
生成一份可复用的种子数据初始化脚本。可用于：
- 在新环境中快速搭建开发/测试数据库
- 重置数据库到已知的初始状态
- CI/CD 流程中的数据库初始化

使用方式:
    cd server && uv run python scripts/ini_data.py                # 使用默认数据库 URL
    cd server && uv run python scripts/ini_data.py --db-url sqlite:///./data/custom.db
    cd server && uv run python scripts/ini_data.py --reset        # 先清空数据库再初始化
    cd server && uv run python scripts/ini_data.py --dry-run      # 只打印数据不执行写入

安全特性:
    - 使用"先查后插"模式确保幂等性，重复执行不会出错
    - 默认不清空已有数据，如需重置请使用 --reset 参数
    - 支持 --dry-run 模式，仅预览不写入
"""

import argparse
from pathlib import Path

from loguru import logger
from sqlalchemy import create_engine

from app.core.database import (
    shares,
    recipients,
    shared_schemas,
    shared_tables,
    recipient_shares,
    snapshot_version,
    bearer_tokens,
    token_revocation,
)

# ============================================================================
# 种子数据 - 基于当前 server/data/server.db 数据库导出
# 生成时间: 2026-04-30
# ============================================================================

# share_id，用于关联各表
_SEED_SHARE_ID = "49229f1d-c85d-4030-8342-a24bb5ba1551"
_SEED_SHARE_NAME = "needn_share"

# schema_id，用于关联 shared_tables
_SEED_SCHEMA_ID = "981fbd0c-046e-49e3-aac2-c56a220b80d8"
_SEED_SCHEMA_NAME = "playground"

# recipient_id，用于关联 bearer_tokens / recipient_shares
_SEED_RECIPIENT_ID = "b22e9747-1322-4c70-bd01-a8d468423496"
_SEED_RECIPIENT_NAME = "needn"

# 时间戳常量（UTC UNIX 秒级时间戳）
_TS_SHARE = 1777469677
_TS_SCHEMA = 1777469693
_TS_TABLE = 1777469693
_TS_RECIPIENT = 1777469716
_TS_GRANT = 1777469716
_TS_SNAPSHOT = 1777469800


def _reset_all_tables(conn) -> None:
    """清空所有业务表数据，保留表结构。

    按外键依赖顺序（子表先删）执行 DELETE 操作。
    使用 SQLAlchemy Core API 替代原生 SQL。

    Args:
        conn: SQLAlchemy Connection 对象。
    """
    logger.warning("正在清空所有业务表数据...")
    table_list = [
        token_revocation,
        bearer_tokens,
        recipient_shares,
        shared_tables,
        shared_schemas,
        recipients,
        snapshot_version,
        shares,
    ]
    for table in table_list:
        result = conn.execute(table.delete())
        logger.info(f"  已清空表: {table.name}（{result.rowcount} 行）")


def _seed_shares(conn) -> None:
    """插入 shares 种子数据。

    使用"先查后插"确保幂等性，替代原生的 INSERT OR REPLACE。

    Args:
        conn: SQLAlchemy Connection 对象。
    """
    result = conn.execute(shares.select().where(shares.c.share_id == _SEED_SHARE_ID))
    if result.fetchone():
        logger.info(f"  [shares] 已存在，跳过: {_SEED_SHARE_NAME}")
        return

    conn.execute(
        shares.insert().values(
            share_id=_SEED_SHARE_ID,
            share_name=_SEED_SHARE_NAME,
            display_name=_SEED_SHARE_NAME,
            comment=_SEED_SHARE_NAME,
            properties=None,
            created_at=_TS_SHARE,
            updated_at=_TS_SHARE,
        )
    )
    logger.info(f"  [shares] 已插入: {_SEED_SHARE_NAME}")


def _seed_recipients(conn) -> None:
    """插入 recipients 种子数据。

    Args:
        conn: SQLAlchemy Connection 对象。
    """
    result = conn.execute(
        recipients.select().where(recipients.c.recipient_id == _SEED_RECIPIENT_ID)
    )
    if result.fetchone():
        logger.info(f"  [recipients] 已存在，跳过: {_SEED_RECIPIENT_NAME}")
        return

    conn.execute(
        recipients.insert().values(
            recipient_id=_SEED_RECIPIENT_ID,
            recipient_name=_SEED_RECIPIENT_NAME,
            comment=_SEED_RECIPIENT_NAME,
            created_at=_TS_RECIPIENT,
            updated_at=_TS_RECIPIENT,
            is_active=1,
        )
    )
    logger.info(f"  [recipients] 已插入: {_SEED_RECIPIENT_NAME}")


def _seed_recipient_shares(conn) -> None:
    """插入 recipient_shares 种子数据。

    授予 needn 用户对 needn_share 的访问权限。

    Args:
        conn: SQLAlchemy Connection 对象。
    """
    result = conn.execute(
        recipient_shares.select().where(
            recipient_shares.c.recipient_id == _SEED_RECIPIENT_ID,
            recipient_shares.c.share_id == _SEED_SHARE_ID,
        )
    )
    if result.fetchone():
        logger.info(
            f"  [recipient_shares] 已存在，跳过: {_SEED_RECIPIENT_NAME} -> {_SEED_SHARE_NAME}"
        )
        return

    conn.execute(
        recipient_shares.insert().values(
            id=1,
            recipient_id=_SEED_RECIPIENT_ID,
            share_id=_SEED_SHARE_ID,
            granted_at=_TS_GRANT,
            granted_by=None,
        )
    )
    logger.info(f"  [recipient_shares] 已插入: {_SEED_RECIPIENT_NAME} -> {_SEED_SHARE_NAME}")


def _seed_shared_schemas(conn) -> None:
    """插入 shared_schemas 种子数据。

    Args:
        conn: SQLAlchemy Connection 对象。
    """
    result = conn.execute(
        shared_schemas.select().where(shared_schemas.c.schema_id == _SEED_SCHEMA_ID)
    )
    if result.fetchone():
        logger.info(f"  [shared_schemas] 已存在，跳过: {_SEED_SCHEMA_NAME}")
        return

    conn.execute(
        shared_schemas.insert().values(
            schema_id=_SEED_SCHEMA_ID,
            share_id=_SEED_SHARE_ID,
            schema_name=_SEED_SCHEMA_NAME,
            metastore_db=_SEED_SCHEMA_NAME,
            created_at=_TS_SCHEMA,
            updated_at=_TS_SCHEMA,
        )
    )
    logger.info(f"  [shared_schemas] 已插入: {_SEED_SCHEMA_NAME}")


def _seed_shared_tables(conn) -> None:
    """插入 shared_tables 种子数据。

    共 8 张 Iceberg 表，分布于 COS playground 和 delta 路径下。

    Args:
        conn: SQLAlchemy Connection 对象。
    """
    tables_data = [
        {
            "table_id": "e5a5d28d-af00-4582-9bc5-4dac18a78331",
            "table_name": "ice_t1",
            "location": "cosn://bigdata-poc-1302805733/delta/ice_t1",
        },
        {
            "table_id": "2ab60d27-ecf4-4b94-a436-4ec3fda28577",
            "table_name": "ice_t2",
            "location": "cosn://bigdata-poc-1302805733/delta/ice_t2",
        },
        {
            "table_id": "9a8c3af4-747e-4a3c-878d-9d404056dec0",
            "table_name": "ice_t3",
            "location": "cosn://bigdata-poc-1302805733/delta/ice_t3",
        },
        {
            "table_id": "943e80a5-bae9-4382-af41-f9f09727180a",
            "table_name": "ice_t4",
            "location": "cosn://bigdata-poc-1302805733/delta/ice_t4",
        },
        {
            "table_id": "73ae8d20-1fc0-49c8-ace7-5c28c7fa83a8",
            "table_name": "n40",
            "location": "cosn://bigdata-poc-1302805733/playground/n40",
        },
        {
            "table_id": "4e1f1d5d-711e-48c5-afb9-660f820dfd52",
            "table_name": "t1_fact2_i",
            "location": "cosn://bigdata-poc-1302805733/playground/t1_fact2_i",
        },
        {
            "table_id": "2dcf658a-51a9-41e9-89d4-a6bcd4eb0361",
            "table_name": "t1_fact_tgt_i",
            "location": "cosn://bigdata-poc-1302805733/playground/t1_fact_tgt_i",
        },
        {
            "table_id": "bb7a78a1-ccbc-4723-bb71-834e356bf757",
            "table_name": "t4_part_i",
            "location": "cosn://bigdata-poc-1302805733/playground/t4_part_i",
        },
    ]

    inserted = 0
    skipped = 0
    for t in tables_data:
        result = conn.execute(
            shared_tables.select().where(shared_tables.c.table_id == t["table_id"])
        )
        if result.fetchone():
            skipped += 1
            continue

        conn.execute(
            shared_tables.insert().values(
                table_id=t["table_id"],
                share_id=_SEED_SHARE_ID,
                linked_schema_id=_SEED_SCHEMA_ID,
                table_name=t["table_name"],
                location=t["location"],
                metastore_db=_SEED_SCHEMA_NAME,
                metastore_table=t["table_name"],
                auxiliary_locations=None,
                created_at=_TS_TABLE,
                updated_at=_TS_TABLE,
            )
        )
        inserted += 1

    logger.info(f"  [shared_tables] 已插入 {inserted} 张表，跳过 {skipped} 张")


def _seed_snapshot_version(conn) -> None:
    """插入 snapshot_version 种子数据。

    为 ice_t4 表记录一个初始快照版本，用于测试版本查询功能。
    timestamp 使用毫秒级 Unix 时间戳，与 metadata.json 中快照的
    timestamp 字段格式保持一致。

    Args:
        conn: SQLAlchemy Connection 对象。
    """
    result = conn.execute(
        snapshot_version.select().where(
            snapshot_version.c.share_name == _SEED_SHARE_NAME,
            snapshot_version.c.schema_name == _SEED_SCHEMA_NAME,
            snapshot_version.c.table_name == "ice_t4",
        )
    )
    if result.fetchone():
        logger.info(
            f"  [snapshot_version] 已存在，跳过: {_SEED_SHARE_NAME}.{_SEED_SCHEMA_NAME}.ice_t4"
        )
        return

    conn.execute(
        snapshot_version.insert().values(
            id=1,
            share_name=_SEED_SHARE_NAME,
            schema_name=_SEED_SCHEMA_NAME,
            table_name="ice_t4",
            snapshot_id=2852334037410610126,
            version=1,
            timestamp=_TS_SNAPSHOT * 1000,
            created_at=_TS_SNAPSHOT,
        )
    )
    logger.info(f"  [snapshot_version] 已插入: {_SEED_SHARE_NAME}.{_SEED_SCHEMA_NAME}.ice_t4")


def initialize_seed_data(db_url: str, reset: bool = False, dry_run: bool = False) -> None:
    """将种子数据写入指定 SQLite 数据库。

    执行流程:
        1. 创建数据库引擎
        2. 创建全部表结构（IF NOT EXISTS 保证幂等）
        3. 如指定 --reset 则清空已有数据
        4. 按外键依赖顺序插入种子数据
        5. 提交事务并关闭引擎

    Args:
        db_url: SQLAlchemy 数据库连接 URL。
        reset: 是否在插入前清空已有数据。
        dry_run: 是否为预览模式，只打印不执行写入。
    """
    if dry_run:
        logger.info(f"=== 预览模式: 数据库 URL = {db_url} ===")
        _print_seed_data_summary()
        return

    # 确保数据目录存在（SQLite 文件模式）
    if db_url.startswith("sqlite:///./"):
        db_path = db_url.replace("sqlite:///./", "./")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"正在初始化数据库: {db_url}")
    logger.info(f"  重置模式: {'是' if reset else '否'}")

    # 创建 Engine，SQLite 需要 check_same_thread=False
    connect_args = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_engine(db_url, connect_args=connect_args)
    # 先确保表结构存在
    from sqlalchemy import MetaData

    metadata_obj = MetaData()
    metadata_obj.reflect(bind=engine)

    try:
        with engine.begin() as conn:
            # 先尝试创建表结构（如果元数据已加载）
            from app.core.database import _metadata

            _metadata.create_all(conn, checkfirst=True)

            # 如需要则清空数据
            if reset:
                _reset_all_tables(conn)

            # 按外键依赖顺序插入种子数据
            # 先插入父表: shares, recipients
            # 再插入子表: shared_schemas, shared_tables, recipient_shares
            # bearer_tokens 不预设种子数据，由管理员通过 UI 自行创建
            # snapshot_version 不依赖其他表，可任意位置插入
            logger.info("正在插入种子数据...")
            _seed_shares(conn)
            _seed_recipients(conn)
            _seed_shared_schemas(conn)
            _seed_shared_tables(conn)
            _seed_recipient_shares(conn)
            _seed_snapshot_version(conn)

        logger.info("种子数据初始化完成！")

        # 输出统计信息
        with engine.connect() as conn:
            _print_statistics(conn)

    except Exception:
        logger.exception("种子数据初始化失败，已回滚事务")
        raise
    finally:
        engine.dispose()


def _print_seed_data_summary() -> None:
    """打印种子数据摘要（dry-run 模式使用）。"""
    logger.info("")
    logger.info("种子数据摘要:")
    logger.info(f"  shares:          1 条 ({_SEED_SHARE_NAME})")
    logger.info(f"  recipients:      1 条 ({_SEED_RECIPIENT_NAME})")
    logger.info(f"  shared_schemas:  1 条 ({_SEED_SCHEMA_NAME})")
    logger.info("  shared_tables:   8 条 (ice_t1~4, n40, t1_fact2_i, t1_fact_tgt_i, t4_part_i)")
    logger.info("  recipient_shares:1 条")
    logger.info("  bearer_tokens:   0 条 (请通过 UI 自行创建)")
    logger.info("  snapshot_version:1 条 (ice_t4 的快照版本)")
    logger.info("")


def _print_statistics(conn) -> None:
    """打印各表行数统计。

    Args:
        conn: SQLAlchemy Connection 对象。
    """
    from sqlalchemy import func

    logger.info("")
    logger.info("各表数据行数统计:")
    table_list = [
        shares,
        recipients,
        shared_schemas,
        shared_tables,
        recipient_shares,
        bearer_tokens,
        token_revocation,
        snapshot_version,
    ]
    for table in table_list:
        result = conn.execute(table.select().with_only_columns(func.count().label("count")))
        row = result.fetchone()
        count = row.count if row else 0
        logger.info(f"  {table.name:<20} {count} 行")


def parse_args() -> argparse.Namespace:
    """解析命令行参数。

    Returns:
        解析后的参数对象。
    """
    parser = argparse.ArgumentParser(
        description="Delta Sharing Server 数据库种子数据初始化脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  uv run python scripts/ini_data.py                           # 默认数据库URL初始化
  uv run python scripts/ini_data.py --db-url sqlite:///./data/custom.db
  uv run python scripts/ini_data.py --reset                   # 先清空再初始化
  uv run python scripts/ini_data.py --dry-run                 # 仅预览数据
        """,
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default="sqlite:///./data/server.db",
        help="SQLAlchemy 数据库连接 URL（默认: sqlite:///./data/server.db）",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="在插入种子数据前清空所有业务表已有数据",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览模式，只打印种子数据摘要，不执行写入",
    )
    return parser.parse_args()


def main():
    """脚本主入口。"""
    args = parse_args()
    initialize_seed_data(
        db_url=args.db_url,
        reset=args.reset,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
