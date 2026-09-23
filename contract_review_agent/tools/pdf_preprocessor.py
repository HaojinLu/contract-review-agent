from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import fitz


_WATERMARK_MIN_RGB = 200
_WATERMARK_MAX_OPACITY = 0.35

_WATERMARK_FRAGMENT_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\d{2,4}[-:]\d{2}[-:]\d{2}[:.]?\d*$"),
    re.compile(r"^/\d{5,}$"),
    re.compile(r"^Q\d{3,}$"),
]


def _color_is_watermark_like(color: float | tuple | list | None) -> bool:
    """Return True only if the color strongly indicates a watermark (very light gray or low opacity)."""
    if color is None:
        return False
    if isinstance(color, (int, float)):
        return max(0, min(1, color)) >= _WATERMARK_MIN_RGB / 255.0
    rgb = [c for c in color]
    if len(rgb) == 4 and 0.0 < rgb[3] <= _WATERMARK_MAX_OPACITY:
        return True
    if len(rgb) >= 3:
        if all(c >= _WATERMARK_MIN_RGB / 255.0 for c in rgb[:3]):
            return True
    return False


def _text_matches_watermark_pattern(text: str) -> bool:
    """Check if text matches known watermark fragment patterns."""
    stripped = text.strip()
    if not stripped:
        return False
    for pattern in _WATERMARK_FRAGMENT_PATTERNS:
        if pattern.search(stripped):
            return True
    return False


def _collect_watermark_spans(page: fitz.Page) -> list[dict[str, Any]]:
    """Collect spans that are very likely watermarks based on color AND content.

    Uses conservative detection: requires BOTH light color AND watermark-like text pattern,
    OR very low opacity text.
    """
    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

    candidates: list[dict[str, Any]] = []
    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if not text:
                    continue

                color = span.get("color")
                bbox = span.get("bbox")
                if bbox is None:
                    continue

                is_light = _color_is_watermark_like(color)
                matches_pattern = _text_matches_watermark_pattern(text)

                # Require BOTH light color AND watermark-like pattern
                # OR very low opacity (regardless of pattern)
                should_remove = False
                if is_light and matches_pattern:
                    should_remove = True
                elif (
                    isinstance(color, (list, tuple))
                    and len(color) == 4
                    and 0 < color[3] <= _WATERMARK_MAX_OPACITY
                ):
                    should_remove = True

                if should_remove:
                    candidates.append(
                        {
                            "bbox": list(bbox),
                            "text": text,
                            "color": color,
                        }
                    )
    return candidates


def remove_watermarks_from_pdf(
    input_pdf: Path,
    output_pdf: Path | None = None,
) -> Path:
    """Detect and remove watermark text from a PDF file.

    Only removes text that is BOTH light-colored AND matches known watermark patterns.
    """
    input_pdf = input_pdf.resolve()
    if output_pdf is None:
        output_pdf = input_pdf.parent / f"{input_pdf.stem}_clean{input_pdf.suffix}"
    output_pdf = Path(output_pdf).resolve()

    doc = fitz.open(str(input_pdf))
    total_redacted = 0

    for page_num in range(len(doc)):
        page = doc[page_num]
        spans = _collect_watermark_spans(page)
        if not spans:
            continue

        for span_info in spans:
            rect = fitz.Rect(span_info["bbox"])
            page.add_redact_annot(rect, fill=(1, 1, 1))
            total_redacted += 1

        page.apply_redactions()

    if total_redacted > 0:
        doc.save(str(output_pdf))
    doc.close()

    return output_pdf


def preprocess_pdf(input_pdf: Path, output_dir: Path | None = None) -> Path:
    """Preprocessing pipeline for contract PDF files.

    Currently a pass-through since watermarks in contract PDFs are typically
    embedded as images (not text), and are handled by OCR noise cleaning instead.

    Returns original path unchanged.
    """
    return input_pdf.resolve()
