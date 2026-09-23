from __future__ import annotations

import json
import re
from typing import Any


def extract_json_payload(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        raise ValueError("No valid JSON payload found in model output.")

    last_error: Exception | None = None

    fenced_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", stripped, flags=re.IGNORECASE)
    for block in fenced_blocks:
        candidate = block.strip()
        if candidate.startswith("{") or candidate.startswith("["):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError as exc:
                last_error = exc

    if stripped.startswith("```"):
        parts = stripped.split("```")
        for part in parts:
            candidate = part.strip()
            if candidate.lower().startswith("json"):
                candidate = candidate[4:].strip()
            if candidate.startswith("{") or candidate.startswith("["):
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError as exc:
                    last_error = exc

    for start_char, end_char in (("{", "}"), ("[", "]")):
        start = stripped.find(start_char)
        if start == -1:
            continue
        depth = 0
        for idx in range(start, len(stripped)):
            ch = stripped[idx]
            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
                if depth == 0:
                    candidate = stripped[start : idx + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError as exc:
                        last_error = exc
                    break
    if last_error is not None:
        raise last_error
    raise ValueError("No valid JSON payload found in model output.")


def to_pretty_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)
