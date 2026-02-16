from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from gh_llm import __version__
from gh_llm.github_api import GitHubClient
from gh_llm.pager import DEFAULT_PAGE_SIZE, TimelinePager
from gh_llm.render import (
    render_event_detail,
    render_expand_hints,
    render_header,
    render_hidden_gap,
    render_page,
)

if TYPE_CHECKING:
    from gh_llm.models import PullRequestMeta, TimelineContext, TimelinePage


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
    pr_parser = subparsers.add_parser("pr", help="PR-related commands")
    pr_subparsers = pr_parser.add_subparsers(dest="pr_command")

    view_parser = pr_subparsers.add_parser(
        "view",
        help="show first/last timeline page with real GitHub cursor pagination",
    )
    view_parser.add_argument("pr", nargs="?", help="PR number/url/branch")
    view_parser.add_argument("--repo", help="repository in OWNER/REPO format")
    view_parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="timeline entries per page")
    view_parser.set_defaults(handler=_cmd_pr_view)

    timeline_expand_parser = pr_subparsers.add_parser(
        "timeline-expand", help="load one timeline page by number"
    )
    timeline_expand_parser.add_argument("page", type=int, help="1-based page number")
    timeline_expand_parser.add_argument("--pr", help="PR number/url/branch")
    timeline_expand_parser.add_argument("--repo", help="repository in OWNER/REPO format")
    timeline_expand_parser.add_argument("--page-size", type=int, help="timeline entries per page")
    timeline_expand_parser.set_defaults(handler=_cmd_pr_timeline_expand)

    event_parser = pr_subparsers.add_parser("event", help="load one timeline event by global index")
    event_parser.add_argument("index", type=int, help="1-based event index from timeline view")
    event_parser.add_argument("--pr", help="PR number/url/branch")
    event_parser.add_argument("--repo", help="repository in OWNER/REPO format")
    event_parser.add_argument("--page-size", type=int, help="timeline entries per page")
    event_parser.set_defaults(handler=_cmd_pr_event)

    review_expand_parser = pr_subparsers.add_parser(
        "review-expand",
        help="expand resolved review comments for one or more review IDs",
    )
    review_expand_parser.add_argument(
        "review_ids",
        nargs="+",
        help="review ids, supports values like `PRR_xxx`, `PRR_xxx,PRR_yyy`",
    )
    review_expand_parser.add_argument("--pr", help="PR number/url/branch")
    review_expand_parser.add_argument("--repo", help="repository in OWNER/REPO format")
    review_expand_parser.add_argument("--page-size", type=int, help="timeline entries per page")
    review_expand_parser.set_defaults(handler=_cmd_pr_review_expand)

    thread_reply_parser = pr_subparsers.add_parser(
        "thread-reply", help="reply to a pull request review thread"
    )
    thread_reply_parser.add_argument("thread_id", help="review thread id, e.g. PRRT_xxx")
    thread_reply_parser.add_argument("--body", required=True, help="reply body")
    thread_reply_parser.add_argument("--pr", help="PR number/url/branch")
    thread_reply_parser.add_argument("--repo", help="repository in OWNER/REPO format")
    thread_reply_parser.set_defaults(handler=_cmd_pr_thread_reply)

    thread_resolve_parser = pr_subparsers.add_parser(
        "thread-resolve", help="mark a pull request review thread as resolved"
    )
    thread_resolve_parser.add_argument("thread_id", help="review thread id, e.g. PRRT_xxx")
    thread_resolve_parser.add_argument("--pr", help="PR number/url/branch")
    thread_resolve_parser.add_argument("--repo", help="repository in OWNER/REPO format")
    thread_resolve_parser.set_defaults(handler=_cmd_pr_thread_resolve)

    thread_unresolve_parser = pr_subparsers.add_parser(
        "thread-unresolve", help="mark a pull request review thread as unresolved"
    )
    thread_unresolve_parser.add_argument("thread_id", help="review thread id, e.g. PRRT_xxx")
    thread_unresolve_parser.add_argument("--pr", help="PR number/url/branch")
    thread_unresolve_parser.add_argument("--repo", help="repository in OWNER/REPO format")
    thread_unresolve_parser.set_defaults(handler=_cmd_pr_thread_unresolve)

    return parser


