"""
RangeChecker — 检查某数值字段在指定范围内

YAML 配置示例:
  - type: range
    table: shopify_orders
    column: total_price
    min: 0
    max: 100000

  # min 或 max 可单独使用
  - type: range
    table: shopify_orders
    column: total_price
    min: 0   # 只检查 >= 0,不限上界
"""

import pandas as pd
from typing import Optional
from data_quality.checkers.base import BaseChecker, CheckResult


class RangeChecker(BaseChecker):
    """检查指定数值字段在 [min, max] 范围内"""

    def __init__(
        self,
        table: str,
        column: str,
        min: Optional[float] = None,
        max: Optional[float] = None,
        **kwargs
    ):
        """
        Args:
            column: 要检查的数值字段
            min: 允许的最小值(包含),None 表示不限下界
            max: 允许的最大值(包含),None 表示不限上界
        """
        super().__init__(table=table, column=column, **kwargs)
        self.min = min
        self.max = max

    def check(self, df: pd.DataFrame) -> CheckResult:
        # 防御性编程:column 必传
        if not self.column:
            return CheckResult(
                check_name=self.check_name,
                table=self.table,
                column=None,
                passed=False,
                failed_count=0,
                total_count=len(df),
                error_message="RangeChecker requires 'column' parameter"
            )

        if self.column not in df.columns:
            return CheckResult(
                check_name=self.check_name,
                table=self.table,
                column=self.column,
                passed=False,
                failed_count=0,
                total_count=len(df),
                error_message=f"Column '{self.column}' not found"
            )

        # 至少要指定 min 或 max 之一
        if self.min is None and self.max is None:
            return CheckResult(
                check_name=self.check_name,
                table=self.table,
                column=self.column,
                passed=False,
                failed_count=0,
                total_count=len(df),
                error_message="RangeChecker requires at least 'min' or 'max'"
            )

        total = len(df)
        # 忽略 null 值(null 不算 out-of-range,可以单独用 NotNullChecker 查)
        non_null = df[self.column].dropna()

        # 构建 out-of-range mask
        out_of_range = pd.Series([False] * len(non_null), index=non_null.index)
        if self.min is not None:
            out_of_range |= (non_null < self.min)
        if self.max is not None:
            out_of_range |= (non_null > self.max)

        failed = int(out_of_range.sum())
        passed = failed == 0

        # 构造易读的错误信息
        range_str = ""
        if self.min is not None and self.max is not None:
            range_str = f"[{self.min}, {self.max}]"
        elif self.min is not None:
            range_str = f">= {self.min}"
        else:
            range_str = f"<= {self.max}"

        return CheckResult(
            check_name=self.check_name,
            table=self.table,
            column=self.column,
            passed=passed,
            failed_count=failed,
            total_count=total,
            error_message=None if passed else f"{failed} values out of range {range_str}"
        )