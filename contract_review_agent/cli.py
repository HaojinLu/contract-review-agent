from __future__ import annotations

import argparse
from pathlib import Path

from contract_review_agent.json_utils import to_pretty_json
from contract_review_agent.llm import ProviderSettings
from contract_review_agent.service import run_contract_review


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LangGraph-based dual contract review agent."
    )
    parser.add_argument("--provider", choices=("deepseek", "minimax", "glm"), required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--procurement-file", required=True)
    parser.add_argument("--contract-file", required=True)
    parser.add_argument("--output-file", default=None)
    parser.add_argument(
        "--report-output-dir",
        default=str(Path.cwd() / "contract_review_report"),
        help="Directory used to store generated review JSON and markdown report.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = ProviderSettings(
        provider=args.provider,
        model=args.model,
        api_key=args.api_key,
        base_url=args.base_url,
        temperature=args.temperature,
    )
    result = run_contract_review(
        settings=settings,
        procurement_file=args.procurement_file,
        contract_file=args.contract_file,
        report_output_dir=args.report_output_dir,
    )
    final_message = result["final_message"]
    print(final_message)

    if args.output_file:
        output_path = Path(args.output_file)
        output_path.write_text(to_pretty_json(result["final_json"]), encoding="utf-8")

    print(f"saved_json_path={result['saved_json_path']}")
    print(f"saved_markdown_path={result['saved_markdown_path']}")


if __name__ == "__main__":
    main()
