"""
Runner — DQ 框架的核心引擎

职责:
  1. 读取 YAML 配置文件
  2. 根据配置实例化对应的 checker
  3. 调用每个 checker 的 check() 方法
  4. 收集所有结果,返回给上层

使用方式:
  runner = DQRunner.from_yaml("configs/shopify_orders.yaml")
  results = runner.run(dataframes_dict)
"""

import yaml
from pathlib import Path
from typing import Dict, List, Any
import pandas as pd

from data_quality.checkers.base import BaseChecker, CheckResult
from data_quality.checkers.not_null import NotNullChecker
from data_quality.checkers.unique import UniqueChecker
from data_quality.checkers.range import RangeChecker
from data_quality.checkers.freshness import FreshnessChecker


# Checker 类型注册表 —— 加新 checker 时只需在这里加一行
CHECKER_REGISTRY: Dict[str, type[BaseChecker]] = {
    "not_null":  NotNullChecker,
    "unique":    UniqueChecker,
    "range":     RangeChecker,
    "freshness": FreshnessChecker,
}


class DQRunner:
    """数据质量检查的运行引擎"""

    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: 已解析的 YAML 配置 dict,格式见 YAML 示例
        """
        self.config = config
        self.checks = config.get("checks", [])

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "DQRunner":
        """从 YAML 文件构造 runner"""
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"YAML config not found: {yaml_path}")

        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        if not isinstance(config, dict) or "checks" not in config:
            raise ValueError(
                f"Invalid YAML structure. Expected 'checks' key at top level."
            )

        return cls(config)

    def _build_checker(self, check_spec: Dict[str, Any]) -> BaseChecker:
        """
        根据单条 YAML check 配置,实例化对应的 checker
        
        check_spec 格式:
          {
            "type": "not_null",
            "table": "shopify_orders",
            "column": "order_id"
          }
        """
        check_type = check_spec.get("type")
        if not check_type:
            raise ValueError(f"Check missing 'type': {check_spec}")

        checker_class = CHECKER_REGISTRY.get(check_type)
        if not checker_class:
            raise ValueError(
                f"Unknown checker type '{check_type}'. "
                f"Available: {list(CHECKER_REGISTRY.keys())}"
            )

        # 除 type 外的所有字段都传给 checker 的 __init__
        kwargs = {k: v for k, v in check_spec.items() if k != "type"}
        return checker_class(**kwargs)

    def run(self, dataframes: Dict[str, pd.DataFrame]) -> List[CheckResult]:
        """
        跑所有检查
        
        Args:
            dataframes: {table_name: DataFrame} 的字典,
                        runner 会按 check 的 table 名查找对应数据
        
        Returns:
            所有 CheckResult 的列表
        """
        results = []

        for check_spec in self.checks:
            try:
                checker = self._build_checker(check_spec)
            except (ValueError, TypeError) as e:
                # 配置错误,生成一个 fail 结果而不是 crash
                results.append(CheckResult(
                    check_name=check_spec.get("type", "unknown"),
                    table=check_spec.get("table", "unknown"),
                    column=check_spec.get("column"),
                    passed=False,
                    failed_count=0,
                    total_count=0,
                    error_message=f"Config error: {e}"
                ))
                continue

            # 找对应的 DataFrame
            df = dataframes.get(checker.table)
            if df is None:
                results.append(CheckResult(
                    check_name=checker.check_name,
                    table=checker.table,
                    column=checker.column,
                    passed=False,
                    failed_count=0,
                    total_count=0,
                    error_message=f"Table '{checker.table}' not provided in dataframes dict"
                ))
                continue

            # 跑检查
            result = checker.check(df)
            results.append(result)

        return results