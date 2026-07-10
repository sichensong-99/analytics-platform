"""
NotNullChecker — 检查某字段是否有 null 值

YAML 配置示例:
  - type: not_null
    table: shopify_orders
    column: order_id
"""

import pandas as pd
from data_quality.checkers.base import BaseChecker, CheckResult


class NotNullChecker(BaseChecker):
    """检查指定 column 没有 null/NaN 值"""

    def check(self, df: pd.DataFrame) -> CheckResult:
        # 防御性编程:检查 column 是否存在
        if self.column not in df.columns:
            return CheckResult(
                check_name=self.check_name,
                table=self.table,
                column=self.column,
                passed=False,
                failed_count=0,
                total_count=len(df),
                error_message=f"Column '{self.column}' not found in table"
            )

        total = len(df)
        # pandas 的 isna() 同时识别 None, NaN, NaT
        failed = df[self.column].isna().sum()
        passed = failed == 0

        return CheckResult(
            check_name=self.check_name,
            table=self.table,
            column=self.column,
            passed=passed,
            failed_count=int(failed),
            total_count=total,
            error_message=None if passed else f"{failed} null values found"
        )