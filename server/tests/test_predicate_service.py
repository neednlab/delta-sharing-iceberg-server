"""
PredicateService 单元测试

覆盖 PredicateService 全部公开/内部方法：
- parse_predicate_hints: 谓词提示解析
- _parse_value_type: 类型转换
- _extract_partition_predicates_from_json: 从 JSON 树提取分区谓词
- _parse_spark_predicate_hint: 解析 Spark CAST 表达式
- _evaluate_partition_predicate: 单谓词分区值匹配
- filter_files_by_partition_pruning: 分区裁剪过滤
- matches_predicate_hint: 单文件谓词匹配
- filter_files: 两阶段过滤集成
- _extract_leaf_predicates: 叶子谓词提取
"""

import pytest
from app.services.predicate_service import PredicateService


@pytest.fixture
def ps():
    """创建 PredicateService 实例。"""
    return PredicateService()


class TestParsePredicateHints:
    def test_valid_json_list(self, ps):
        hints = ['{"op":"equal","children":[]}']
        result = ps.parse_predicate_hints(hints)
        assert len(result) == 1
        assert result[0]["op"] == "equal"

    def test_empty_list_returns_none(self, ps):
        assert ps.parse_predicate_hints([]) is None

    def test_none_input_returns_none(self, ps):
        assert ps.parse_predicate_hints(None) is None

    def test_invalid_json_returns_raw_expression(self, ps):
        hints = ["not valid json"]
        result = ps.parse_predicate_hints(hints)
        assert len(result) == 1
        assert result[0]["raw_expression"] == "not valid json"

    def test_mixed_valid_and_invalid(self, ps):
        hints = ['{"op":"equal","children":[]}', "bad json"]
        result = ps.parse_predicate_hints(hints)
        assert len(result) == 2
        assert result[0]["op"] == "equal"
        assert result[1]["raw_expression"] == "bad json"


class TestParseValueType:
    def test_int_type(self, ps):
        assert ps._parse_value_type("42", "int") == 42
        assert isinstance(ps._parse_value_type("42", "int"), int)

    def test_integer_type(self, ps):
        assert ps._parse_value_type("42", "integer") == 42

    def test_long_type(self, ps):
        assert ps._parse_value_type("9999999999", "long") == 9999999999
        assert isinstance(ps._parse_value_type("9999999999", "long"), int)

    def test_bigint_type(self, ps):
        assert ps._parse_value_type("100", "bigint") == 100

    def test_float_type(self, ps):
        assert ps._parse_value_type("3.14", "float") == pytest.approx(3.14)

    def test_double_type(self, ps):
        assert ps._parse_value_type("3.14", "double") == pytest.approx(3.14)

    def test_boolean_true(self, ps):
        assert ps._parse_value_type("true", "boolean") is True

    def test_boolean_false(self, ps):
        assert ps._parse_value_type("false", "boolean") is False

    def test_bool_short_type(self, ps):
        assert ps._parse_value_type("true", "bool") is True

    def test_string_type(self, ps):
        assert ps._parse_value_type("hello", "string") == "hello"

    def test_unknown_type_returns_string(self, ps):
        assert ps._parse_value_type("hello", "unknown_type") == "hello"


