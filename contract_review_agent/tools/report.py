from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

from contract_review_agent.json_utils import extract_json_payload, to_pretty_json


def _as_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def build_quality_report_tool():
    @tool("generate_quality_report")
    def generate_quality_report(
        review_payload_json: str,
        title: str = "合同质检报告",
    ) -> str:
        """Generate a readable markdown quality report from review JSON payload."""
        payload = extract_json_payload(review_payload_json)
        review_report = payload.get("review_report", payload)

        summary = str(review_report.get("review_summary", "")).strip()
        missing_items = _as_list(review_report.get("missing_items"))
        discrepancies = _as_list(review_report.get("discrepancies"))
        consistent_items = _as_list(review_report.get("consistent_items"))

        lines = [f"# {title}", ""]
        lines.append("## 总结")
        lines.append(summary if summary else "未提供总结。")
        lines.append("")

        def append_section(name: str, items: list[dict[str, Any]]) -> None:
            lines.append(f"## {name}（{len(items)}）")
            if not items:
                lines.append("- 无")
                lines.append("")
                return
            for idx, item in enumerate(items, start=1):
                dimension = item.get("dimension", "unknown")
                sub_dimension = item.get("sub_dimension", "unknown")
                risk_level = item.get("risk_level", "n/a")
                analysis = item.get("analysis", "")
                procurement_quote = item.get("procurement_quote", "")
                contract_quote = item.get("contract_quote", "")

                lines.append(f"### {idx}. {dimension} / {sub_dimension}")
                lines.append(f"- 风险等级: {risk_level}")
                if procurement_quote:
                    lines.append(f"- 采购文件: {procurement_quote}")
                if contract_quote:
                    lines.append(f"- 合同草案: {contract_quote}")
                if analysis:
                    lines.append(f"- 分析: {analysis}")
                lines.append("")

        append_section("缺失项", missing_items)
        append_section("差异项", discrepancies)
        append_section("一致项", consistent_items)

        return to_pretty_json(
            {
                "title": title,
                "report_markdown": "\n".join(lines).strip() + "\n",
                "report_stats": {
                    "missing_items": len(missing_items),
                    "discrepancies": len(discrepancies),
                    "consistent_items": len(consistent_items),
                },
            }
        )

    return generate_quality_report
