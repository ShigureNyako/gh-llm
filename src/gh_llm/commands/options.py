from __future__ import annotations

from difflib import get_close_matches
from typing import NoReturn


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
