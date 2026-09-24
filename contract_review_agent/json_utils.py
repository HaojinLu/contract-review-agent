from __future__ import annotations

import json
import re
from typing import Any


def extract_json_payload(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        raise ValueError("No valid JSON payload found in model output.")

    last_error: Exception | None = None

    # Prefer the complete payload when the model returned valid JSON directly.
    # Otherwise the fallback scanner can mistake an object inside an array for
    # the top-level response.
    if stripped.startswith(("{", "[")):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError as exc:
            last_error = exc

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

    starts = sorted(
        (stripped.find(start_char), start_char, end_char)
        for start_char, end_char in (("{", "}"), ("[", "]"))
        if stripped.find(start_char) != -1
    )
    for start, start_char, end_char in starts:
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
