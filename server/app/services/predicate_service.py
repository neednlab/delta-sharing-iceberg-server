"""
谓词解析与文件过滤服务

将客户端发送的 predicateHints / jsonPredicateHints 解析为结构化的谓词条件，
并基于 partition_values 和文件统计信息（min/max/nullCount）执行分区裁剪和文件级过滤。

所有逻辑提取自原 query.py 中的模块级函数，重构为无状态 Service 类。
"""

import json
import re
from typing import Any, Dict, List, Optional

from loguru import logger


class PredicateService:
    """谓词解析与文件过滤服务。

    采用与项目中 ShareService、IcebergService 一致的无状态 Service 类模式。
    公开方法提供谓词解析、分区裁剪和文件级过滤功能。
    """

    def parse_predicate_hints(
        self, predicate_hints: Optional[List[str]]
    ) -> Optional[List[Dict[str, Any]]]:
        """解析谓词提示列表。

        Args:
            predicate_hints: 谓词提示字符串列表，每个元素是 JSON 格式的谓词表达式。

        Returns:
            解析后的谓词字典列表，如果解析失败则返回包含 raw_expression 的字典。
        """
        if not predicate_hints:
            return None

        parsed = []
        for hint in predicate_hints:
            try:
                parsed.append(json.loads(hint))
            except json.JSONDecodeError:
                parsed.append({"raw_expression": hint})
        return parsed

    def _parse_value_type(self, value_str: str, value_type: str) -> Any:
        """根据 valueType 将字符串值转换为正确的 Python 类型。

        Args:
            value_str: 字符串值。
            value_type: 值类型（如 'int', 'long', 'string', 'double' 等）。

        Returns:
            转换后的 Python 值。
        """
        if value_type in ("int", "integer"):
            return int(value_str)
        elif value_type in ("long", "bigint"):
            return int(value_str)
        elif value_type in ("float", "double"):
            return float(value_str)
        elif value_type in ("boolean", "bool"):
            return value_str.lower() == "true"
        return value_str

    def _extract_partition_predicates_from_json(
        self,
        json_predicate: Dict[str, Any],
        partition_columns: List[str],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """从 JSON 谓词树中提取分区列的过滤条件。

        递归遍历 JSON 谓词树，提取出所有作用在分区列上的简单谓词
        （如 equal、lessThan、greaterThan 等），按列名分组返回。

        正确处理 NOT 节点的谓词取反：NOT(isNull(col)) → isNotNull(col)

        Args:
            json_predicate: JSON 谓词树（由 jsonPredicateHints 解析得到）。
            partition_columns: 表的分区列名称列表。

        Returns:
            按列名分组的谓词条件字典，格式为 {col_name: [{"op": "equal", "literal": 202604}, ...]}。
        """
        predicates: Dict[str, List[Dict[str, Any]]] = {}

        def _negate_op(op: str) -> str:
            """对谓词操作符取反。"""
            negation_map = {
                "isNull": "isNotNull",
                "isNotNull": "isNull",
                "equal": "notEqual",
                "notEqual": "equal",
                "lessThan": "greaterThanOrEqual",
                "lessThanOrEqual": "greaterThan",
                "greaterThan": "lessThanOrEqual",
                "greaterThanOrEqual": "lessThan",
            }
            return negation_map.get(op, op)

        def _extract_from_node(node: Dict[str, Any], negated: bool = False) -> None:
            if not isinstance(node, dict):
                return

            op = node.get("op", "unknown")

            if op == "and":
                for child in node.get("children", []):
                    _extract_from_node(child, negated)
            elif op == "or":
                pass
            elif op == "not":
                for child in node.get("children", []):
                    _extract_from_node(child, not negated)
            elif op in (
                "equal",
                "lessThan",
                "lessThanOrEqual",
                "greaterThan",
                "greaterThanOrEqual",
            ):
                children = node.get("children", [])
                if len(children) >= 2:
                    col_node = children[0]
                    lit_node = children[1]
                    if (
                        isinstance(col_node, dict)
                        and col_node.get("op") == "column"
                        and isinstance(lit_node, dict)
                        and lit_node.get("op") == "literal"
                    ):
                        col_name = col_node.get("name", "")
                        if col_name in partition_columns:
                            value_type = lit_node.get("valueType", "string")
                            literal_val = self._parse_value_type(
                                lit_node.get("value", ""), value_type
                            )
                            final_op = _negate_op(op) if negated else op
                            if col_name not in predicates:
                                predicates[col_name] = []
                            predicates[col_name].append(
                                {
                                    "op": final_op,
                                    "literal": literal_val,
                                    "valueType": value_type,
                                }
                            )
            elif op == "isNull":
                children = node.get("children", [])
                if children:
                    col_node = children[0]
                    if isinstance(col_node, dict) and col_node.get("op") == "column":
                        col_name = col_node.get("name", "")
                        if col_name in partition_columns:
                            final_op = "isNotNull" if negated else "isNull"
                            if col_name not in predicates:
                                predicates[col_name] = []
                            predicates[col_name].append(
                                {
                                    "op": final_op,
                                    "valueType": col_node.get("valueType", "string"),
                                }
                            )
            elif op == "isNotNull":
                children = node.get("children", [])
                if children:
                    col_node = children[0]
                    if isinstance(col_node, dict) and col_node.get("op") == "column":
                        col_name = col_node.get("name", "")
                        if col_name in partition_columns:
                            final_op = "isNull" if negated else "isNotNull"
                            if col_name not in predicates:
                                predicates[col_name] = []
                            predicates[col_name].append(
                                {
                                    "op": final_op,
                                    "valueType": col_node.get("valueType", "string"),
                                }
                            )
            elif op == "column":
                pass
            elif op == "literal":
                pass

        _extract_from_node(json_predicate)
        return predicates

    def _parse_spark_predicate_hint(
        self, hint: str, partition_columns: List[str]
    ) -> Optional[Dict[str, Any]]:
        """解析 Spark 生成的简单谓词提示字符串。

        Spark 客户端发送的 predicateHints 格式如：
        '(CAST(partitionValues.month_id AS INT) = 202604)'
        或 '(CAST(partitionValues.month_id AS INT) IS NOT NULL)'

        Args:
            hint: Spark 谓词提示字符串。
            partition_columns: 表的分区列名称列表。

        Returns:
            解析后的谓词字典，格式为 {"column": "month_id", "op": "equal", "literal": 202604}，
            无法解析或非分区列则返回 None。
        """
        hint_stripped = hint.strip()
        if hint_stripped.startswith("(") and hint_stripped.endswith(")"):
            hint_stripped = hint_stripped[1:-1]

        cast_pattern = r"CAST\s*\(\s*partitionValues\.(\\w+)\s+AS\s+(\\w+)\s*\)\s*(=|!=|<>|>=|<=|>|<)\s*(.+)"
        cast_match = re.match(cast_pattern, hint_stripped, re.IGNORECASE)
        if cast_match:
            col_name = cast_match.group(1)
            col_type = cast_match.group(2)
            op_token = cast_match.group(3)
            literal_str = cast_match.group(4).strip()

            if col_name not in partition_columns:
                return None

            if op_token == "=":
                op = "equal"
            elif op_token in ("!=", "<>"):
                op = "notEqual"
            elif op_token == ">":
                op = "greaterThan"
            elif op_token == ">=":
                op = "greaterThanOrEqual"
            elif op_token == "<":
                op = "lessThan"
            elif op_token == "<=":
                op = "lessThanOrEqual"
            else:
                return None

            try:
                literal_val = self._parse_value_type(literal_str, col_type)
            except (ValueError, TypeError):
                return None

            return {"column": col_name, "op": op, "literal": literal_val}

        null_pattern = r"CAST\s*\(\s*partitionValues\.(\\w+)\s+AS\s+(\\w+)\s*\)\s+IS\s+(NOT\s+)?NULL"
        null_match = re.match(null_pattern, hint_stripped, re.IGNORECASE)
        if null_match:
            col_name = null_match.group(1)
            is_not_null = null_match.group(3) is not None
            if col_name not in partition_columns:
                return None
            return {"column": col_name, "op": "isNotNull" if is_not_null else "isNull"}

        raw_col_pattern = r"partitionValues\.(\\w+)\s*(=|!=|<>|>=|<=|>|<)\s*(.+)"
        raw_match = re.match(raw_col_pattern, hint_stripped, re.IGNORECASE)
        if raw_match:
            col_name = raw_match.group(1)
            op_token = raw_match.group(2)
            literal_str = raw_match.group(3).strip()

            if col_name not in partition_columns:
                return None

            if op_token == "=":
                op = "equal"
            elif op_token in ("!=", "<>"):
                op = "notEqual"
            elif op_token == ">":
                op = "greaterThan"
            elif op_token == ">=":
                op = "greaterThanOrEqual"
            elif op_token == "<":
                op = "lessThan"
            elif op_token == "<=":
                op = "lessThanOrEqual"
            else:
                return None

            literal_str = literal_str.strip("'").strip('"')
            try:
                literal_val = int(literal_str)
            except ValueError:
                try:
                    literal_val = float(literal_str)
                except ValueError:
                    literal_val = literal_str

            return {"column": col_name, "op": op, "literal": literal_val}

        return None

    def _evaluate_partition_predicate(
        self,
        partition_values: Dict[str, Any],
        predicate: Dict[str, Any],
    ) -> bool:
        """判断文件的 partition_values 是否匹配单个分区谓词条件。

        这是 PredicateService 内部唯一的分区值比较入口，
        matches_predicate_hint 在命中分区列时委托调用本方法。

        Args:
            partition_values: 文件的分区值字典。
            predicate: 单个谓词条件（从 _extract_partition_predicates_from_json 产生）。

        Returns:
            如果匹配返回 True，否则返回 False。
        """
        col_name = predicate.get("column")
        op = predicate.get("op")

        if col_name is None:
            return True

        if op == "isNull":
            return (
                col_name not in partition_values
                or partition_values.get(col_name) is None
            )
        elif op == "isNotNull":
            return (
                col_name in partition_values
                and partition_values.get(col_name) is not None
            )

        literal = predicate.get("literal")
        if literal is None:
            return True

        partition_value = partition_values.get(col_name)
        if partition_value is None:
            return False

        try:
            pv = int(partition_value)
            lit_val = int(literal)
        except (ValueError, TypeError):
            try:
                pv = float(partition_value)
                lit_val = float(literal)
            except (ValueError, TypeError):
                pv = str(partition_value)
                lit_val = str(literal)

        if op == "equal":
            return pv == lit_val
        elif op == "lessThan":
            return pv < lit_val
        elif op == "lessThanOrEqual":
            return pv <= lit_val
        elif op == "greaterThan":
            return pv > lit_val
        elif op == "greaterThanOrEqual":
            return pv >= lit_val
        elif op == "notEqual":
            return pv != lit_val

        return True

    def filter_files_by_partition_pruning(
        self,
        data_files: List[Dict[str, Any]],
        json_predicate: Optional[Dict[str, Any]],
        predicate_hints: Optional[List[Dict[str, Any]]],
        partition_columns: List[str],
    ) -> List[Dict[str, Any]]:
        """对数据文件列表执行分区裁剪过滤。

        根据客户端发送的谓词条件（jsonPredicateHints / predicateHints），
        对比每个文件的 partition_values，过滤掉不在目标分区范围内的文件。

        Args:
            data_files: 原始数据文件列表。
            json_predicate: JSON 格式的谓词条件树。
            predicate_hints: Spark 简单谓词提示列表。
            partition_columns: 表的分区列名称列表。

        Returns:
            过滤后的数据文件列表。
        """
        if not partition_columns or (not json_predicate and not predicate_hints):
            return data_files

        all_predicates: Dict[str, List[Dict[str, Any]]] = {}

        if json_predicate and isinstance(json_predicate, dict):
            json_preds = self._extract_partition_predicates_from_json(
                json_predicate, partition_columns
            )
            for col, preds in json_preds.items():
                if col not in all_predicates:
                    all_predicates[col] = []
                all_predicates[col].extend(preds)

        if predicate_hints:
            for hint in predicate_hints:
                if isinstance(hint, dict) and "raw_expression" in hint:
                    spark_pred = self._parse_spark_predicate_hint(
                        hint["raw_expression"], partition_columns
                    )
                    if spark_pred:
                        col = spark_pred["column"]
                        if col not in all_predicates:
                            all_predicates[col] = []
                        all_predicates[col].append(
                            {
                                "op": spark_pred["op"],
                                "literal": spark_pred.get("literal"),
                                "valueType": "string",
                            }
                        )

        if not all_predicates:
            return data_files

        logger.info(
            f"Partition pruning enabled with partition_columns={partition_columns}, "
            f"predicates={all_predicates}, total_files={len(data_files)}"
        )

        pruned_files = []
        for f in data_files:
            partition_values = f.get("partition_values", {})
            if not isinstance(partition_values, dict):
                partition_values = {}
            matches = True
            for col, preds in all_predicates.items():
                for pred in preds:
                    pred_copy = dict(pred)
                    pred_copy["column"] = col
                    if not self._evaluate_partition_predicate(
                        partition_values, pred_copy
                    ):
                        matches = False
                        break
                if not matches:
                    break
            if matches:
                pruned_files.append(f)

        if len(pruned_files) < len(data_files):
            logger.info(
                f"Partition pruning filtered files: {len(data_files)} -> {len(pruned_files)}"
            )

        return pruned_files

    def _get_predicate_target_columns(
        self,
        predicate: Dict[str, Any],
        partition_columns: List[str],
    ) -> List[str]:
        """获取谓词条件目标的分区列列表。

        Args:
            predicate: 单个谓词条件字典。
            partition_columns: 表的分区列名称列表。

        Returns:
            该谓词目标的分区列名称列表（可能为空）。
        """
        if isinstance(predicate, dict):
            col = predicate.get("column")
            if col and col in partition_columns:
                return [col]
        return []

    def filter_files(
        self,
        data_files: List[Dict[str, Any]],
        json_predicate: Optional[Dict[str, Any]],
        predicate_hints: Optional[List[Dict[str, Any]]],
        partition_columns: List[str],
    ) -> List[Dict[str, Any]]:
        """统一谓词过滤方法，合并分区裁剪和文件级统计过滤为单次调用。

        内部先调用 filter_files_by_partition_pruning 做分区裁剪，
        再对裁剪后的文件逐文件调用 matches_predicate_hint 做统计过滤，
        但跳过已在分区裁剪阶段处理的分区列谓词，消除两阶段重叠。

        Args:
            data_files: 原始数据文件列表。
            json_predicate: JSON 格式的谓词条件树。
            predicate_hints: 解析后的谓词提示列表。
            partition_columns: 表的分区列名称列表。

        Returns:
            过滤后的数据文件列表。
        """
        # 阶段一：分区裁剪
        pruned = self.filter_files_by_partition_pruning(
            data_files, json_predicate, predicate_hints, partition_columns
        )

        if not pruned:
            return pruned

        # 确定哪些分区列在阶段一中已有谓词条件处理
        handled_partition_cols: set = set()
        if partition_columns and predicate_hints:
            for pred in predicate_hints:
                handled_partition_cols.update(
                    self._get_predicate_target_columns(pred, partition_columns)
                )
        if partition_columns and json_predicate and isinstance(json_predicate, dict):
            json_preds = self._extract_partition_predicates_from_json(
                json_predicate, partition_columns
            )
            handled_partition_cols.update(json_preds.keys())

        # 阶段二：逐文件统计过滤，跳过已处理的分区列谓词
        result = []
        for f in pruned:
            matches = True
            if predicate_hints:
                for pred in predicate_hints:
                    # 跳过 Spark 原始表达式类型的谓词（仅涉及分区列）
                    if isinstance(pred, dict) and "raw_expression" in pred:
                        continue
                    # 跳过目标列为已处理分区列的谓词
                    target_cols = self._get_predicate_target_columns(
                        pred, partition_columns
                    )
                    if any(col in handled_partition_cols for col in target_cols):
                        continue
                    if not self.matches_predicate_hint(f, pred):
                        matches = False
                        break
            if matches and json_predicate and isinstance(json_predicate, dict):
                # json_predicate 为树形结构，其分区列谓词已在阶段一处理
                # 从树中提取非分区列的叶子谓词进行过滤
                leaf_preds = self._extract_leaf_predicates(json_predicate)
                for leaf in leaf_preds:
                    col = leaf.get("column")
                    if col in handled_partition_cols:
                        continue
                    if not self.matches_predicate_hint(f, leaf):
                        matches = False
                        break
            if matches:
                result.append(f)

        if len(result) < len(pruned):
            logger.info(
                f"Statistics filtering: {len(pruned)} -> {len(result)} files "
                f"(skipped {len(handled_partition_cols)} partition columns)"
            )

        return result

    def _extract_leaf_predicates(self, node: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从 JSON 谓词树中提取叶子谓词节点。

        遍历谓词树，提取 equal/lessThan/greaterThan/isNull 等叶子节点，
        跳过 and/or/not 等逻辑节点。

        Args:
            node: JSON 谓词树节点。

        Returns:
            叶子谓词列表。
        """
        if not isinstance(node, dict):
            return []

        op = node.get("op", "unknown")

        if op in ("and", "or"):
            leaves = []
            for child in node.get("children", []):
                leaves.extend(self._extract_leaf_predicates(child))
            return leaves
        elif op == "not":
            leaves = []
            for child in node.get("children", []):
                leaves.extend(self._extract_leaf_predicates(child))
            return leaves
        elif op in (
            "equal",
            "lessThan",
            "lessThanOrEqual",
            "greaterThan",
            "greaterThanOrEqual",
        ):
            children = node.get("children", [])
            if len(children) >= 2:
                col_node = children[0]
                lit_node = children[1]
                if (
                    isinstance(col_node, dict)
                    and col_node.get("op") == "column"
                    and isinstance(lit_node, dict)
                    and lit_node.get("op") == "literal"
                ):
                    return [
                        {
                            "column": col_node.get("name", ""),
                            "op": op,
                            "literal": lit_node.get("value", ""),
                        }
                    ]
            return []
        elif op in ("isNull", "isNotNull"):
            children = node.get("children", [])
            if children:
                col_node = children[0]
                if isinstance(col_node, dict) and col_node.get("op") == "column":
                    return [
                        {
                            "column": col_node.get("name", ""),
                            "op": op,
                            "literal": None,
                        }
                    ]
            return []

        return []

    def _get_file_stats(self, file_info: Dict[str, Any]) -> Dict[str, Any]:
        """从文件信息字典中提取统一的统计信息结构。

        兼容两种数据源：
        - 扁平的 min_values/max_values/null_count 键（直接从 manifest 解析）
        - 嵌套的 stats 字典（经过序列化的 stats 字符串）

        Args:
            file_info: 文件信息字典。

        Returns:
            包含 minValues、maxValues、nullCount 键的字典。
        """
        stats = file_info.get("stats", {})

        if not stats:
            min_values = file_info.get("min_values", {})
            max_values = file_info.get("max_values", {})
            null_count = file_info.get("null_count", {})

            if min_values or max_values or null_count:
                stats = {
                    "minValues": min_values if isinstance(min_values, dict) else {},
                    "maxValues": max_values if isinstance(max_values, dict) else {},
                    "nullCount": null_count if isinstance(null_count, dict) else {},
                }

        return stats if isinstance(stats, dict) else {}

    def matches_predicate_hint(
        self, file_info: Dict[str, Any], predicate: Dict[str, Any]
    ) -> bool:
        """判断文件是否匹配谓词条件。

        优先使用 partition_values 进行分区裁剪，其次使用文件统计信息
        （minValues、maxValues、nullCount）进行过滤。

        当命中分区列时，委托调用 _evaluate_partition_predicate 进行比较，
        消除了原实现中与 _evaluate_partition_predicate 重复的比较逻辑。

        Args:
            file_info: 文件信息字典，可包含 partition_values、stats 等。
            predicate: 谓词条件字典。

        Returns:
            如果文件匹配谓词条件返回 True，否则返回 False。
        """
        if "raw_expression" in predicate:
            partition_values = file_info.get("partition_values", {})
            if not isinstance(partition_values, dict):
                partition_values = {}
            if partition_values:
                spark_pred = self._parse_spark_predicate_hint(
                    predicate["raw_expression"], list(partition_values.keys())
                )
                if spark_pred:
                    return self._evaluate_partition_predicate(
                        partition_values, spark_pred
                    )
            return True

        column = predicate.get("column")
        if not column:
            return True

        operator = predicate.get("op", "equal")
        literal = predicate.get("literal")

        partition_values = file_info.get("partition_values", {})
        if isinstance(partition_values, dict) and column in partition_values:
            return self._evaluate_partition_predicate(
                partition_values,
                {"column": column, "op": operator, "literal": literal},
            )

        stats = self._get_file_stats(file_info)
        min_values = stats.get("minValues", {})
        max_values = stats.get("maxValues", {})
        null_count = stats.get("nullCount", {})

        if column in null_count and null_count[column] > 0:
            if operator in [
                "equal",
                "lessThan",
                "lessThanOrEqual",
                "greaterThan",
                "greaterThanOrEqual",
            ]:
                return False

        min_val = min_values.get(column)
        max_val = max_values.get(column)

        if min_val is None or max_val is None:
            return True

        if literal is None:
            return True

        try:
            lit_val = type(min_val)(literal)

            if operator == "equal":
                return min_val <= lit_val <= max_val
            elif operator == "lessThan":
                return min_val < lit_val
            elif operator == "lessThanOrEqual":
                return min_val <= lit_val
            elif operator == "greaterThan":
                return max_val > lit_val
            elif operator == "greaterThanOrEqual":
                return max_val >= lit_val
            elif operator == "notEqual":
                return lit_val < min_val or lit_val > max_val
        except (ValueError, TypeError):
            pass

        return True
