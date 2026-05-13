"""
UniqueChecker — 检查某字段(或多字段组合)是否唯一

YAML 配置示例:
  - type: unique
    table: shopify_orders
    column: order_id

  # 也支持多字段组合唯一
  - type: unique
    table: order_lines
    columns: [order_id, line_number]
"""

import pandas as pd
from typing import Optional, List, Union
from data_quality.checkers.base import BaseChecker, CheckResult


class UniqueChecker(BaseChecker):
    """检查指定 column(单字段)或 columns(多字段组合)是否唯一"""

    def __init__(
        self,
        table: str,
        column: Optional[str] = None,
        columns: Optional[List[str]] = None,
        **kwargs
    ):
        """
        Args:
            column: 单字段唯一性(常用)
            columns: 多字段组合唯一性(复合主键场景)
        """
        super().__init__(table=table, column=column, **kwargs)
        self.columns = columns
        # 优先用 columns(多字段),其次用 column(单字段)
        self.check_columns = columns if columns else [column] if column else []

    def check(self, df: pd.DataFrame) -> CheckResult:
        # 防御性编程:check_columns 不能为空
        if not self.check_columns:
            return CheckResult(
                check_name=self.check_name,
                table=self.table,
                column=self.column,
                passed=False,
                failed_count=0,
                total_count=len(df),
                error_message="UniqueChecker requires 'column' or 'columns' parameter"
            )

        # 检查所有指定字段都存在
        missing = [c for c in self.check_columns if c not in df.columns]
        if missing:
            return CheckResult(
                check_name=self.check_name,
                table=self.table,
                column=",".join(self.check_columns),
                passed=False,
                failed_count=0,
                total_count=len(df),
                error_message=f"Column(s) not found: {missing}"
            )

        total = len(df)
        # duplicated() 返回 boolean Series,True 表示重复(第一次出现不算重复)
        # 用 keep=False 把所有重复行都标记(包括第一次出现的)
        duplicated_mask = df.duplicated(subset=self.check_columns, keep=False)
        failed = duplicated_mask.sum()
        passed = failed == 0

        return CheckResult(
            check_name=self.check_name,
            table=self.table,
            column=",".join(self.check_columns),
            passed=passed,
            failed_count=int(failed),
            total_count=total,
            error_message=None if passed else f"{failed} duplicate rows found on {self.check_columns}"
        )