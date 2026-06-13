#!/usr/bin/env python3
"""
初始化管理员账户脚本

该脚本用于在 Delta Sharing Server 数据库中创建或更新管理员用户。
需要在 server 目录下运行，使用项目相同的配置和依赖。

用法:
    # 在 server 目录下运行
    cd server

    # 创建新管理员
    uv run python scripts/init_admin.py --username admin --password mypassword

    # 创建管理员并指定显示名称
    uv run python scripts/init_admin.py --username admin --password mypassword --display-name "System Admin"

    # 更新现有管理员的密码
    uv run python scripts/init_admin.py --username admin --password newpassword

注意：
    - 密码通过命令行参数传入，请注意 shell 历史记录安全
    - 生产环境建议通过环境变量传入密码
"""

import argparse
import sys
import os

# 将 server 目录加入 Python 路径，确保可以导入 app 模块
_script_dir = os.path.dirname(os.path.abspath(__file__))
_server_dir = os.path.dirname(_script_dir)
sys.path.insert(0, _server_dir)

from app.core.config import load_config
from app.core.database import init_database
from app.repositories.admin_user_repository import AdminUserRepository


def main():
    parser = argparse.ArgumentParser(
        description="初始化或更新 Delta Sharing Server 管理员账户",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  uv run python scripts/init_admin.py --username admin --password mypassword
  uv run python scripts/init_admin.py --username admin --password newpass --display-name "Admin User"
        """,
    )
    parser.add_argument(
        "--username",
        required=True,
        help="管理员用户名",
    )
    parser.add_argument(
        "--password",
        required=True,
        help="管理员密码",
    )
    parser.add_argument(
        "--display-name",
        default="",
        help="管理员显示名称（可选）",
    )
    parser.add_argument(
        "--config",
        default="./config.yaml",
        help="配置文件路径（默认: ./config.yaml）",
    )

    args = parser.parse_args()

    # 加载配置
    config_path = os.path.join(_server_dir, args.config) if not os.path.isabs(args.config) else args.config
    print(f"Loading config from: {config_path}")
    load_config(config_path)

    # 初始化数据库
    print("Initializing database...")
    init_database()
    print("Database initialized.")

    # 创建或更新管理员用户
    repo = AdminUserRepository()
    existing = repo.find_by_username(args.username)

    if existing:
        # 用户已存在，更新密码
        success = repo.update_password(args.username, args.password)
        if success:
            print(f"Password updated successfully for admin user: {args.username}")
        else:
            print(f"Error: Failed to update password for {args.username}", file=sys.stderr)
            sys.exit(1)
    else:
        # 创建新管理员
        try:
            admin = repo.create(
                username=args.username,
                plain_password=args.password,
                display_name=args.display_name,
            )
            print(f"Admin user created successfully: {admin['username']} (ID: {admin['admin_id']})")
        except Exception as e:
            print(f"Error creating admin user: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
