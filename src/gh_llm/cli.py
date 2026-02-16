from __future__ import annotations

import argparse
import sys

from gh_llm import __version__
from gh_llm.commands.pr import (
    parse_event_indexes as _parse_event_indexes,
    parse_review_ids as _parse_review_ids,
    register_pr_parser,
)


def run(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0

    try:
        return int(handler(args))
    except (RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gh-llm",
        description="LLM-friendly GitHub pull request timeline viewer",
    )
    parser.add_argument("-v", "--version", action="version", version=__version__)

    subparsers = parser.add_subparsers(dest="command")
    register_pr_parser(subparsers)

    return parser


def parse_event_indexes(raw_indexes: list[str]) -> list[int]:
    return _parse_event_indexes(raw_indexes)


def parse_review_ids(raw_review_ids: list[str]) -> list[str]:
    return _parse_review_ids(raw_review_ids)
