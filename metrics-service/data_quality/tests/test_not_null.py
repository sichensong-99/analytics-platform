"""
快速验证 NotNullChecker 是否跑得通
直接 python data_quality/tests/test_not_null.py 即可
"""

import sys
import os

# 把 metrics-service 加入 import path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd
from data_quality.checkers.not_null import NotNullChecker


def test_not_null_pass():
    """场景 1:所有值都不是 null,应该通过"""
    df = pd.DataFrame({
        "order_id": [1, 2, 3, 4, 5],
        "amount":   [10.0, 20.0, 30.0, 40.0, 50.0],
    })

    checker = NotNullChecker(table="orders", column="order_id")
    result = checker.check(df)

    print(result)
    assert result.passed, "Expected PASS, but got FAIL"
    assert result.failed_count == 0


def test_not_null_fail():
    """场景 2:有 null 值,应该不通过"""
    df = pd.DataFrame({
        "order_id": [1, 2, None, 4, None],
        "amount":   [10.0, 20.0, 30.0, 40.0, 50.0],
    })

    checker = NotNullChecker(table="orders", column="order_id")
    result = checker.check(df)

    print(result)
    assert not result.passed, "Expected FAIL, but got PASS"
    assert result.failed_count == 2


def test_column_not_found():
    """场景 3:指定的字段不存在,应该返回错误信息"""
    df = pd.DataFrame({
        "order_id": [1, 2, 3],
    })

    checker = NotNullChecker(table="orders", column="nonexistent_field")
    result = checker.check(df)

    print(result)
    assert not result.passed
    assert "not found" in result.error_message


if __name__ == "__main__":
    print("=" * 60)
    print("Test 1: not_null check on clean data (should PASS)")
    print("=" * 60)
    test_not_null_pass()
    print()

    print("=" * 60)
    print("Test 2: not_null check on dirty data (should FAIL)")
    print("=" * 60)
    test_not_null_fail()
    print()

    print("=" * 60)
    print("Test 3: column not found (should FAIL gracefully)")
    print("=" * 60)
    test_column_not_found()
    print()

    print("🎉 All tests passed!")