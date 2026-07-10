"""
BaseChecker — 所有 data quality checker 的抽象基类

设计原则:
- 每个 checker(not_null / unique / range / freshness)继承这个类
- 强制实现 check() 方法,统一接口
- 返回标准化的 CheckResult,便于 runner 收集报告
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import pandas as pd


@dataclass
class CheckResult:
    """统一的 check 结果格式,所有 checker 都返回这个"""
    check_name: str          # 检查名,比如 "not_null"
    table: str               # 检查的表,比如 "shopify_orders"
    column: Optional[str]    # 检查的字段,比如 "order_id"(有些 check 不针对单字段,所以可空)
    passed: bool             # 通过 or 不通过
    failed_count: int        # 失败的行数(通过时为 0)
    total_count: int         # 总行数
    error_message: Optional[str] = None  # 失败时的描述信息

    def __str__(self):
        status = "✅ PASS" if self.passed else "❌ FAIL"
        col_part = f".{self.column}" if self.column else ""
        return (f"{status} [{self.check_name}] {self.table}{col_part} "
                f"({self.failed_count}/{self.total_count} failed)")


class BaseChecker(ABC):
    """
    所有 checker 的基类。
    每个具体 checker(not_null / unique / range / freshness)继承这个,实现 check()。
    """

    def __init__(self, table: str, column: Optional[str] = None, **kwargs):
        """
        Args:
            table: 要检查的表名(比如 "shopify_orders")
            column: 要检查的字段名(有些 check 不针对单字段,可不传)
            **kwargs: 子类需要的额外参数(比如 range 需要 min/max)
        """
        self.table = table
        self.column = column
        self.params = kwargs  # 子类自己从 params 里取需要的参数

    @abstractmethod
    def check(self, df: pd.DataFrame) -> CheckResult:
        """
        执行检查。子类必须实现。
        
        Args:
            df: 要检查的数据(本期用 pandas DataFrame mock,后期切到 Spark DataFrame)
        
        Returns:
            CheckResult: 检查结果
        """
        pass

    @property
    def check_name(self) -> str:
        """返回 checker 类型名,比如 'not_null'。子类可覆盖。"""
        return self.__class__.__name__.replace("Checker", "").lower()