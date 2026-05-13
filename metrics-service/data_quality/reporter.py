"""
Reporter — 把 CheckResult 列表输出成人看的报告

支持两种格式:
  1. console (文本表格,默认)
  2. json (机器可读,给下游用)
"""

import json
from typing import List, Dict, Any
from data_quality.checkers.base import CheckResult


def _to_json_safe(obj: Any) -> Any:
    """
    把 numpy/pandas 的特殊类型(np.bool_, np.int64 等)转成 Python 原生类型
    防止 json.dumps 报 'Object of type X is not JSON serializable'
    """
    # numpy bool → Python bool
    if hasattr(obj, "__bool__") and obj.__class__.__name__ in ("bool_", "bool8"):
        return bool(obj)
    # numpy int → Python int
    if hasattr(obj, "__int__") and "int" in obj.__class__.__name__.lower() and obj.__class__.__name__ != "int":
        return int(obj)
    # numpy float → Python float
    if hasattr(obj, "__float__") and "float" in obj.__class__.__name__.lower() and obj.__class__.__name__ != "float":
        return float(obj)
    return obj


class Reporter:
    """质量报告生成器"""

    @staticmethod
    def to_console(results: List[CheckResult]) -> str:
        """生成可在终端打印的人类可读报告"""
        if not results:
            return "No checks were run."

        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        pass_rate = (passed / total * 100) if total > 0 else 0

        lines = []
        lines.append("=" * 70)
        lines.append("DATA QUALITY REPORT")
        lines.append("=" * 70)
        lines.append(f"Total Checks:  {total}")
        lines.append(f"Passed:        {passed}")
        lines.append(f"Failed:        {failed}")
        lines.append(f"Pass Rate:     {pass_rate:.1f}%")
        lines.append("-" * 70)

        # 按 table 分组展示
        by_table: Dict[str, List[CheckResult]] = {}
        for r in results:
            by_table.setdefault(r.table, []).append(r)

        for table, table_results in by_table.items():
            lines.append(f"\n📋 Table: {table}")
            for r in table_results:
                status = "✅ PASS" if r.passed else "❌ FAIL"
                col_part = f".{r.column}" if r.column else ""
                line = f"  {status} [{r.check_name}]{col_part}"
                if not r.passed and r.error_message:
                    line += f"  →  {r.error_message}"
                lines.append(line)

        lines.append("\n" + "=" * 70)
        if failed == 0:
            lines.append("🎉 All data quality checks passed!")
        else:
            lines.append(f"⚠️  {failed} check(s) failed. Review above.")
        lines.append("=" * 70)

        return "\n".join(lines)

    @staticmethod
    def to_json(results: List[CheckResult]) -> str:
        """生成机器可读的 JSON 报告(供 pipeline 集成)"""
        payload = {
            "summary": {
                "total":   len(results),
                "passed":  sum(1 for r in results if r.passed),
                "failed":  sum(1 for r in results if not r.passed),
            },
            "results": [
                {
                    "check_name":    r.check_name,
                    "table":         r.table,
                    "column":        r.column,
                    "passed":        _to_json_safe(r.passed),
                    "failed_count":  _to_json_safe(r.failed_count),
                    "total_count":   _to_json_safe(r.total_count),
                    "error_message": r.error_message,
                }
                for r in results
            ]
        }
        return json.dumps(payload, indent=2, ensure_ascii=False)