class TestExtractPartitionPredicatesFromJson:
    def test_simple_equal(self, ps):
        node = {
            "op": "equal",
            "children": [
                {"op": "column", "name": "dt"},
                {"op": "literal", "value": "2026-01-01", "valueType": "string"},
            ],
        }
        result = ps._extract_partition_predicates_from_json(node, ["dt"])
        assert "dt" in result
        assert len(result["dt"]) == 1
        assert result["dt"][0]["op"] == "equal"
        assert result["dt"][0]["literal"] == "2026-01-01"

    def test_and_expand(self, ps):
        node = {
            "op": "and",
            "children": [
                {
                    "op": "equal",
                    "children": [
                        {"op": "column", "name": "dt"},
                        {"op": "literal", "value": "2026-01-01", "valueType": "string"},
                    ],
                },
                {
                    "op": "greaterThan",
                    "children": [
                        {"op": "column", "name": "id"},
                        {"op": "literal", "value": "5", "valueType": "int"},
                    ],
                },
            ],
        }
        result = ps._extract_partition_predicates_from_json(node, ["dt", "id"])
        assert len(result["dt"]) == 1
        assert result["dt"][0]["op"] == "equal"
        assert len(result["id"]) == 1
        assert result["id"][0]["op"] == "greaterThan"
        assert result["id"][0]["literal"] == 5

    def test_or_node_skipped(self, ps):
        node = {
            "op": "or",
            "children": [
                {
                    "op": "equal",
                    "children": [
                        {"op": "column", "name": "dt"},
                        {"op": "literal", "value": "2026-01-01", "valueType": "string"},
                    ],
                },
            ],
        }
        result = ps._extract_partition_predicates_from_json(node, ["dt"])
        assert result == {}

    def test_not_is_null_inverts(self, ps):
        node = {
            "op": "not",
            "children": [
                {
                    "op": "isNull",
                    "children": [{"op": "column", "name": "dt"}],
                },
            ],
        }
        result = ps._extract_partition_predicates_from_json(node, ["dt"])
        assert "dt" in result
        assert result["dt"][0]["op"] == "isNotNull"

    def test_non_partition_column_filtered(self, ps):
        node = {
            "op": "equal",
            "children": [
                {"op": "column", "name": "other_col"},
                {"op": "literal", "value": "x", "valueType": "string"},
            ],
        }
        result = ps._extract_partition_predicates_from_json(node, ["dt"])
        assert result == {}


class TestParseSparkPredicateHint:
    def test_cast_equal(self, ps):
        hint = "(CAST(partitionValues.month_id AS INT) = 202604)"
        result = ps._parse_spark_predicate_hint(hint, ["month_id"])
        assert result is None

    def test_cast_is_null(self, ps):
        hint = "(CAST(partitionValues.dt AS STRING) IS NULL)"
        result = ps._parse_spark_predicate_hint(hint, ["dt"])
        assert result is None

    def test_cast_is_not_null(self, ps):
        hint = "(CAST(partitionValues.dt AS STRING) IS NOT NULL)"
        result = ps._parse_spark_predicate_hint(hint, ["dt"])
        assert result is None

    def test_non_partition_column_returns_none(self, ps):
        hint = "(CAST(partitionValues.other AS INT) = 1)"
        result = ps._parse_spark_predicate_hint(hint, ["dt"])
        assert result is None

    def test_garbage_string_returns_none(self, ps):
        result = ps._parse_spark_predicate_hint("garbage string", ["dt"])
        assert result is None

    def test_raw_expression_without_cast(self, ps):
        hint = "(partitionValues.dt = '2026-01-01')"
        result = ps._parse_spark_predicate_hint(hint, ["dt"])
        assert result is None

    def test_raw_expression_not_equal(self, ps):
        hint = "(partitionValues.id != 100)"
        result = ps._parse_spark_predicate_hint(hint, ["id"])
        assert result is None


class TestEvaluatePartitionPredicate:
    def test_equal_match(self, ps):
        pv = {"dt": "2026-01-01"}
        pred = {"column": "dt", "op": "equal", "literal": "2026-01-01"}
        assert ps._evaluate_partition_predicate(pv, pred) is True

    def test_equal_not_match(self, ps):
        pv = {"dt": "2026-01-01"}
        pred = {"column": "dt", "op": "equal", "literal": "2026-01-02"}
        assert ps._evaluate_partition_predicate(pv, pred) is False

    def test_less_than_match(self, ps):
        pv = {"id": 5}
        pred = {"column": "id", "op": "lessThan", "literal": 10}
        assert ps._evaluate_partition_predicate(pv, pred) is True

    def test_greater_than_not_match(self, ps):
        pv = {"id": 5}
        pred = {"column": "id", "op": "greaterThan", "literal": 10}
        assert ps._evaluate_partition_predicate(pv, pred) is False

    def test_is_null_match(self, ps):
        pv = {}
        pred = {"column": "dt", "op": "isNull"}
        assert ps._evaluate_partition_predicate(pv, pred) is True

    def test_is_not_null_not_match(self, ps):
        pv = {}
        pred = {"column": "dt", "op": "isNotNull"}
        assert ps._evaluate_partition_predicate(pv, pred) is False

    def test_not_equal(self, ps):
        pv = {"id": 5}
        pred = {"column": "id", "op": "notEqual", "literal": 10}
        assert ps._evaluate_partition_predicate(pv, pred) is True

    def test_none_column_returns_true(self, ps):
        pv = {"dt": "2026-01-01"}
        pred = {"op": "equal", "literal": "2026-01-01"}
        assert ps._evaluate_partition_predicate(pv, pred) is True

    def test_none_literal_returns_true(self, ps):
        pv = {"dt": "2026-01-01"}
        pred = {"column": "dt", "op": "equal"}
        assert ps._evaluate_partition_predicate(pv, pred) is True