def _cmd_pr_view(args: argparse.Namespace) -> int:
    page_size = int(args.page_size)
    client = GitHubClient()
    pager = TimelinePager(client)

    meta = client.resolve_pull_request(selector=args.pr, repo=args.repo)
    context, first_page, last_page = pager.build_initial(meta, page_size=page_size)
    shown_pages: set[int] = {1}

    for line in render_header(context):
        print(line)
    for line in render_page(1, context, first_page):
        print(line)

    if last_page is not None:
        trailing_pages: list[tuple[int, TimelinePage]] = []
        include_previous = (
            context.total_pages > 2 and context.total_count % context.page_size != 0
        )
        if include_previous:
            previous_page_number = context.total_pages - 1
            previous_page = pager.fetch_page(meta=meta, context=context, page=previous_page_number)
            trailing_pages.append((previous_page_number, previous_page))
            shown_pages.add(previous_page_number)

        trailing_pages.append((context.total_pages, last_page))
        shown_pages.add(context.total_pages)

        first_trailing_page = min(page_number for page_number, _ in trailing_pages)
        hidden_start = 2
        hidden_end = first_trailing_page - 1
        hidden_pages = list(range(hidden_start, hidden_end + 1)) if hidden_start <= hidden_end else []
        print()
        for line in render_hidden_gap(context, hidden_pages):
            print(line)
        if hidden_pages:
            print()
        for index, (page_number, page_data) in enumerate(trailing_pages):
            if index > 0:
                print()
            for line in render_page(page_number, context, page_data):
                print(line)

    print()
    for line in render_expand_hints(context, shown_pages):
        print(line)

    return 0


def _cmd_pr_timeline_expand(args: argparse.Namespace) -> int:
    client = GitHubClient()
    pager = TimelinePager(client)
    context, meta = _resolve_context_and_meta(client=client, pager=pager, args=args)

    page = pager.fetch_page(meta=meta, context=context, page=int(args.page))

    for line in render_header(context):
        print(line)
    for line in render_page(int(args.page), context, page):
        print(line)

    return 0


