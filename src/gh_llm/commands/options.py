from __future__ import annotations

import sys
from difflib import get_close_matches
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

if TYPE_CHECKING:
    from collections.abc import Callable


def add_body_input_arguments(
    parser: Any,
    *,
    required: bool,
    body_help: str,
    file_help: str,
    default: str | None = None,
) -> None:
    group = parser.add_mutually_exclusive_group(required=required)
    body_kwargs: dict[str, object] = {"help": body_help}
    if default is not None:
        body_kwargs["default"] = default
    group.add_argument("--body", **body_kwargs)
    group.add_argument(
        "-F",
        "--body-file",
        help=file_help,
    )


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
    if file_path is not None:
        return read_text_from_path_or_stdin(str(file_path))
    text = getattr(args, text_attr, None)
    if text is None:
        return default
    return str(text)


def resolve_subject[T](
    *,
    selector: str | None,
    repo: str | None,
    selector_flag: str,
    resolver: Callable[[str | None, str | None], T],
) -> T:
    _validate_selector_for_repo(selector=selector, repo=repo, selector_flag=selector_flag)
    return resolver(selector, repo)


def maybe_resolve_subject[T](
    *,
    selector: str | None,
    repo: str | None,
    selector_flag: str,
    resolver: Callable[[str | None, str | None], T],
) -> T | None:
    _validate_selector_for_repo(selector=selector, repo=repo, selector_flag=selector_flag)
    if selector is None:
        return None
    return resolver(selector, repo)


def _validate_selector_for_repo(*, selector: str | None, repo: str | None, selector_flag: str) -> None:
    if repo is not None and selector is None:
        raise RuntimeError(f"`{selector_flag}` is required when `--repo` is provided")


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
