"""
pytest 共享测试基础设施

该模块为所有集成测试提供共享的 fixtures，包括：
- test_db: 临时 SQLite 数据库，测试后自动清理
- client_dp: 基于 create_data_plane_app() 的 TestClient，预配置认证 mock
- client_admin: 基于 create_admin_app() 的 TestClient
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from main import create_data_plane_app, create_admin_app
from app.core.database import init_database
from app.core.config import load_config


@pytest.fixture(scope="function")
def test_db():
    """创建临时 SQLite 测试数据库，测试完成后自动清理。

    每个测试函数获得独立的数据库文件，确保测试隔离。

    Yields:
        SQLAlchemy engine 实例。
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        test_db_path = f.name

    load_config("./config.yaml")
    db = init_database(f"sqlite:///{test_db_path}")

    yield db

    db.close()
    if os.path.exists(test_db_path):
        os.unlink(test_db_path)


@pytest.fixture(scope="function")
def client_dp(test_db):
    """创建 Data Plane TestClient，覆盖 get_current_recipient 依赖。

    通过 app.dependency_overrides 将 get_current_recipient 覆盖为
    返回固定 recipient_id，使数据面路由测试无需真实 token。

    Args:
        test_db: 共享的测试数据库 fixture。

    Returns:
        基于 create_data_plane_app() 的 TestClient 实例。
    """
    app = create_data_plane_app()

    async def _mock_get_current_recipient():
        return "test-recipient-id"

    from app.core.authentication import get_current_recipient

    app.dependency_overrides[get_current_recipient] = _mock_get_current_recipient

    return TestClient(app)


@pytest.fixture(scope="function")
def client_admin(test_db):
    """创建 Admin API TestClient。

    Args:
        test_db: 共享的测试数据库 fixture。

    Returns:
        基于 create_admin_app() 的 TestClient 实例。
    """
    app = create_admin_app()
    return TestClient(app)
