from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

import fitz
import mammoth
from PIL import Image


OFFICE_SUFFIXES = {".doc", ".docx", ".ppt", ".pptx"}
PDF_SUFFIXES = {".pdf"}
PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output_md"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "magic-pdf.json"
MODELS_DIR = PROJECT_ROOT / "mineru_models" / "models"
LAYOUTREADER_DIR = PROJECT_ROOT / "layoutreader"
ULTRALYTICS_CONFIG_ROOT = PROJECT_ROOT
MAX_OCR_IMAGE_COUNT = 80
MIN_OCR_IMAGE_WIDTH = 120
MIN_OCR_IMAGE_HEIGHT = 40
os.environ.setdefault("MINERU_TOOLS_CONFIG_JSON", str(DEFAULT_CONFIG_PATH))
os.environ.setdefault("YOLO_CONFIG_DIR", str(ULTRALYTICS_CONFIG_ROOT))


def _resolve_stored_path(stored: str, project_root: Path) -> str:
    """Resolve a possibly relative stored path to an absolute string."""
    path = Path(stored)
    if path.is_absolute():
        return str(path.resolve())
    return str((project_root / path).resolve())


def sync_local_mineru_config(config_path: Path = DEFAULT_CONFIG_PATH) -> Path:
    """
    Keep MinerU model paths valid after the project directory is moved.

    The JSON file stores paths as relative-to-project-root so it is portable.
    At runtime this function resolves them to absolute paths and writes them
    back so that MinerU can find the models regardless of the working directory.
    """
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            config = {}
    else:
        config = {}

    config.setdefault("device-mode", "cpu")
    config.setdefault("layout-config", {"model": "doclayout_yolo"})
    config.setdefault(
        "formula-config",
        {
            "mfd_model": "yolo_v8_mfd",
            "mfr_model": "unimernet_small",
            "enable": False,
        },
    )
    config.setdefault(
        "table-config",
        {
            "model": "rapid_table",
            "sub_model": "slanet_plus",
            "enable": False,
            "max_time": 400,
        },
    )
    config.setdefault("latex-delimiter-config", None)

    expected_models_dir = str(MODELS_DIR.resolve())
    expected_layoutreader_dir = str(LAYOUTREADER_DIR.resolve())

    stored_models_dir = _resolve_stored_path(
        config.get("models-dir", ""), PROJECT_ROOT
    )
    stored_layoutreader_dir = _resolve_stored_path(
        config.get("layoutreader-model-dir", ""), PROJECT_ROOT
    )

    changed = (
        stored_models_dir != expected_models_dir
        or stored_layoutreader_dir != expected_layoutreader_dir
    )
    config["models-dir"] = expected_models_dir
    config["layoutreader-model-dir"] = expected_layoutreader_dir

    if changed or not config_path.exists():
        config_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    os.environ["MINERU_TOOLS_CONFIG_JSON"] = str(config_path)
    return config_path


sync_local_mineru_config()

from magic_pdf.data.data_reader_writer import FileBasedDataReader
from magic_pdf.tools.common import do_parse
from magic_pdf.utils.office_to_pdf import ConvertToPdfError, convert_file_to_pdf


_OCR_ENGINE = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Use MinerU to convert PDF/DOCX files into Markdown."
    )
    parser.add_argument(
        "input_path",
        type=Path,
        help="Path to a .pdf or .docx file.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory used to store markdown output.",
    )
    parser.add_argument(
        "-m",
        "--method",
        choices=("auto", "ocr", "txt"),
        default="auto",
        help="MinerU parse mode for PDF inputs.",
    )
    parser.add_argument(
        "--lang",
        default=None,
        help="Optional OCR language hint passed to MinerU.",
    )
    return parser.parse_args()


def ensure_input_supported(input_path: Path) -> None:
    if not input_path.exists():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")
    if input_path.suffix.lower() not in PDF_SUFFIXES | OFFICE_SUFFIXES:
        raise ValueError("Only .pdf, .doc, .docx, .ppt, and .pptx are supported.")


def ensure_local_mineru_config(config_path: Path = DEFAULT_CONFIG_PATH) -> Path:
    sync_local_mineru_config(config_path)
    if not config_path.exists():
        raise FileNotFoundError(
            "MinerU config is missing. Run bootstrap_mineru.py first to download "
            f"the required models and create {config_path.name}."
        )

    os.environ["MINERU_TOOLS_CONFIG_JSON"] = str(config_path)
    return config_path


