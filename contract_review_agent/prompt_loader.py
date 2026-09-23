from __future__ import annotations

from pathlib import Path


def read_text_with_fallback(path: str | Path) -> str:
    file_path = Path(path)
    encodings = ("utf-8", "utf-8-sig", "gb18030", "gbk")
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            return file_path.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return file_path.read_text()
