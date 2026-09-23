from __future__ import annotations

import json
import os
import importlib.util
from pathlib import Path

from huggingface_hub import hf_hub_download


REPO_ID = "opendatalab/PDF-Extract-Kit-1.0"
ROOT_DIR = Path(__file__).resolve().parent
MODELS_ROOT = ROOT_DIR / "mineru_models"
MODELS_DIR = MODELS_ROOT / "models"
CONFIG_PATH = ROOT_DIR / "magic-pdf.json"
LAYOUTREADER_DIR = ROOT_DIR / "layoutreader"
REQUIRED_FILES = [
    "models/Layout/YOLO/doclayout_yolo_docstructbench_imgsz1280_2501.pt",
    "models/OCR/paddleocr_torch/ch_PP-OCRv5_det_infer.pth",
    "models/OCR/paddleocr_torch/ch_PP-OCRv5_rec_infer.pth",
]
LAYOUTREADER_FILES = [
    "config.json",
    "model.safetensors",
]
def download_required_files() -> None:
    MODELS_ROOT.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

    for relative_path in REQUIRED_FILES:
        downloaded_path = hf_hub_download(
            repo_id=REPO_ID,
            filename=relative_path,
            local_dir=str(MODELS_ROOT),
            local_dir_use_symlinks=False,
        )
        print(f"downloaded={downloaded_path}")

    LAYOUTREADER_DIR.mkdir(parents=True, exist_ok=True)
    for relative_path in LAYOUTREADER_FILES:
        downloaded_path = hf_hub_download(
            repo_id="hantian/layoutreader",
            filename=relative_path,
            repo_type="model",
            local_dir=str(LAYOUTREADER_DIR),
            local_dir_use_symlinks=False,
        )
        print(f"downloaded={downloaded_path}")


def write_config() -> None:
    config = {
        "models-dir": str(MODELS_DIR.resolve()),
        "device-mode": "cpu",
        "layoutreader-model-dir": str(LAYOUTREADER_DIR.resolve()),
        "layout-config": {
            "model": "doclayout_yolo",
        },
        "formula-config": {
            "mfd_model": "yolo_v8_mfd",
            "mfr_model": "unimernet_small",
            "enable": False,
        },
        "table-config": {
            "model": "rapid_table",
            "sub_model": "slanet_plus",
            "enable": True,
            "max_time": 400,
        },
        "latex-delimiter-config": None,
    }
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"config={CONFIG_PATH.resolve()}")


def patch_ocr_model_map() -> None:
    package = importlib.util.find_spec("magic_pdf")
    if package is None or not package.submodule_search_locations:
        raise RuntimeError("MinerU is not installed. Install requirements first.")
    package_dir = Path(next(iter(package.submodule_search_locations)))
    ocr_models_config = (
        package_dir / "model" / "sub_modules" / "ocr" /
        "paddleocr2pytorch" / "pytorchocr" / "utils" /
        "resources" / "models_config.yml"
    )
    if not ocr_models_config.is_file():
        raise RuntimeError(f"MinerU OCR configuration not found: {ocr_models_config}")
    original = ocr_models_config.read_text(encoding="utf-8")
    patched = original.replace(
        "det: ch_PP-OCRv3_det_infer.pth",
        "det: ch_PP-OCRv5_det_infer.pth",
    )
    if patched == original and "det: ch_PP-OCRv5_det_infer.pth" not in original:
        raise RuntimeError("Unsupported MinerU OCR configuration; expected v3/v5 model mapping.")
    if patched != original:
        ocr_models_config.write_text(patched, encoding="utf-8")
    print(f"ocr_config={ocr_models_config.resolve()}")


def main() -> None:
    download_required_files()
    patch_ocr_model_map()
    write_config()


if __name__ == "__main__":
    main()
