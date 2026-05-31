"""
数据库查询次数基准测试脚本

该模块提供独立的数据库查询基准测试，使用 SQLAlchemy
before_cursor_execute 事件监听器统计各 Repository/Service 层方法的
SQL 查询次数。不依赖 HTTP 网络 I/O，仅测量数据库访问。

使用方法:
    cd server
    uv run .\\tests\\benchmarks\\db_query_benchmark.py
    uv run .\\tests\\benchmarks\\db_query_benchmark.py --mode pre-optimize
    uv run .\\tests\\benchmarks\\db_query_benchmark.py --mode post-optimize
"""

import argparse
import json
import sys
from typing import Dict, List, Optional

from sqlalchemy import event

from app.core.config import load_config, get_all_shares
from app.core.database import init_database, get_database


class SqlCounter:
    """SQL 查询次数统计器。

    通过 SQLAlchemy event.listens_for 监听 before_cursor_execute 事件，
    在方法调用开始前重置计数器，方法执行完毕后读取计数。

    支持嵌套调用场景的层级计数：使用 _depth 跟踪嵌套调用层级，
    仅在顶层调用重置和读取计数。

    Attributes:
        count: 累积的 SQL 执行次数。
        statements: 捕获的 SQL 语句列表（用于调试和报告）。
        _depth: 嵌套调用深度计数器。
    """

    def __init__(self):
        """初始化 SQL 查询次数统计器。"""
        self.count = 0
        self.statements: List[str] = []
        self._depth = 0
        self._attached = False

    def _on_before_cursor_execute(self, conn, cursor, statement, parameters, context, executemany):
        """SQLAlchemy before_cursor_execute 事件回调。"""
        self.count += 1
        self.statements.append(str(statement).strip())

    def attach(self):
        """启动事件监听，每调用一次嵌套层级加 1。

        仅在顶层调用（_depth == 0）时重置计数器和注册监听器，
        避免嵌套调用时重复注册导致计数翻倍。
        """
        if self._depth == 0:
            self.count = 0
            self.statements = []
            if not self._attached:
                event.listen(
                    get_database().get_engine(),
                    "before_cursor_execute",
                    self._on_before_cursor_execute,
                )
                self._attached = True
        self._depth += 1

    def detach(self, label: str = "") -> Dict:
        """停止事件监听并返回本次调用期间的统计。

        Args:
            label: 本次统计的标签（用于报告标识）。

        Returns:
            包含 label、count、statements、depth 的字典。
        """
        self._depth -= 1
        if self._depth == 0:
            if self._attached:
                event.remove(
                    get_database().get_engine(),
                    "before_cursor_execute",
                    self._on_before_cursor_execute,
                )
                self._attached = False
        return {
            "label": label,
            "count": self.count,
            "statements": self.statements.copy(),
            "depth": self._depth,
        }