def _cmd_pr_event(args: argparse.Namespace) -> int:
    client = GitHubClient()
    pager = TimelinePager(client)
    context, meta = _resolve_context_and_meta(client=client, pager=pager, args=args)

    index = int(args.index)
    if index < 1 or index > context.total_count:
        raise RuntimeError(f"invalid event index {index}, expected in 1..{context.total_count}")

    page_number = ((index - 1) // context.page_size) + 1
    page = pager.fetch_page(meta=meta, context=context, page=page_number)

    page_start = (page_number - 1) * context.page_size + 1
    offset = index - page_start
    if offset < 0 or offset >= len(page.items):
        raise RuntimeError("event index is outside loaded page range")

    for line in render_event_detail(index=index, event=page.items[offset]):
        print(line)
    return 0


def _cmd_pr_review_expand(args: argparse.Namespace) -> int:
    client = GitHubClient()
    pager = TimelinePager(client)
    context, meta = _resolve_context_and_meta(client=client, pager=pager, args=args)
    review_ids = parse_review_ids(args.review_ids)

    matched: dict[str, tuple[int, TimelinePage]] = {}
    for page_number in range(1, context.total_pages + 1):
        page = pager.fetch_page(
            meta=meta, context=context, page=page_number, show_resolved_details=True
        )
        for offset, event in enumerate(page.items):
            if not event.kind.startswith("review/"):
                continue
            if event.source_id in review_ids:
                event_index = ((page_number - 1) * context.page_size) + offset + 1
                matched[event.source_id] = (event_index, page)
        if len(matched) == len(review_ids):
            break

    for review_id in review_ids:
        item = matched.get(review_id)
        if item is None:
            print(f"## Review {review_id}")
            print("(not found on this PR timeline)")
            print()
            continue

        event_index, page = item
        page_start = (event_index - 1) // context.page_size * context.page_size + 1
        offset = event_index - page_start
        event = page.items[offset]
        for line in render_event_detail(index=event_index, event=event):
            print(line)
        print()

    return 0


def _cmd_pr_thread_reply(args: argparse.Namespace) -> int:
    client = GitHubClient()
    if args.repo is not None and args.pr is None:
        raise RuntimeError("`--pr` is required when `--repo` is provided")
    if args.pr is not None:
        client.resolve_pull_request(selector=args.pr, repo=args.repo)

    comment_id = client.reply_review_thread(thread_id=str(args.thread_id), body=str(args.body))
    print(f"thread: {args.thread_id}")
    if comment_id:
        print(f"reply_comment_id: {comment_id}")
    print("status: replied")
    return 0


def _cmd_pr_thread_resolve(args: argparse.Namespace) -> int:
    client = GitHubClient()
    if args.repo is not None and args.pr is None:
        raise RuntimeError("`--pr` is required when `--repo` is provided")
    if args.pr is not None:
        client.resolve_pull_request(selector=args.pr, repo=args.repo)

    resolved = client.resolve_review_thread(thread_id=str(args.thread_id))
    print(f"thread: {args.thread_id}")
    print(f"status: {'resolved' if resolved else 'unchanged'}")
    return 0


def _cmd_pr_thread_unresolve(args: argparse.Namespace) -> int:
    client = GitHubClient()
    if args.repo is not None and args.pr is None:
        raise RuntimeError("`--pr` is required when `--repo` is provided")
    if args.pr is not None:
        client.resolve_pull_request(selector=args.pr, repo=args.repo)

    resolved = client.unresolve_review_thread(thread_id=str(args.thread_id))
    print(f"thread: {args.thread_id}")
    print(f"status: {'still_resolved' if resolved else 'unresolved'}")
    return 0


def _resolve_context_and_meta(
    *, client: GitHubClient, pager: TimelinePager, args: argparse.Namespace
) -> tuple[TimelineContext, PullRequestMeta]:
    selector = getattr(args, "pr", None)
    repo = getattr(args, "repo", None)
    if repo is not None and selector is None:
        raise RuntimeError("`--pr` is required when `--repo` is provided")
    page_size = getattr(args, "page_size", None)
    effective_page_size = DEFAULT_PAGE_SIZE if page_size is None else int(page_size)
    meta = client.resolve_pull_request(selector=selector, repo=repo)
    context, _, _ = pager.build_initial(meta=meta, page_size=effective_page_size)
    return context, meta


def parse_event_indexes(raw_indexes: list[str]) -> list[int]:
    values: set[int] = set()
    for raw in raw_indexes:
        chunks = [chunk.strip() for chunk in raw.split(",") if chunk.strip()]
        for chunk in chunks:
            if "-" in chunk:
                left, right = chunk.split("-", 1)
                start = int(left)
                end = int(right)
                if start <= 0 or end <= 0:
                    raise RuntimeError(f"invalid index range: {chunk}")
                if start > end:
                    start, end = end, start
                values.update(range(start, end + 1))
                continue
            value = int(chunk)
            if value <= 0:
                raise RuntimeError(f"invalid event index: {value}")
            values.add(value)

    if not values:
        raise RuntimeError("no valid event indexes provided")
    return sorted(values)


def parse_review_ids(raw_review_ids: list[str]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for raw in raw_review_ids:
        for token in [chunk.strip() for chunk in raw.split(",") if chunk.strip()]:
            if not token.startswith("PRR_"):
                raise RuntimeError(f"invalid review id: {token}")
            if token in seen:
                continue
            seen.add(token)
            values.append(token)
    if not values:
        raise RuntimeError("no valid review ids provided")
    return values
