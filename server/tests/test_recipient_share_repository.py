"""
RecipientShareRepository 单元测试

覆盖范围：
- grant(): 创建授权记录（核心：验证 UUID 主键写入 Integer 列的 datatype mismatch 修复）
- grant(): 重复授权检测
- revoke(): 删除授权记录
- exists(): 存在性检查
- check_access(): 访问权限检查
- list_by_recipient(): JOIN 查询授权列表
- list_share_names(): 仅返回 share 名称列表

使用真实 SQLite 数据库（test_db fixture）验证 schema 兼容性，
确保 recipient_shares 表的 id 列 (String) 能正确接受 UUID 值。
"""

import uuid
import re

import pytest

from app.core.errors import DeltaSharingError, ErrorCode
from app.repositories.recipient_repository import RecipientRepository
from app.repositories.recipient_share_repository import RecipientShareRepository
from app.repositories.share_repository import ShareRepository


@pytest.fixture(scope="function")
def repo(test_db):
    """创建 RecipientShareRepository 实例。"""
    return RecipientShareRepository()


@pytest.fixture(scope="function")
def recipient_repo(test_db):
    """创建 RecipientRepository 实例。"""
    return RecipientRepository()


@pytest.fixture(scope="function")
def share_repo(test_db):
    """创建 ShareRepository 实例。"""
    return ShareRepository()


@pytest.fixture(scope="function")
def recipient(recipient_repo):
    """创建一个测试用 Recipient，返回其字典。"""
    return recipient_repo.create("test_recipient")


@pytest.fixture(scope="function")
def share(share_repo):
    """创建一个测试用 Share，返回其字典。"""
    return share_repo.create_share("test_share")


@pytest.fixture(scope="function")
def granted(repo, recipient, share):
    """创建一个已授权的 grant 记录，返回授权字典。"""
    return repo.grant(
        recipient_id=recipient["recipient_id"],
        share_id=share["share_id"],
        granted_by="admin",
    )