def run_benchmark(mode: str) -> Dict:
    """运行数据库查询基准测试。

    依次调用各 Repository/Service 层方法，统计每个方法的 SQL 查询次数，
    汇总生成 JSON 格式报告。

    Args:
        mode: 基准测试模式标识（pre-optimize 或 post-optimize）。

    Returns:
        包含 mode、steps、total_sql_count、summary 的字典。
    """
    from app.repositories.share_repository import ShareRepository
    from app.repositories.recipient_share_repository import RecipientShareRepository
    from app.services.share_service import ShareService
    from app.services.authorization_service import AuthorizationService

    counter = SqlCounter()
    steps: List[Dict] = []
    total_sql_count = 0

    share_repo = ShareRepository()
    auth_repo = RecipientShareRepository()
    share_service = ShareService()
    auth_service = AuthorizationService()

    # 获取测试用的 share 和 recipient 信息
    all_shares = get_all_shares()
    test_share: Optional[str] = None
    for share_name in all_shares:
        test_share = share_name
        break

    test_recipient_id = "test-recipient-id"

    # ------------------------------------------------------------------
    # Step 1: share_exists() 调用
    # ------------------------------------------------------------------
    if test_share:
        counter.attach()
        result = share_service.share_exists(test_share)
        stats = counter.detach("share_exists()")
        steps.append(
            {
                "method": "share_exists",
                "sql_count": stats["count"],
                "statements": stats["statements"],
                "result": result,
            }
        )
        total_sql_count += stats["count"]

    # ------------------------------------------------------------------
    # Step 2: AuthorizationService.check_share_access() 调用
    # ------------------------------------------------------------------
    if test_share:
        counter.attach()
        result = auth_service.check_share_access(test_recipient_id, test_share)
        stats = counter.detach("check_share_access()")
        steps.append(
            {
                "method": "check_share_access",
                "sql_count": stats["count"],
                "statements": stats["statements"],
                "result": result,
            }
        )
        total_sql_count += stats["count"]

    # ------------------------------------------------------------------
    # Step 3: RecipientShareRepository.check_access_with_share_validation() 调用
    #   该方法可能尚未实现（pre-optimize 模式下），使用 try/except 兜底
    # ------------------------------------------------------------------
    if test_share and hasattr(auth_repo, "check_access_with_share_validation"):
        counter.attach()
        result = auth_repo.check_access_with_share_validation(test_share, test_recipient_id)
        stats = counter.detach("check_access_with_share_validation()")
        steps.append(
            {
                "method": "check_access_with_share_validation",
                "sql_count": stats["count"],
                "statements": stats["statements"],
                "result": result,
            }
        )
        total_sql_count += stats["count"]
    else:
        steps.append(
            {
                "method": "check_access_with_share_validation",
                "sql_count": 0,
                "statements": [],
                "result": "NOT_IMPLEMENTED",
            }
        )

    # ------------------------------------------------------------------
    # Step 4: get_share_id() 调用（直接获取 share_id）
    # ------------------------------------------------------------------
    if test_share:
        counter.attach()
        result = share_repo.get_share_id(test_share)
        stats = counter.detach("get_share_id()")
        steps.append(
            {
                "method": "get_share_id",
                "sql_count": stats["count"],
                "statements": stats["statements"],
                "result": result,
            }
        )
        total_sql_count += stats["count"]

    # ------------------------------------------------------------------
    # Step 5: RecipientShareRepository.check_access() 调用（旧方法）
    # ------------------------------------------------------------------
    if test_share:
        share_id = share_repo.get_share_id(test_share)
        if share_id:
            counter.attach()
            result = auth_repo.check_access(test_recipient_id, share_id)
            stats = counter.detach("check_access()")
            steps.append(
                {
                    "method": "check_access",
                    "sql_count": stats["count"],
                    "statements": stats["statements"],
                    "result": result,
                }
            )
            total_sql_count += stats["count"]
        else:
            steps.append(
                {
                    "method": "check_access",
                    "sql_count": 0,
                    "statements": [],
                    "result": "SKIPPED (no share_id)",
                }
            )

    # ------------------------------------------------------------------
    # Step 6: 组合调用 share_exists + check_share_access（old pattern）
    # ------------------------------------------------------------------
    if test_share:
        counter.attach()
        exists = share_service.share_exists(test_share)
        access = auth_service.check_share_access(test_recipient_id, test_share)
        stats = counter.detach("share_exists() + check_share_access() 组合调用")
        steps.append(
            {
                "method": "share_exists + check_share_access (组合)",
                "sql_count": stats["count"],
                "statements": stats["statements"],
                "result": {"exists": exists, "access": access},
            }
        )
        total_sql_count += stats["count"]

    return {
        "mode": mode,
        "steps": steps,
        "total_sql_count": total_sql_count,
        "summary": f"模式 '{mode}'：共 {len(steps)} 个测试步骤，总计 {total_sql_count} 次 SQL 查询",
    }


def main():
    """程序入口函数。

    解析命令行参数，初始化数据库，执行基准测试，
    以 JSON 格式输出统计报告到 stdout。
    """
    parser = argparse.ArgumentParser(description="Database Query Count Benchmark")
    parser.add_argument(
        "--mode",
        default="pre-optimize",
        choices=["pre-optimize", "post-optimize"],
        help="Benchmark mode identification (default: pre-optimize)",
    )
    args = parser.parse_args()

    load_config("./config.yaml")

    config_ref = __import__("app.core.config", fromlist=["get_config"])
    db_url = config_ref.get_config().database.url

    init_database(db_url)

    print(
        f"[INFO] Running benchmark in mode: {args.mode}",
        file=sys.stderr,
    )

    report = run_benchmark(args.mode)

    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
