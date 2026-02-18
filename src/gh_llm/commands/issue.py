from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from gh_llm.github_api import GitHubClient
from gh_llm.pager import DEFAULT_PAGE_SIZE, TimelinePager
from gh_llm.render import (
    render_description,
    render_event_detail,
    render_event_detail_blocks,
    render_expand_hints,
    render_frontmatter,
    render_header,
    render_hidden_gap,
    render_issue_actions,
    render_page,
)

if TYPE_CHECKING:
    from gh_llm.models import PullRequestMeta, TimelineContext, TimelinePage


@dataclass(frozen=True)
class _ExpandOptions:
    hidden: bool = False
    details: bool = False


@dataclass(frozen=True)
class _ShowOptions:
    meta: bool = True
    description: bool = True
    timeline: bool = True
    actions: bool = True


def register_issue_parser(subparsers: Any) -> None:
    issue_parser = subparsers.add_parser("issue", help="Issue-related commands")
    issue_subparsers = issue_parser.add_subparsers(dest="issue_command")

    view_parser = issue_subparsers.add_parser(
        "view",
        help="show first/last timeline page with real GitHub cursor pagination",
    )
    view_parser.add_argument("issue", nargs="?", help="Issue number/url")
    view_parser.add_argument("--repo", help="repository in OWNER/REPO format")
    view_parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="timeline entries per page")
    view_parser.add_argument(
        "--show",
        action="append",
        default=[],
        help="show regions: meta, description, timeline, actions, all (comma-separated or repeatable)",
    )
    view_parser.add_argument(
        "--expand",
        action="append",
        default=[],
        help="auto-expand folded content: hidden, details, all (comma-separated or repeatable)",
    )
    view_parser.set_defaults(handler=cmd_issue_view)

    timeline_expand_parser = issue_subparsers.add_parser("timeline-expand", help="load one timeline page by number")
    timeline_expand_parser.add_argument("page", type=int, help="1-based page number")
    timeline_expand_parser.add_argument("--issue", help="Issue number/url")
    timeline_expand_parser.add_argument("--repo", help="repository in OWNER/REPO format")
    timeline_expand_parser.add_argument("--page-size", type=int, help="timeline entries per page")
    timeline_expand_parser.add_argument(
        "--expand",
        action="append",
        default=[],
        help="auto-expand folded content: hidden, details, all (comma-separated or repeatable)",
    )
    timeline_expand_parser.set_defaults(handler=cmd_issue_timeline_expand)

    event_parser = issue_subparsers.add_parser("event", help="load one timeline event by global index")
    event_parser.add_argument("index", type=int, help="1-based event index from timeline view")
    event_parser.add_argument("--issue", help="Issue number/url")
    event_parser.add_argument("--repo", help="repository in OWNER/REPO format")
    event_parser.add_argument("--page-size", type=int, help="timeline entries per page")
    event_parser.set_defaults(handler=cmd_issue_event)

    details_expand_parser = issue_subparsers.add_parser(
        "details-expand",
        help="show collapsed <details>/<summary> blocks for one timeline event",
    )
    details_expand_parser.add_argument("index", type=int, help="1-based event index from timeline view")
    details_expand_parser.add_argument("--issue", help="Issue number/url")
    details_expand_parser.add_argument("--repo", help="repository in OWNER/REPO format")
    details_expand_parser.add_argument("--page-size", type=int, help="timeline entries per page")
    details_expand_parser.set_defaults(handler=cmd_issue_details_expand)

    comment_edit_parser = issue_subparsers.add_parser("comment-edit", help="edit one issue comment by node id")
    comment_edit_parser.add_argument("comment_id", help="comment id, e.g. IC_xxx")
    comment_edit_parser.add_argument("--body", required=True, help="new comment body")
    comment_edit_parser.add_argument("--issue", help="Issue number/url")
    comment_edit_parser.add_argument("--repo", help="repository in OWNER/REPO format")
    comment_edit_parser.set_defaults(handler=cmd_issue_comment_edit)


def cmd_issue_view(args: Any) -> int:
    page_size = int(args.page_size)
    expand = _parse_expand_options(raw_values=list(getattr(args, "expand", [])))
    show = _parse_show_options(raw_values=list(getattr(args, "show", [])))
    client = GitHubClient()
    pager = TimelinePager(client)

    meta = client.resolve_issue(selector=args.issue, repo=args.repo)
    context, first_page, last_page = pager.build_initial(
        meta,
        page_size=page_size,
        show_minimized_details=expand.hidden,
        show_details_blocks=expand.details,
    )
    shown_pages: set[int] = {1}

    wrote_output = False

    def print_block(lines: list[str]) -> None:
        nonlocal wrote_output
        if not lines:
            return
        if wrote_output:
            print()
        for line in lines:
            print(line)
        wrote_output = True

    if show.meta:
        print_block(render_frontmatter(context))
    if show.description:
        print_block(render_description(context))
    if show.timeline:
        print_block(render_page(1, context, first_page))

    if show.timeline and last_page is not None:
        trailing_pages: list[tuple[int, TimelinePage]] = []
        include_previous = context.total_pages > 2 and context.total_count % context.page_size != 0
        if include_previous:
            previous_page_number = context.total_pages - 1
            previous_page = pager.fetch_page(
                meta=meta,
                context=context,
                page=previous_page_number,
                show_minimized_details=expand.hidden,
                show_details_blocks=expand.details,
            )
            trailing_pages.append((previous_page_number, previous_page))
            shown_pages.add(previous_page_number)

        trailing_pages.append((context.total_pages, last_page))
        shown_pages.add(context.total_pages)

        first_trailing_page = min(page_number for page_number, _ in trailing_pages)
        hidden_start = 2
        hidden_end = first_trailing_page - 1
        hidden_pages = list(range(hidden_start, hidden_end + 1)) if hidden_start <= hidden_end else []
        print_block(render_hidden_gap(context, hidden_pages))
        if hidden_pages:
            print()
        for index, (page_number, page_data) in enumerate(trailing_pages):
            if index > 0:
                print()
            for line in render_page(page_number, context, page_data):
                print(line)

    if show.timeline:
        print_block(render_expand_hints(context, shown_pages))
    if show.actions:
        print_block(render_issue_actions(context))

    return 0