class TestGrant:
    """验证 RecipientShareRepository.grant() 方法。

    Bug 背景：表定义中 id 列曾是 Integer + autoincrement，但 grant() 方法
    写入 UUID 字符串 (str(uuid.uuid4()))，导致 sqlite3.IntegrityError: datatype mismatch。
    修复后 id 列改为 String，UUID 字符串写入应正常。
    """

    def test_grant_returns_correct_structure(self, repo, recipient, share):
        """验证 grant() 返回值包含正确的字段结构。"""
        result = repo.grant(
            recipient_id=recipient["recipient_id"],
            share_id=share["share_id"],
            granted_by="admin",
        )

        assert "id" in result
        assert "recipient_id" in result
        assert "share_id" in result
        assert "granted_at" in result
        assert "granted_by" in result

    def test_grant_id_is_uuid_string(self, repo, recipient, share):
        """验证 id 字段是有效的 UUID 字符串（非整数）。

        这是 Bug 2 的核心验证点：如果 id 列定义与写入值类型不匹配，
        此测试将在 SQL insert 时抛出 IntegrityError。
        """
        result = repo.grant(
            recipient_id=recipient["recipient_id"],
            share_id=share["share_id"],
        )

        assert isinstance(result["id"], str)
        uuid.UUID(result["id"])

    def test_grant_id_is_valid_uuid_format(self, repo, recipient, share):
        """验证 id 字段符合标准 UUID v4 格式。"""
        result = repo.grant(
            recipient_id=recipient["recipient_id"],
            share_id=share["share_id"],
        )

        uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
        assert re.match(uuid_pattern, result["id"], re.IGNORECASE) is not None

    def test_grant_returns_correct_recipient_id(self, repo, recipient, share):
        """验证返回的 recipient_id 与输入一致。"""
        result = repo.grant(
            recipient_id=recipient["recipient_id"],
            share_id=share["share_id"],
        )

        assert result["recipient_id"] == recipient["recipient_id"]

    def test_grant_returns_correct_share_id(self, repo, recipient, share):
        """验证返回的 share_id 与输入一致。"""
        result = repo.grant(
            recipient_id=recipient["recipient_id"],
            share_id=share["share_id"],
        )

        assert result["share_id"] == share["share_id"]

    def test_grant_returns_correct_granted_by(self, repo, recipient, share):
        """验证 granted_by 字段正确存储。"""
        result = repo.grant(
            recipient_id=recipient["recipient_id"],
            share_id=share["share_id"],
            granted_by="superadmin",
        )

        assert result["granted_by"] == "superadmin"

    def test_grant_granted_by_defaults_to_none(self, repo, recipient, share):
        """验证不传 granted_by 时默认为 None。"""
        result = repo.grant(
            recipient_id=recipient["recipient_id"],
            share_id=share["share_id"],
        )

        assert result["granted_by"] is None

    def test_grant_granted_at_is_integer_timestamp(self, repo, recipient, share):
        """验证 granted_at 是整数型 UNIX 时间戳。"""
        result = repo.grant(
            recipient_id=recipient["recipient_id"],
            share_id=share["share_id"],
        )

        assert isinstance(result["granted_at"], int)
        assert result["granted_at"] > 0

    def test_duplicate_grant_raises_authorization_exists(self, repo, recipient, share):
        """验证重复授权抛出 AUTHORIZATION_ALREADY_EXISTS 错误。"""
        repo.grant(
            recipient_id=recipient["recipient_id"],
            share_id=share["share_id"],
        )

        with pytest.raises(DeltaSharingError) as exc_info:
            repo.grant(
                recipient_id=recipient["recipient_id"],
                share_id=share["share_id"],
            )

        assert exc_info.value.error_code == ErrorCode.AUTHORIZATION_ALREADY_EXISTS
        assert exc_info.value.status_code == 409

    def test_grant_different_recipient_same_share_succeeds(
        self, repo, recipient, share, recipient_repo
    ):
        """验证不同 recipient 对同一 share 的授权独立，互不影响。"""
        recipient2 = recipient_repo.create("test_recipient_2")

        result1 = repo.grant(
            recipient_id=recipient["recipient_id"],
            share_id=share["share_id"],
        )
        result2 = repo.grant(
            recipient_id=recipient2["recipient_id"],
            share_id=share["share_id"],
        )

        assert result1["recipient_id"] != result2["recipient_id"]
        assert result1["share_id"] == result2["share_id"]

    def test_grant_same_recipient_different_share_succeeds(
        self, repo, recipient, share, share_repo
    ):
        """验证同一 recipient 对不同 share 的授权独立，互不影响。"""
        share2 = share_repo.create_share("test_share_2")

        result1 = repo.grant(
            recipient_id=recipient["recipient_id"],
            share_id=share["share_id"],
        )
        result2 = repo.grant(
            recipient_id=recipient["recipient_id"],
            share_id=share2["share_id"],
        )

        assert result1["recipient_id"] == result2["recipient_id"]
        assert result1["share_id"] != result2["share_id"]


class TestRevoke:
    """验证 RecipientShareRepository.revoke() 方法。"""

    def test_revoke_existing_returns_true(self, repo, granted, recipient, share):
        """验证撤销已存在的授权记录返回 True。"""
        result = repo.revoke(
            recipient_id=recipient["recipient_id"],
            share_id=share["share_id"],
        )
        assert result is True

    def test_revoke_nonexistent_returns_false(self, repo, recipient, share):
        """验证撤销不存在的授权记录返回 False。"""
        result = repo.revoke(
            recipient_id=recipient["recipient_id"],
            share_id=share["share_id"],
        )
        assert result is False

    def test_revoke_idempotent(self, repo, granted, recipient, share):
        """验证重复撤销：首次返回 True，再次返回 False。"""
        first = repo.revoke(
            recipient_id=recipient["recipient_id"],
            share_id=share["share_id"],
        )
        second = repo.revoke(
            recipient_id=recipient["recipient_id"],
            share_id=share["share_id"],
        )
        assert first is True
        assert second is False

    def test_exists_after_revoke_returns_false(self, repo, granted, recipient, share):
        """验证撤销后 exists() 返回 False。"""
        repo.revoke(
            recipient_id=recipient["recipient_id"],
            share_id=share["share_id"],
        )
        assert repo.exists(recipient["recipient_id"], share["share_id"]) is False


