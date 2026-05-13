"""
快速验证 3 个新 checker(unique / range / freshness)
直接 python data_quality/tests/test_all_checkers.py 即可
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd
from datetime import datetime, timedelta, timezone
from data_quality.checkers.unique import UniqueChecker
from data_quality.checkers.range import RangeChecker
from data_quality.checkers.freshness import FreshnessChecker


# ==========================================
# UniqueChecker 测试
# ==========================================
def test_unique_pass():
    df = pd.DataFrame({"order_id": [1, 2, 3, 4, 5]})
    result = UniqueChecker(table="orders", column="order_id").check(df)
    print(result)
    assert result.passed


def test_unique_fail():
    df = pd.DataFrame({"order_id": [1, 2, 2, 3, 3]})
    result = UniqueChecker(table="orders", column="order_id").check(df)
    print(result)
    assert not result.passed
    assert result.failed_count == 4  # 2 个 dup of 2, 2 个 dup of 3


def test_unique_multi_column():
    """复合主键场景"""
    df = pd.DataFrame({
        "order_id":    [1, 1, 1, 2],
        "line_number": [1, 2, 2, 1],  # (1, 2) 重复
    })
    result = UniqueChecker(table="lines", columns=["order_id", "line_number"]).check(df)
    print(result)
    assert not result.passed


# ==========================================
# RangeChecker 测试
# ==========================================
def test_range_pass():
    df = pd.DataFrame({"price": [10, 20, 30, 40, 50]})
    result = RangeChecker(table="orders", column="price", min=0, max=100).check(df)
    print(result)
    assert result.passed


def test_range_fail():
    df = pd.DataFrame({"price": [-5, 20, 30, 999999, 50]})
    result = RangeChecker(table="orders", column="price", min=0, max=100).check(df)
    print(result)
    assert not result.passed
    assert result.failed_count == 2  # -5 和 999999


def test_range_only_min():
    """只设下界,不设上界"""
    df = pd.DataFrame({"price": [-1, 0, 100, 999999]})
    result = RangeChecker(table="orders", column="price", min=0).check(df)
    print(result)
    assert not result.passed
    assert result.failed_count == 1  # 只有 -1 不通过


# ==========================================
# FreshnessChecker 测试
# ==========================================
def test_freshness_pass():
    """最新数据是 1 小时前,允许 24 小时,应通过"""
    now = datetime.now(timezone.utc)
    df = pd.DataFrame({
        "synced_at": [
            now - timedelta(hours=10),
            now - timedelta(hours=5),
            now - timedelta(hours=1),  # 最新
        ]
    })
    result = FreshnessChecker(
        table="orders", column="synced_at", max_age_hours=24
    ).check(df)
    print(result)
    assert result.passed


def test_freshness_fail():
    """最新数据是 48 小时前,允许 24 小时,不通过"""
    now = datetime.now(timezone.utc)
    df = pd.DataFrame({
        "synced_at": [
            now - timedelta(hours=72),
            now - timedelta(hours=48),  # 最新但太旧
        ]
    })
    result = FreshnessChecker(
        table="orders", column="synced_at", max_age_hours=24
    ).check(df)
    print(result)
    assert not result.passed


if __name__ == "__main__":
    tests = [
        ("Unique PASS", test_unique_pass),
        ("Unique FAIL", test_unique_fail),
        ("Unique multi-column FAIL", test_unique_multi_column),
        ("Range PASS", test_range_pass),
        ("Range FAIL", test_range_fail),
        ("Range only-min FAIL", test_range_only_min),
        ("Freshness PASS", test_freshness_pass),
        ("Freshness FAIL", test_freshness_fail),
    ]
    for name, fn in tests:
        print("=" * 60)
        print(f"Test: {name}")
        print("=" * 60)
        fn()
        print()

    print("🎉 All 8 tests passed!")