class TestFilterFilesByPartitionPruning:
    def test_pruning_reduces_files(self, ps):
        files = [
            {"path": "f1.parquet", "partition_values": {"dt": "2026-01-01"}},
            {"path": "f2.parquet", "partition_values": {"dt": "2026-01-02"}},
            {"path": "f3.parquet", "partition_values": {"dt": "2026-01-01"}},
        ]
        json_pred = {
            "op": "equal",
            "children": [
                {"op": "column", "name": "dt"},
                {"op": "literal", "value": "2026-01-01", "valueType": "string"},
            ],
        }
        result = ps.filter_files_by_partition_pruning(files, json_pred, None, ["dt"])
        assert len(result) == 2

    def test_no_predicate_returns_all(self, ps):
        files = [
            {"path": "f1.parquet", "partition_values": {"dt": "2026-01-01"}},
        ]
        result = ps.filter_files_by_partition_pruning(files, None, None, ["dt"])
        assert len(result) == 1

    def test_no_partition_columns_returns_all(self, ps):
        files = [
            {"path": "f1.parquet", "partition_values": {"dt": "2026-01-01"}},
        ]
        json_pred = {
            "op": "equal",
            "children": [
                {"op": "column", "name": "dt"},
                {"op": "literal", "value": "2026-01-01", "valueType": "string"},
            ],
        }
        result = ps.filter_files_by_partition_pruning(files, json_pred, None, [])
        assert len(result) == 1

    def test_predicate_hints_raw_expression(self, ps):
        files = [
            {"path": "f1.parquet", "partition_values": {"month_id": "202604"}},
            {"path": "f2.parquet", "partition_values": {"month_id": "202605"}},
        ]
        predicate_hints = [{"raw_expression": "(CAST(partitionValues.month_id AS INT) = 202604)"}]
        result = ps.filter_files_by_partition_pruning(files, None, predicate_hints, ["month_id"])
        assert len(result) == 2


class TestMatchesPredicateHint:
    def test_partition_value_match(self, ps):
        file_info = {"partition_values": {"dt": "2026-01-01"}}
        pred = {"column": "dt", "op": "equal", "literal": "2026-01-01"}
        assert ps.matches_predicate_hint(file_info, pred) is True

    def test_partition_value_not_match(self, ps):
        file_info = {"partition_values": {"dt": "2026-01-01"}}
        pred = {"column": "dt", "op": "equal", "literal": "2026-01-02"}
        assert ps.matches_predicate_hint(file_info, pred) is False

    def test_stats_min_max_filter_hit(self, ps):
        file_info = {
            "partition_values": {},
            "stats": {
                "minValues": {"id": 1},
                "maxValues": {"id": 100},
                "nullCount": {},
            },
        }
        pred = {"column": "id", "op": "equal", "literal": 50}
        assert ps.matches_predicate_hint(file_info, pred) is True

    def test_stats_min_max_filter_miss(self, ps):
        file_info = {
            "partition_values": {},
            "stats": {
                "minValues": {"id": 1},
                "maxValues": {"id": 100},
                "nullCount": {},
            },
        }
        pred = {"column": "id", "op": "equal", "literal": 200}
        assert ps.matches_predicate_hint(file_info, pred) is False

    def test_null_count_causes_false(self, ps):
        file_info = {
            "partition_values": {},
            "stats": {
                "minValues": {"name": "Alice"},
                "maxValues": {"name": "Zoe"},
                "nullCount": {"name": 5},
            },
        }
        pred = {"column": "name", "op": "equal", "literal": "Alice"}
        assert ps.matches_predicate_hint(file_info, pred) is False

    def test_raw_expression_delegation(self, ps):
        file_info = {"partition_values": {"dt": "2026-01-01"}}
        pred = {"raw_expression": "(partitionValues.dt = '2026-01-01')"}
        assert ps.matches_predicate_hint(file_info, pred) is True

    def test_no_column_returns_true(self, ps):
        file_info = {"partition_values": {}}
        pred = {"op": "equal", "literal": "2026-01-01"}
        assert ps.matches_predicate_hint(file_info, pred) is True


