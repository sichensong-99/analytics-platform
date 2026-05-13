"""
端到端测试:验证整套 DQ 框架(YAML → Runner → Checker → Report)
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd
from datetime import datetime, timedelta, timezone
from data_quality.runner import DQRunner
from data_quality.reporter import Reporter


def make_mock_shopify_orders(dirty: bool = False) -> pd.DataFrame:
    """造一个 mock Shopify orders 数据"""
    now = datetime.now(timezone.utc)
    base = pd.DataFrame({
        "order_id":         [1001, 1002, 1003, 1004, 1005],
        "created_at":       [now - timedelta(days=i) for i in range(5)],
        "total_price":      [49.99, 120.00, 75.50, 230.00, 19.99],
        "_fivetran_synced": [now - timedelta(hours=1)] * 5,
    })

    if dirty:
        # 制造一些问题:order_id 有重复,total_price 有负数,有 null
        base.loc[5] = [1003, now, -50, now]  # 重复 ID + 负价格
        base.loc[6] = [None, now, 80, now]  # null ID

    return base


def make_mock_tw_attribution() -> pd.DataFrame:
    """造一个 mock TW attribution 数据"""
    now = datetime.now(timezone.utc)
    return pd.DataFrame({
        "_triple_whale_order_id": ["7137654571097", "7137653850201", "7137650999385"],
        "total_price":            [71.59, 32.95, 32.07],
        "_synced_at":             [now - timedelta(hours=2)] * 3,
    })


def test_clean_data():
    """场景 1:干净数据,所有检查应该通过"""
    print("\n" + "=" * 70)
    print("Scenario 1: Clean Shopify Data (expect ALL PASS)")
    print("=" * 70)

    runner = DQRunner.from_yaml(
        "data_quality/configs/shopify_orders.yaml"
    )

    dataframes = {
        "shopify_orders": make_mock_shopify_orders(dirty=False),
    }
    results = runner.run(dataframes)
    report = Reporter.to_console(results)
    print(report)

    assert all(r.passed for r in results), "Expected all checks to pass"


def test_dirty_data():
    """场景 2:脏数据,应该有检查失败"""
    print("\n" + "=" * 70)
    print("Scenario 2: Dirty Shopify Data (expect some FAIL)")
    print("=" * 70)

    runner = DQRunner.from_yaml(
        "data_quality/configs/shopify_orders.yaml"
    )

    dataframes = {
        "shopify_orders": make_mock_shopify_orders(dirty=True),
    }
    results = runner.run(dataframes)
    report = Reporter.to_console(results)
    print(report)

    failed = [r for r in results if not r.passed]
    assert len(failed) > 0, "Expected some checks to fail"


def test_tw_attribution():
    """场景 3:TW 数据"""
    print("\n" + "=" * 70)
    print("Scenario 3: TW Attribution Data")
    print("=" * 70)

    runner = DQRunner.from_yaml(
        "data_quality/configs/tw_attribution.yaml"
    )

    dataframes = {
        "tw_attribution_order": make_mock_tw_attribution(),
    }
    results = runner.run(dataframes)
    report = Reporter.to_console(results)
    print(report)


def test_json_output():
    """场景 4:JSON 报告"""
    print("\n" + "=" * 70)
    print("Scenario 4: JSON Report Output")
    print("=" * 70)

    runner = DQRunner.from_yaml(
        "data_quality/configs/shopify_orders.yaml"
    )
    dataframes = {"shopify_orders": make_mock_shopify_orders(dirty=True)}
    results = runner.run(dataframes)
    json_report = Reporter.to_json(results)
    print(json_report)


if __name__ == "__main__":
    test_clean_data()
    test_dirty_data()
    test_tw_attribution()
    test_json_output()
    print("\n🎉 All end-to-end tests completed!")