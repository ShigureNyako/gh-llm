from __future__ import annotations

import sys
from difflib import get_close_matches
from pathlib import Path
from typing import Any, NoReturn


def read_text_from_path_or_stdin(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def resolve_file_or_inline_text(
    args: Any,
    *,
    text_attr: str,
    file_attr: str,
    default: str = "",
) -> str:
    file_path = getattr(args, file_attr, None)
    if file_path:
        return read_text_from_path_or_stdin(str(file_path))
    text = getattr(args, text_attr, None)
    if text is None:
        return default
    return str(text)


def raise_unknown_option_value(
    *,
    flag: str,
    token: str,
    valid_values: list[str],
    alias_values: list[str] | None = None,
) -> NoReturn:
    candidates = list(valid_values)
    if alias_values:
        candidates.extend(alias_values)
    suggestion = get_close_matches(token, candidates, n=1, cutoff=0.6)
    suggest_text = f" Did you mean '{suggestion[0]}'?" if suggestion else ""
    valid_text = ", ".join(valid_values)
    raise RuntimeError(f"unknown {flag} option: {token}. Valid values: {valid_text}.{suggest_text}")