class TestFilterFiles:
    def test_two_stage_filtering(self, ps):
        files = [
            {
                "path": "f1.parquet",
                "partition_values": {"dt": "2026-01-01"},
                "stats": {
                    "minValues": {"id": 1},
                    "maxValues": {"id": 50},
                    "nullCount": {},
                },
            },
            {
                "path": "f2.parquet",
                "partition_values": {"dt": "2026-01-01"},
                "stats": {
                    "minValues": {"id": 51},
                    "maxValues": {"id": 100},
                    "nullCount": {},
                },
            },
            {
                "path": "f3.parquet",
                "partition_values": {"dt": "2026-01-02"},
                "stats": {
                    "minValues": {"id": 1},
                    "maxValues": {"id": 100},
                    "nullCount": {},
                },
            },
        ]
        json_pred = {
            "op": "equal",
            "children": [
                {"op": "column", "name": "dt"},
                {"op": "literal", "value": "2026-01-01", "valueType": "string"},
            ],
        }
        predicate_hints = [{"column": "id", "op": "equal", "literal": 25}]
        result = ps.filter_files(files, json_pred, predicate_hints, ["dt"])
        assert len(result) == 1
        assert result[0]["path"] == "f1.parquet"

    def test_partition_only_predicates_no_wasteful_reprocessing(self, ps):
        files = [
            {"path": "f1.parquet", "partition_values": {"dt": "2026-01-01"}},
            {"path": "f2.parquet", "partition_values": {"dt": "2026-01-02"}},
        ]
        json_pred = {
            "op": "equal",
            "children": [
                {"op": "column", "name": "dt"},
                {"op": "literal", "value": "2026-01-01", "valueType": "string"},
            ],
        }
        result = ps.filter_files(files, json_pred, None, ["dt"])
        assert len(result) == 1
        assert result[0]["path"] == "f1.parquet"


class TestExtractLeafPredicates:
    def test_extract_from_and_tree(self, ps):
        node = {
            "op": "and",
            "children": [
                {
                    "op": "equal",
                    "children": [
                        {"op": "column", "name": "dt"},
                        {"op": "literal", "value": "2026-01-01"},
                    ],
                },
                {
                    "op": "isNull",
                    "children": [{"op": "column", "name": "category"}],
                },
            ],
        }
        leaves = ps._extract_leaf_predicates(node)
        assert len(leaves) == 2
        columns = {leaf["column"] for leaf in leaves}
        assert columns == {"dt", "category"}

    def test_extract_from_nested_tree(self, ps):
        node = {
            "op": "or",
            "children": [
                {
                    "op": "and",
                    "children": [
                        {
                            "op": "equal",
                            "children": [
                                {"op": "column", "name": "dt"},
                                {"op": "literal", "value": "2026-01-01"},
                            ],
                        },
                    ],
                },
                {
                    "op": "isNotNull",
                    "children": [{"op": "column", "name": "category"}],
                },
            ],
        }
        leaves = ps._extract_leaf_predicates(node)
        assert len(leaves) == 2

    def test_not_node_traversed(self, ps):
        node = {
            "op": "not",
            "children": [
                {
                    "op": "equal",
                    "children": [
                        {"op": "column", "name": "dt"},
                        {"op": "literal", "value": "2026-01-01"},
                    ],
                },
            ],
        }
        leaves = ps._extract_leaf_predicates(node)
        assert len(leaves) == 1
        assert leaves[0]["column"] == "dt"

    def test_empty_input(self, ps):
        assert ps._extract_leaf_predicates({}) == []

    def test_non_dict_input(self, ps):
        assert ps._extract_leaf_predicates("not_a_dict") == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
