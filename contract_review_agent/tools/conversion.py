from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from contract_review_agent.json_utils import to_pretty_json
from contract_review_agent.prompt_loader import read_text_with_fallback
def build_convert_to_markdown_tool():
    @tool("convert_contract_to_markdown")
    def convert_contract_to_markdown(
        file_path: str,
        parse_method: str = "auto",
        lang: str | None = None,
    ) -> str:
        """Convert a local PDF or DOCX contract file to markdown under the project output_md directory."""
        from mineru_markdown_converter import (
            DEFAULT_OUTPUT_DIR,
            PDF_SUFFIXES,
            convert_office_with_mineru_or_fallback,
            convert_pdf_with_mineru,
            ensure_input_supported,
        )

        source_path = Path(file_path).resolve()
        ensure_input_supported(source_path)

        suffix = source_path.suffix.lower()
        target_dir = DEFAULT_OUTPUT_DIR.resolve()
        target_dir.mkdir(parents=True, exist_ok=True)

        if suffix in PDF_SUFFIXES:
            markdown_path = convert_pdf_with_mineru(
                source_path,
                target_dir,
                parse_method,
                lang,
            )
            engine = "mineru"
        else:
            markdown_path, engine = convert_office_with_mineru_or_fallback(
                source_path,
                target_dir,
                parse_method,
                lang,
            )

        markdown_text = read_text_with_fallback(markdown_path)
        return to_pretty_json(
            {
                "source_path": str(source_path),
                "markdown_path": str(markdown_path.resolve()),
                "engine": engine,
                "markdown_preview": markdown_text[:1000],
                "markdown_char_count": len(markdown_text),
            }
        )

    return convert_contract_to_markdown