def cmd_issue_timeline_expand(args: Any) -> int:
    client = GitHubClient()
    pager = TimelinePager(client)
    context, meta = _resolve_context_and_meta(client=client, pager=pager, args=args)
    expand = _parse_expand_options(raw_values=list(getattr(args, "expand", [])))

    page = pager.fetch_page(
        meta=meta,
        context=context,
        page=int(args.page),
        show_minimized_details=expand.hidden,
        show_details_blocks=expand.details,
    )

    for line in render_header(context):
        print(line)
    for line in render_page(int(args.page), context, page):
        print(line)

    return 0


def cmd_issue_event(args: Any) -> int:
    client = GitHubClient()
    pager = TimelinePager(client)
    context, meta = _resolve_context_and_meta(client=client, pager=pager, args=args)

    index = int(args.index)
    if index < 1 or index > context.total_count:
        raise RuntimeError(f"invalid event index {index}, expected in 1..{context.total_count}")

    page_number = ((index - 1) // context.page_size) + 1
    page = pager.fetch_page(
        meta=meta,
        context=context,
        page=page_number,
        show_minimized_details=True,
        show_details_blocks=False,
    )

    page_start = (page_number - 1) * context.page_size + 1
    offset = index - page_start
    if offset < 0 or offset >= len(page.items):
        raise RuntimeError("event index is outside loaded page range")

    for line in render_event_detail(index=index, event=page.items[offset]):
        print(line)
    return 0


def cmd_issue_details_expand(args: Any) -> int:
    client = GitHubClient()
    pager = TimelinePager(client)
    context, meta = _resolve_context_and_meta(client=client, pager=pager, args=args)

    index = int(args.index)
    if index < 1 or index > context.total_count:
        raise RuntimeError(f"invalid event index {index}, expected in 1..{context.total_count}")

    page_number = ((index - 1) // context.page_size) + 1
    page = pager.fetch_page(
        meta=meta,
        context=context,
        page=page_number,
        show_minimized_details=True,
        show_details_blocks=True,
        diff_hunk_lines=None,
    )
    page_start = (page_number - 1) * context.page_size + 1
    offset = index - page_start
    if offset < 0 or offset >= len(page.items):
        raise RuntimeError("event index is outside loaded page range")

    for line in render_event_detail_blocks(index=index, event=page.items[offset]):
        print(line)
    return 0


def cmd_issue_comment_edit(args: Any) -> int:
    client = GitHubClient()
    if args.repo is not None and args.issue is None:
        raise RuntimeError("`--issue` is required when `--repo` is provided")
    if args.issue is not None:
        client.resolve_issue(selector=args.issue, repo=args.repo)
    updated_comment_id = client.edit_comment(comment_id=str(args.comment_id), body=str(args.body))
    print(f"comment: {updated_comment_id}")
    print("status: edited")
    return 0


def _resolve_context_and_meta(
    *, client: GitHubClient, pager: TimelinePager, args: Any
) -> tuple[TimelineContext, PullRequestMeta]:
    selector = getattr(args, "issue", None)
    repo = getattr(args, "repo", None)
    if repo is not None and selector is None:
        raise RuntimeError("`--issue` is required when `--repo` is provided")
    page_size = getattr(args, "page_size", None)
    effective_page_size = DEFAULT_PAGE_SIZE if page_size is None else int(page_size)
    meta = client.resolve_issue(selector=selector, repo=repo)
    context, _, _ = pager.build_initial(meta=meta, page_size=effective_page_size)
    return context, meta


def _parse_expand_options(*, raw_values: list[str]) -> _ExpandOptions:
    hidden = False
    details = False

    aliases: dict[str, str] = {
        "hidden": "hidden",
        "hidden_comments": "hidden",
        "hidden-comments": "hidden",
        "minimized": "hidden",
        "outdated": "hidden",
        "details": "details",
        "detail": "details",
        "all": "all",
        "*": "all",
    }

    for raw in raw_values:
        for part in raw.split(","):
            token = part.strip().lower()
            if not token:
                continue
            normalized = aliases.get(token)
            if normalized is None:
                raise RuntimeError(f"unknown expand option: {token}")
            if normalized == "all":
                hidden = True
                details = True
                continue
            if normalized == "hidden":
                hidden = True
            elif normalized == "details":
                details = True

    return _ExpandOptions(hidden=hidden, details=details)


def _parse_show_options(*, raw_values: list[str]) -> _ShowOptions:
    if not raw_values:
        return _ShowOptions()

    selected: set[str] = set()
    aliases: dict[str, set[str]] = {
        "meta": {"meta"},
        "description": {"description"},
        "desc": {"description"},
        "timeline": {"timeline"},
        "actions": {"actions"},
        "summary": {"meta", "description"},
        "all": {"meta", "description", "timeline", "actions"},
        "*": {"meta", "description", "timeline", "actions"},
    }

    for raw in raw_values:
        for part in raw.split(","):
            token = part.strip().lower()
            if not token:
                continue
            mapped = aliases.get(token)
            if mapped is None:
                raise RuntimeError(f"unknown show option: {token}")
            selected.update(mapped)

    return _ShowOptions(
        meta=("meta" in selected),
        description=("description" in selected),
        timeline=("timeline" in selected),
        actions=("actions" in selected),
    )
