from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage

from contract_review_agent.graph import build_contract_review_graph
from contract_review_agent.json_utils import extract_json_payload, to_pretty_json
from contract_review_agent.llm import ProviderSettings
from contract_review_agent.tools.report import build_quality_report_tool


def _extract_latest_structured_result(messages: list[Any]) -> dict[str, Any]:
    """Prefer the latest valid tool JSON when the agent's final JSON is malformed."""
    last_error: Exception | None = None
    markdown_only_payload: dict[str, Any] | None = None
    for message in reversed(messages):
        content = getattr(message, "content", "")
        if not isinstance(content, str) or not content.strip():
            continue
        try:
            payload = extract_json_payload(content)
        except Exception as exc:
            last_error = exc
            continue
        if isinstance(payload, dict) and "review_report" in payload:
            return payload
        if isinstance(payload, dict) and markdown_only_payload is None and "report_markdown" in payload:
            markdown_only_payload = payload
    if markdown_only_payload is not None:
        return markdown_only_payload
    if last_error is not None:
        raise last_error
    raise ValueError("No structured review JSON found in agent messages.")


def build_user_prompt(procurement_file: str, contract_file: str) -> str:
    return f"""请你审核两份合同/采购相关文件，并自主调用工具完成工作。

采购文件路径: {Path(procurement_file).resolve()}
合同草案路径: {Path(contract_file).resolve()}

要求：
1. 如果源文件不是 markdown，请先转成 markdown
2. 再进行逐条条款比对
3. 对疑似差异项做语义级深分析
4. 生成结构化JSON审核结果，并补充质检报告 markdown
"""


def run_contract_review(
    settings: ProviderSettings,
    procurement_file: str,
    contract_file: str,
    report_output_dir: str | None = None,
) -> dict[str, Any]:
    graph = build_contract_review_graph(settings)
    result = graph.invoke(
        {
            "messages": [
                HumanMessage(
                    content=build_user_prompt(
                        procurement_file=procurement_file,
                        contract_file=contract_file,
                    )
                )
            ]
        }
    )
    final_message = result["messages"][-1].content
    try:
        final_json = extract_json_payload(final_message)
    except Exception:
        final_json = _extract_latest_structured_result(result["messages"])

    if isinstance(final_json, dict) and "report_markdown" not in final_json:
        report_tool = build_quality_report_tool()
        report_payload = report_tool.invoke(
            {
                "review_payload_json": to_pretty_json(final_json),
                "title": "合同质检报告",
            }
        )
        report_json = extract_json_payload(report_payload)
        if isinstance(report_json, dict):
            final_json["report_markdown"] = report_json.get("report_markdown", "")
            final_json["report_stats"] = report_json.get("report_stats", {})

    report_dir = (
        Path(report_output_dir).resolve()
        if report_output_dir
        else Path.cwd() / "contract_review_report"
    )
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = report_dir / f"review_{timestamp}.json"
    markdown_path = report_dir / f"review_{timestamp}.md"
    json_path.write_text(to_pretty_json(final_json), encoding="utf-8")
    report_markdown = ""
    if isinstance(final_json, dict):
        report_markdown = str(final_json.get("report_markdown", ""))
    markdown_path.write_text(report_markdown, encoding="utf-8")

    return {
        "final_message": final_message,
        "final_json": final_json,
        "saved_json_path": str(json_path),
        "saved_markdown_path": str(markdown_path),
    }