def read_local_pdf(pdf_path: Path) -> bytes:
    reader = FileBasedDataReader(str(pdf_path.parent))
    return reader.read(pdf_path.name)


def copy_markdown_to_flat_output(output_dir: Path, stem: str, method: str) -> Path:
    nested_md = output_dir / stem / method / f"{stem}.md"
    if not nested_md.exists():
        raise FileNotFoundError(f"MinerU markdown output not found: {nested_md}")

    flat_md = output_dir / f"{stem}.md"
    flat_md.write_text(nested_md.read_text(encoding="utf-8"), encoding="utf-8")
    return flat_md


def _collect_table_hints_from_content_list(content_list_path: Path) -> list[str]:
    if not content_list_path.exists():
        return []
    try:
        payload = json.loads(content_list_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    hints: list[str] = []
    if not isinstance(payload, list):
        return hints
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            continue
        if item.get("type") != "table":
            continue
        page_idx = item.get("page_idx")
        caption = item.get("table_caption") or []
        footnote = item.get("table_footnote") or []
        caption_text = "；".join(str(text).strip() for text in caption if str(text).strip())
        footnote_text = "；".join(str(text).strip() for text in footnote if str(text).strip())
        parts = [f"表格{index}"]
        if page_idx is not None:
            parts.append(f"页码={page_idx}")
        if caption_text:
            parts.append(f"标题={caption_text}")
        if footnote_text:
            parts.append(f"注释={footnote_text}")
        hints.append("，".join(parts))
    return hints


def _extract_text_fragments(value) -> list[str]:
    fragments: list[str] = []
    if isinstance(value, str):
        text = value.strip()
        if text:
            fragments.append(text)
    elif isinstance(value, list):
        for item in value:
            fragments.extend(_extract_text_fragments(item))
    elif isinstance(value, dict):
        for key in (
            "text",
            "content",
            "table_body",
            "table_caption",
            "table_footnote",
            "img_caption",
            "img_footnote",
        ):
            if key in value:
                fragments.extend(_extract_text_fragments(value[key]))
    return fragments


def _collect_visual_text_from_content_list(content_list_path: Path) -> list[str]:
    if not content_list_path.exists():
        return []
    try:
        payload = json.loads(content_list_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []

    visual_texts: list[str] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type not in {"image", "table"}:
            continue
        fragments = _extract_text_fragments(item)
        if not fragments:
            continue
        page_idx = item.get("page_idx")
        prefix = f"{item_type}{index}"
        if page_idx is not None:
            prefix += f"（页码={page_idx}）"
        visual_texts.append(f"{prefix}: " + "\n".join(dict.fromkeys(fragments)))
    return visual_texts


def _resolve_image_ref(output_dir: Path, stem: str, method: str, ref: str) -> Path | None:
    ref_path = Path(ref)
    candidates = []
    if ref_path.is_absolute():
        candidates.append(ref_path)
    candidates.extend(
        [
            output_dir / ref,
            output_dir / stem / method / ref,
            output_dir / stem / method / "images" / ref_path.name,
            output_dir / stem / method / ref_path.name,
            output_dir / ref_path.name,
        ]
    )
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _unique_asset_path(asset_dir: Path, source_path: Path) -> Path:
    target_path = asset_dir / source_path.name
    if not target_path.exists():
        return target_path
    for index in range(2, 10000):
        candidate = asset_dir / f"{source_path.stem}_{index}{source_path.suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Unable to create unique asset name for {source_path.name}")


def _materialize_markdown_images(
    markdown_text: str,
    output_dir: Path,
    stem: str,
    method: str,
    image_refs: list[str],
) -> tuple[str, dict[str, Path]]:
    asset_dir = output_dir / f"{stem}_assets"
    copied_images: dict[str, Path] = {}
    replacements: dict[str, str] = {}

    for ref in image_refs:
        if ref in replacements:
            continue
        source_path = _resolve_image_ref(output_dir, stem, method, ref)
        if source_path is None:
            continue

        asset_dir.mkdir(parents=True, exist_ok=True)
        target_path = asset_dir / source_path.name
        if source_path.resolve() != target_path.resolve():
            target_path = _unique_asset_path(asset_dir, source_path)
            shutil.copy2(source_path, target_path)

        relative_ref = target_path.relative_to(output_dir).as_posix()
        replacements[ref] = relative_ref
        copied_images[ref] = target_path

    for original_ref, new_ref in replacements.items():
        markdown_text = markdown_text.replace(f"]({original_ref})", f"]({new_ref})")

    return markdown_text, copied_images


def _missing_image_refs(
    output_dir: Path,
    stem: str,
    method: str,
    image_refs: list[str],
    image_paths_by_ref: dict[str, Path],
) -> list[str]:
    missing: list[str] = []
    for ref in image_refs:
        if ref in image_paths_by_ref:
            continue
        if _resolve_image_ref(output_dir, stem, method, ref) is None:
            missing.append(ref)
    return missing


def _get_ocr_engine(lang: str | None = None):
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        from magic_pdf.model.sub_modules.ocr.paddleocr2pytorch.pytorch_paddle import (
            PytorchPaddleOCR,
        )

        _OCR_ENGINE = PytorchPaddleOCR(lang=lang or "ch")
    return _OCR_ENGINE


def _ocr_image_text(image_path: Path, lang: str | None = None) -> str:
    try:
        ocr = _get_ocr_engine(lang)
        result = ocr.ocr(image_path.read_bytes(), det=True, rec=True)
    except Exception as exc:
        return f"OCR失败: {exc}"

    lines: list[str] = []
    for page_result in result or []:
        for item in page_result or []:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            recognition = item[1]
            if isinstance(recognition, (list, tuple)) and recognition:
                text = str(recognition[0]).strip()
                score = float(recognition[1]) if len(recognition) > 1 else 1.0
            else:
                text = str(recognition).strip()
                score = 1.0
            if text and score >= 0.35:
                lines.append(text)
    return "\n".join(lines).strip()


def _should_ocr_image(image_path: Path) -> bool:
    try:
        with Image.open(image_path) as image:
            width, height = image.size
    except Exception:
        return True
    return width >= MIN_OCR_IMAGE_WIDTH and height >= MIN_OCR_IMAGE_HEIGHT


_OCR_NOISE_PATTERNS: list[re.Pattern] = [
    # Timestamp debris: "0122:21:2220", "22:21:2", "26-02-0122"
    re.compile(r"^\d{2,4}[-:]\d{2}[-:]\d{2}[:.]?\d*$"),
    re.compile(r"^\d{1,2}:\d{2}:\d{2}$"),
    # ID fragment patterns: "/01012345", "/0101"
    re.compile(r"^/\d{5,}$"),
    re.compile(r"^/\d{4}$"),
    # Isolated control codes
    re.compile(r"^Q\d{3,}$"),
    re.compile(r"^Q\d+$"),
    # Garbled line with mixed numbers and single chars
    re.compile(r"^[\d\s]{2,}[\d\s/:.\-]*$"),
]


def _looks_like_ocr_noise_line(stripped: str) -> bool:
    """Check if a single line looks like OCR noise that should be removed."""
    if not stripped:
        return False
    has_chinese = bool(re.search(r"[一-鿿]", stripped))
    has_alpha = bool(re.search(r"[a-zA-Z]", stripped))
    has_digit = bool(re.search(r"\d", stripped))
    has_punct = bool(re.search(r"[。，；：？！、（）《》]", stripped))

    # Pure number/date/ID lines without Chinese context
    if not has_chinese and len(stripped) < 8:
        if re.fullmatch(r"[\d\s/:.\-\\]+", stripped):
            return True

    # Short Chinese fragment without sentence markers in OCR appendix
    if has_chinese and len(stripped) <= 6 and not has_punct:
        # Check against known watermark patterns
        for pattern in _OCR_NOISE_PATTERNS:
            if pattern.search(stripped):
                return True
        # Very short fragments likely noise
        if len(stripped) <= 3:
            return True

    # Check all noise patterns
    for pattern in _OCR_NOISE_PATTERNS:
        if pattern.search(stripped):
            return True

    return False


def _clean_ocr_noise(text: str) -> str:
    """Remove watermark fragments and OCR artifacts from markdown text.

    Only applies aggressive filtering within the OCR appendix section.
    The main markdown body is left largely intact.
    """
    appendix_start = text.find("## 附加说明")
    if appendix_start == -1:
        return text

    body = text[:appendix_start]
    appendix = text[appendix_start:]

    lines = appendix.split("\n")
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append(line)
            continue
        if _looks_like_ocr_noise_line(stripped):
            continue
        cleaned.append(line)

    return body + "\n" + "\n".join(cleaned)


def _extract_full_text_from_pdf(pdf_path: Path) -> str:
    """Use PyMuPDF to extract all text from each page of a PDF.

    This captures text that MinerU might have missed due to layout analysis errors.
    """
    doc = fitz.open(str(pdf_path))
    all_lines: list[str] = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")
        if text.strip():
            all_lines.append(f"\n### Page {page_num + 1}\n{text.strip()}")
    doc.close()
    return "\n".join(all_lines).strip()


def _find_missing_text(mineru_md: str, full_pdf_text: str) -> list[str]:
    """Find sentences in full_pdf_text that don't appear (even partially) in mineru_md.

    Filters out known watermark fragments, timestamps, boilerplate, and repeated
    company signatures that appear across multiple pages.
    Returns meaningful lines of text that are likely missing from MinerU output.
    """
    mineru_normalized = re.sub(r"\s+", "", mineru_md)
    seen_norm: set[str] = set()
    missing: list[str] = []
    for line in full_pdf_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if len(stripped) < 8:
            continue
        # Skip page markers
        if re.match(r"^### Page \d+$", stripped):
            continue
        # Skip purely numeric/timestamp lines
        if re.fullmatch(r"[\d\s/:.\-\\¥￥]+", stripped):
            continue
        if re.match(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", stripped):
            continue
        # Skip phone/ID fragments
        if re.fullmatch(r"[/\\]?\d{5,}", stripped):
            continue
        if re.fullmatch(r".{0,5}(/\d{5,}|20\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2}).*", stripped):
            continue
        # Skip known OCR noise patterns
        if _looks_like_ocr_noise_line(stripped):
            continue
        # Deduplicate
        norm = re.sub(r"\s+", "", stripped)
        if norm in seen_norm or norm in mineru_normalized:
            continue
        seen_norm.add(norm)
        missing.append(stripped)
        if len(missing) >= 30:
            break
    return missing


def enrich_markdown_with_visual_text(
    output_dir: Path,
    stem: str,
    method: str,
    lang: str | None = None,
    original_pdf_path: Path | None = None,
) -> None:
    flat_md_path = output_dir / f"{stem}.md"
    if not flat_md_path.exists():
        return

    markdown_text = flat_md_path.read_text(encoding="utf-8")
    appendix_marker = "\n\n## 附加说明（表格/图片 OCR 抽取）"
    if appendix_marker in markdown_text:
        markdown_text = markdown_text.split(appendix_marker, 1)[0].rstrip()
    image_refs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", markdown_text)
    markdown_text, image_paths_by_ref = _materialize_markdown_images(
        markdown_text,
        output_dir,
        stem,
        method,
        image_refs,
    )
    missing_images = _missing_image_refs(
        output_dir,
        stem,
        method,
        image_refs,
        image_paths_by_ref,
    )

    content_list_path = output_dir / stem / method / f"{stem}_content_list.json"
    table_hints = _collect_table_hints_from_content_list(content_list_path)
    visual_texts = _collect_visual_text_from_content_list(content_list_path)

    ocr_results: list[str] = []
    seen_images: set[Path] = set()
    for idx, ref in enumerate(image_refs, start=1):
        if len(ocr_results) >= MAX_OCR_IMAGE_COUNT:
            break
        image_path = image_paths_by_ref.get(ref) or _resolve_image_ref(output_dir, stem, method, ref)
        if image_path is None or image_path in seen_images:
            continue
        if not _should_ocr_image(image_path):
            continue
        seen_images.add(image_path)
        ocr_text = _ocr_image_text(image_path, lang)
        if not ocr_text:
            continue
        relative_path = image_path
        try:
            relative_path = image_path.relative_to(output_dir)
        except ValueError:
            pass
        ocr_results.append(f"图片{idx}: {relative_path}\n{ocr_text}")

    if not image_refs and not table_hints and not visual_texts and not ocr_results:
        return

    lines: list[str] = []
    lines.append("\n\n## 附加说明（表格/图片 OCR 抽取）")
    lines.append(
        "以下内容由 MinerU 中间结果与本地 OCR 自动补充，用于让后续 LLM 能读取 markdown 图片中的合同文字。"
    )
    lines.append("")
    lines.append(f"- 检测到图片引用数量: {len(image_refs)}")
    lines.append(f"- 已保存到 output_md 的图片数量: {len(image_paths_by_ref)}")
    if missing_images:
        lines.append(f"- 未找到源文件、无法 OCR 的图片数量: {len(missing_images)}")
    lines.append(f"- 检测到表格块数量: {len(table_hints)}")
    for idx, ref in enumerate(image_refs, start=1):
        lines.append(f"- 图片{idx}: {ref}")
    if table_hints:
        lines.append("")
        lines.append("### 表格元信息")
        for hint in table_hints:
            lines.append(f"- {hint}")
    if visual_texts:
        lines.append("")
        lines.append("### MinerU 中间结果中的图片/表格文本")
        for text in visual_texts:
            lines.append(f"- {text}")
    if ocr_results:
        lines.append("")
        lines.append("### 图片 OCR 文本")
        for text in ocr_results:
            lines.append("")
            lines.append(text)

    final_text = _clean_ocr_noise(
        markdown_text + "\n" + "\n".join(lines) + "\n"
    )

    # 补充 PyMuPDF 全量文本提取，补偿 MinerU 布局解析丢失的文字
    if original_pdf_path and original_pdf_path.exists():
        try:
            full_text = _extract_full_text_from_pdf(original_pdf_path)
            if full_text:
                missing_lines = _find_missing_text(final_text, full_text)
                if missing_lines:
                    final_text += (
                        "\n\n## 补充文本（PyMuPDF 全量提取）\n"
                        "以下文本来自 PDF 原始文本层，MinerU 布局解析可能遗漏。请结合此补充内容进行条款抽取。\n\n"
                        + "\n".join(missing_lines)
                        + "\n"
                    )
        except Exception:
            pass

    flat_md_path.write_text(final_text, encoding="utf-8")


def convert_pdf_with_mineru(
    pdf_path: Path,
    output_dir: Path,
    method: str,
    lang: str | None,
) -> Path:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    original_stem = pdf_path.stem
    original_pdf = pdf_path.resolve()

    # 预处理：去除 PDF 水印
    try:
        from contract_review_agent.tools.pdf_preprocessor import preprocess_pdf

        pdf_path = preprocess_pdf(pdf_path, output_dir)
    except Exception:
        pass

    pdf_bytes = read_local_pdf(pdf_path)

    do_parse(
        output_dir=str(output_dir),
        pdf_file_name=original_stem,
        pdf_bytes_or_dataset=pdf_bytes,
        model_list=[],
        parse_method=method,
        debug_able=False,
        f_draw_span_bbox=False,
        f_draw_layout_bbox=False,
        f_dump_md=True,
        f_dump_middle_json=True,
        f_dump_model_json=False,
        f_dump_orig_pdf=False,
        f_dump_content_list=True,
        start_page_id=0,
        end_page_id=None,
        lang=lang,
    )

    markdown_path = copy_markdown_to_flat_output(output_dir, original_stem, method)
    enrich_markdown_with_visual_text(
        output_dir, original_stem, method, lang,
        original_pdf_path=original_pdf,
    )
    return markdown_path


def convert_docx_with_mammoth(docx_path: Path, output_dir: Path) -> Path:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / f"{docx_path.stem}.md"
    with docx_path.open("rb") as docx_file:
        result = mammoth.convert_to_markdown(docx_file)

    markdown_path.write_text(result.value, encoding="utf-8")
    return markdown_path


def convert_office_with_mineru_or_fallback(
    office_path: Path,
    output_dir: Path,
    method: str,
    lang: str | None,
) -> tuple[Path, str]:
    temp_dir = Path(tempfile.mkdtemp(prefix="mineru_office_"))
    try:
        convert_file_to_pdf(str(office_path), str(temp_dir))
        pdf_path = temp_dir / f"{office_path.stem}.pdf"
        markdown_path = convert_pdf_with_mineru(pdf_path, output_dir, method, lang)
        return markdown_path, "mineru"
    except ConvertToPdfError:
        if office_path.suffix.lower() not in {".doc", ".docx"}:
            raise
        markdown_path = convert_docx_with_mammoth(office_path, output_dir)
        return markdown_path, "mammoth"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def main() -> None:
    args = parse_args()
    input_path = args.input_path.resolve()
    output_dir = args.output_dir.resolve()
    ensure_input_supported(input_path)
    ensure_local_mineru_config()

    suffix = input_path.suffix.lower()
    if suffix in PDF_SUFFIXES:
        markdown_path = convert_pdf_with_mineru(
            input_path, output_dir, args.method, args.lang
        )
        engine = "mineru"
    else:
        markdown_path, engine = convert_office_with_mineru_or_fallback(
            input_path, output_dir, args.method, args.lang
        )

    print(f"engine={engine}")
    print(f"markdown={markdown_path}")


if __name__ == "__main__":
    main()
