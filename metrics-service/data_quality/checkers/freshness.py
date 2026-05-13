"""
FreshnessChecker — 检查数据是否在指定时间窗口内更新过

YAML 配置示例:
  - type: freshness
    table: shopify_orders
    column: _fivetran_synced
    max_age_hours: 24    # 最新一条记录不能超过 24 小时前
"""

import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Optional
from data_quality.checkers.base import BaseChecker, CheckResult


class FreshnessChecker(BaseChecker):
    """
    检查指定时间字段的最大值,与当前时间相比,是否在 max_age_hours 之内。
    
    用于检测 pipeline 是否在按时跑(stale data detection)。
    """

    def __init__(
        self,
        table: str,
        column: str,
        max_age_hours: float,
        **kwargs
    ):
        """
        Args:
            column: 时间戳字段(比如 _fivetran_synced, created_at)
            max_age_hours: 最大允许年龄(小时),超过则不通过
        """
        super().__init__(table=table, column=column, **kwargs)
        self.max_age_hours = max_age_hours

    def check(self, df: pd.DataFrame) -> CheckResult:
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

        total = len(df)

        if total == 0:
            return CheckResult(
                check_name=self.check_name,
                table=self.table,
                column=self.column,
                passed=False,
                failed_count=0,
                total_count=0,
                error_message="Table is empty, cannot check freshness"
            )

        # 转换成 datetime,确保兼容字符串/datetime/timestamp 类型
        try:
            ts_series = pd.to_datetime(df[self.column], errors="coerce", utc=True)
        except Exception as e:
            return CheckResult(
                check_name=self.check_name,
                table=self.table,
                column=self.column,
                passed=False,
                failed_count=0,
                total_count=total,
                error_message=f"Failed to parse timestamp column: {e}"
            )

        latest = ts_series.max()
        if pd.isna(latest):
            return CheckResult(
                check_name=self.check_name,
                table=self.table,
                column=self.column,
                passed=False,
                failed_count=0,
                total_count=total,
                error_message="No valid timestamps found"
            )

        now = datetime.now(timezone.utc)
        age = now - latest.to_pydatetime()
        age_hours = age.total_seconds() / 3600
        passed = age_hours <= self.max_age_hours

        return CheckResult(
            check_name=self.check_name,
            table=self.table,
            column=self.column,
            passed=passed,
            failed_count=0 if passed else 1,  # freshness 是 table-level,不计行
            total_count=total,
            error_message=(
                None if passed
                else f"Data is {age_hours:.1f}h old (max allowed: {self.max_age_hours}h)"
            )
        )