class TestExists:
    """验证 RecipientShareRepository.exists() 方法。"""

    def test_exists_after_grant_returns_true(self, repo, granted, recipient, share):
        """验证授权后 exists() 返回 True。"""
        assert repo.exists(recipient["recipient_id"], share["share_id"]) is True

    def test_exists_without_grant_returns_false(self, repo, recipient, share):
        """验证未授权时 exists() 返回 False。"""
        assert repo.exists(recipient["recipient_id"], share["share_id"]) is False

    def test_exists_with_nonexistent_recipient(self, repo, share):
        """验证不存在的 recipient_id 返回 False。"""
        assert repo.exists("nonexistent-id", share["share_id"]) is False

    def test_exists_with_nonexistent_share(self, repo, recipient):
        """验证不存在的 share_id 返回 False。"""
        assert repo.exists(recipient["recipient_id"], "nonexistent-id") is False


class TestCheckAccess:
    """验证 RecipientShareRepository.check_access() 方法。"""

    def test_check_access_after_grant_returns_true(self, repo, granted, recipient, share):
        """验证授权后 check_access() 返回 True。"""
        assert repo.check_access(recipient["recipient_id"], share["share_id"]) is True

    def test_check_access_without_grant_returns_false(self, repo, recipient, share):
        """验证未授权时 check_access() 返回 False。"""
        assert repo.check_access(recipient["recipient_id"], share["share_id"]) is False


class TestListByRecipient:
    """验证 RecipientShareRepository.list_by_recipient() 方法。"""

    def test_list_by_recipient_returns_list(self, repo, granted, recipient, share):
        """验证返回值为列表类型。"""
        results = repo.list_by_recipient(recipient["recipient_id"])
        assert isinstance(results, list)

    def test_list_by_recipient_contains_granted_record(self, repo, granted, recipient, share):
        """验证返回列表包含已授权的记录。"""
        results = repo.list_by_recipient(recipient["recipient_id"])
        assert len(results) == 1
        assert results[0]["recipient_id"] == recipient["recipient_id"]
        assert results[0]["share_id"] == share["share_id"]
        assert results[0]["share_name"] == share["share_name"]
        assert results[0]["granted_by"] == "admin"

    def test_list_by_recipient_includes_id_field(self, repo, granted, recipient):
        """验证返回记录包含 id 字段（UUID 字符串）。"""
        results = repo.list_by_recipient(recipient["recipient_id"])
        assert isinstance(results[0]["id"], str)
        uuid.UUID(results[0]["id"])

    def test_list_by_recipient_includes_granted_at(self, repo, granted, recipient):
        """验证返回记录包含 granted_at 字段。"""
        results = repo.list_by_recipient(recipient["recipient_id"])
        assert isinstance(results[0]["granted_at"], int)

    def test_list_by_recipient_empty_for_no_grants(self, repo, recipient):
        """验证无授权记录时返回空列表。"""
        results = repo.list_by_recipient(recipient["recipient_id"])
        assert results == []

    def test_list_by_recipient_multiple_grants(self, repo, recipient, share, share_repo):
        """验证多个授权记录全部返回。"""
        share2 = share_repo.create_share("test_share_2")
        repo.grant(recipient["recipient_id"], share["share_id"])
        repo.grant(recipient["recipient_id"], share2["share_id"])

        results = repo.list_by_recipient(recipient["recipient_id"])
        assert len(results) == 2


class TestListShareNames:
    """验证 RecipientShareRepository.list_share_names() 方法。"""

    def test_list_share_names_returns_list_of_strings(self, repo, granted, recipient):
        """验证返回值为字符串列表。"""
        names = repo.list_share_names(recipient["recipient_id"])
        assert isinstance(names, list)
        assert "test_share" in names

    def test_list_share_names_empty_for_no_grants(self, repo, recipient):
        """验证无授权记录时返回空列表。"""
        names = repo.list_share_names(recipient["recipient_id"])
        assert names == []

    def test_list_share_names_multiple_shares(self, repo, recipient, share, share_repo):
        """验证多个 share 的授权记录全部返回。"""
        share2 = share_repo.create_share("test_share_2")
        repo.grant(recipient["recipient_id"], share["share_id"])
        repo.grant(recipient["recipient_id"], share2["share_id"])

        names = repo.list_share_names(recipient["recipient_id"])
        assert len(names) == 2
        assert "test_share" in names
        assert "test_share_2" in names


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
