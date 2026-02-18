from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from gh_llm.github_api import GitHubClient
from gh_llm.invocation import display_command_with
from gh_llm.pager import DEFAULT_PAGE_SIZE, TimelinePager
from gh_llm.render import (
    render_checks_section,
    render_event_detail,
    render_event_detail_blocks,
    render_expand_hints,
    render_header,
    render_hidden_gap,
    render_page,
    render_pr_actions,
)

if TYPE_CHECKING:
    from gh_llm.models import PullRequestMeta, TimelineContext, TimelinePage

DEFAULT_DIFF_HUNK_LINES = 12


@dataclass(frozen=True)
class _ExpandOptions:
    resolved: bool = False
    hidden: bool = False
    details: bool = False


def register_pr_parser(subparsers: Any) -> None:
    pr_parser = subparsers.add_parser("pr", help="PR-related commands")
    pr_subparsers = pr_parser.add_subparsers(dest="pr_command")

    view_parser = pr_subparsers.add_parser(
        "view",
        help="show first/last timeline page with real GitHub cursor pagination",
    )
    view_parser.add_argument("pr", nargs="?", help="PR number/url/branch")
    view_parser.add_argument("--repo", help="repository in OWNER/REPO format")
    view_parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="timeline entries per page")
    view_parser.add_argument(
        "--expand",
        action="append",
        default=[],
        help="auto-expand folded content: resolved, hidden, details, all (comma-separated or repeatable)",
    )
    view_parser.add_argument(
        "--diff-hunk-lines",
        type=int,
        default=DEFAULT_DIFF_HUNK_LINES,
        help="max lines for each review diff hunk (<=0 means full)",
    )
    view_parser.set_defaults(handler=cmd_pr_view)

    timeline_expand_parser = pr_subparsers.add_parser("timeline-expand", help="load one timeline page by number")
    timeline_expand_parser.add_argument("page", type=int, help="1-based page number")
    timeline_expand_parser.add_argument("--pr", help="PR number/url/branch")
    timeline_expand_parser.add_argument("--repo", help="repository in OWNER/REPO format")
    timeline_expand_parser.add_argument("--page-size", type=int, help="timeline entries per page")
    timeline_expand_parser.add_argument(
        "--expand",
        action="append",
        default=[],
        help="auto-expand folded content: resolved, hidden, details, all (comma-separated or repeatable)",
    )
    timeline_expand_parser.add_argument(
        "--diff-hunk-lines",
        type=int,
        default=DEFAULT_DIFF_HUNK_LINES,
        help="max lines for each review diff hunk (<=0 means full)",
    )
    timeline_expand_parser.set_defaults(handler=cmd_pr_timeline_expand)

    event_parser = pr_subparsers.add_parser("event", help="load one timeline event by global index")
    event_parser.add_argument("index", type=int, help="1-based event index from timeline view")
    event_parser.add_argument("--pr", help="PR number/url/branch")
    event_parser.add_argument("--repo", help="repository in OWNER/REPO format")
    event_parser.add_argument("--page-size", type=int, help="timeline entries per page")
    event_parser.add_argument(
        "--diff-hunk-lines",
        type=int,
        default=0,
        help="max lines for each review diff hunk (default full for event view)",
    )
    event_parser.set_defaults(handler=cmd_pr_event)

    details_expand_parser = pr_subparsers.add_parser(
        "details-expand",
        help="show collapsed <details>/<summary> blocks for one timeline event",
    )
    details_expand_parser.add_argument("index", type=int, help="1-based event index from timeline view")
    details_expand_parser.add_argument("--pr", help="PR number/url/branch")
    details_expand_parser.add_argument("--repo", help="repository in OWNER/REPO format")
    details_expand_parser.add_argument("--page-size", type=int, help="timeline entries per page")
    details_expand_parser.set_defaults(handler=cmd_pr_details_expand)

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
    review_expand_parser.add_argument(
        "--diff-hunk-lines",
        type=int,
        default=DEFAULT_DIFF_HUNK_LINES,
        help="max lines for each review diff hunk (<=0 means full)",
    )
    review_expand_parser.set_defaults(handler=cmd_pr_review_expand)

    checks_parser = pr_subparsers.add_parser("checks", help="show CI checks for the pull request")
    checks_parser.add_argument("--pr", help="PR number/url/branch")
    checks_parser.add_argument("--repo", help="repository in OWNER/REPO format")
    checks_parser.add_argument("--all", action="store_true", help="show all checks including passed")
    checks_parser.set_defaults(handler=cmd_pr_checks)

    thread_reply_parser = pr_subparsers.add_parser("thread-reply", help="reply to a pull request review thread")
    thread_reply_parser.add_argument("thread_id", help="review thread id, e.g. PRRT_xxx")
    thread_reply_parser.add_argument("--body", required=True, help="reply body")
    thread_reply_parser.add_argument("--pr", help="PR number/url/branch")
    thread_reply_parser.add_argument("--repo", help="repository in OWNER/REPO format")
    thread_reply_parser.set_defaults(handler=cmd_pr_thread_reply)

    thread_resolve_parser = pr_subparsers.add_parser(
        "thread-resolve", help="mark a pull request review thread as resolved"
    )
    thread_resolve_parser.add_argument("thread_id", help="review thread id, e.g. PRRT_xxx")
    thread_resolve_parser.add_argument("--pr", help="PR number/url/branch")
    thread_resolve_parser.add_argument("--repo", help="repository in OWNER/REPO format")
    thread_resolve_parser.set_defaults(handler=cmd_pr_thread_resolve)

    thread_unresolve_parser = pr_subparsers.add_parser(
        "thread-unresolve", help="mark a pull request review thread as unresolved"
    )
    thread_unresolve_parser.add_argument("thread_id", help="review thread id, e.g. PRRT_xxx")
    thread_unresolve_parser.add_argument("--pr", help="PR number/url/branch")
    thread_unresolve_parser.add_argument("--repo", help="repository in OWNER/REPO format")
    thread_unresolve_parser.set_defaults(handler=cmd_pr_thread_unresolve)

    comment_edit_parser = pr_subparsers.add_parser("comment-edit", help="edit one issue/review comment by node id")
    comment_edit_parser.add_argument("comment_id", help="comment id, e.g. IC_xxx or PRRC_xxx")
    comment_edit_parser.add_argument("--body", required=True, help="new comment body")
    comment_edit_parser.add_argument("--pr", help="PR number/url/branch")
    comment_edit_parser.add_argument("--repo", help="repository in OWNER/REPO format")
    comment_edit_parser.set_defaults(handler=cmd_pr_comment_edit)

    review_start_parser = pr_subparsers.add_parser(
        "review-start",
        help="show review-oriented diff hunks and ready-to-run comment/suggestion commands",
    )
    review_start_parser.add_argument("--pr", help="PR number/url/branch")
    review_start_parser.add_argument("--repo", help="repository in OWNER/REPO format")
    review_start_parser.add_argument("--max-hunks", type=int, default=40, help="maximum hunks to render")
    review_start_parser.set_defaults(handler=cmd_pr_review_start)

    review_comment_parser = pr_subparsers.add_parser(
        "review-comment", help="add one inline review comment at a specific line"
    )
    review_comment_parser.add_argument("--path", required=True, help="file path in pull request")
    review_comment_parser.add_argument("--line", required=True, type=int, help="line number on selected side")
    review_comment_parser.add_argument("--side", choices=["RIGHT", "LEFT"], default="RIGHT", help="diff side")
    review_comment_parser.add_argument("--body", required=True, help="review comment body")
    review_comment_parser.add_argument("--pr", help="PR number/url/branch")
    review_comment_parser.add_argument("--repo", help="repository in OWNER/REPO format")
    review_comment_parser.set_defaults(handler=cmd_pr_review_comment)

    review_suggest_parser = pr_subparsers.add_parser(
        "review-suggest", help="add one inline review suggestion at a specific line"
    )
    review_suggest_parser.add_argument("--path", required=True, help="file path in pull request")
    review_suggest_parser.add_argument("--line", required=True, type=int, help="line number on selected side")
    review_suggest_parser.add_argument("--side", choices=["RIGHT", "LEFT"], default="RIGHT", help="diff side")
    review_suggest_parser.add_argument(
        "--body",
        default="Suggested change",
        help="review comment body before suggestion block",
    )
    review_suggest_parser.add_argument(
        "--suggestion",
        required=True,
        help="replacement content inserted inside ```suggestion block",
    )
    review_suggest_parser.add_argument("--pr", help="PR number/url/branch")
    review_suggest_parser.add_argument("--repo", help="repository in OWNER/REPO format")
    review_suggest_parser.set_defaults(handler=cmd_pr_review_suggest)

    review_submit_parser = pr_subparsers.add_parser(
        "review-submit", help="submit a top-level PR review (approve/request changes/comment)"
    )
    review_submit_parser.add_argument(
        "--event",
        choices=["COMMENT", "APPROVE", "REQUEST_CHANGES"],
        default="COMMENT",
        help="review event type",
    )
    review_submit_parser.add_argument("--body", default="", help="review summary body")
    review_submit_parser.add_argument("--pr", help="PR number/url/branch")
    review_submit_parser.add_argument("--repo", help="repository in OWNER/REPO format")
    review_submit_parser.set_defaults(handler=cmd_pr_review_submit)


def cmd_pr_view(args: Any) -> int:
    page_size = int(args.page_size)
    diff_hunk_lines = _resolve_diff_hunk_lines(args=args, default=DEFAULT_DIFF_HUNK_LINES)
    expand = _parse_expand_options(raw_values=list(getattr(args, "expand", [])))
    client = GitHubClient()
    pager = TimelinePager(client)

    meta = client.resolve_pull_request(selector=args.pr, repo=args.repo)
    context, first_page, last_page = pager.build_initial(
        meta,
        page_size=page_size,
        show_resolved_details=expand.resolved,
        show_minimized_details=expand.hidden,
        show_details_blocks=expand.details,
        diff_hunk_lines=diff_hunk_lines,
    )
    shown_pages: set[int] = {1}

    for line in render_header(context):
        print(line)
    for line in render_page(1, context, first_page):
        print(line)

    if last_page is not None:
        trailing_pages: list[tuple[int, TimelinePage]] = []
        include_previous = context.total_pages > 2 and context.total_count % context.page_size != 0
        if include_previous:
            previous_page_number = context.total_pages - 1
            previous_page = pager.fetch_page(
                meta=meta,
                context=context,
                page=previous_page_number,
                show_resolved_details=expand.resolved,
                show_minimized_details=expand.hidden,
                show_details_blocks=expand.details,
                diff_hunk_lines=diff_hunk_lines,
            )
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
    checks = client.fetch_checks(meta.ref) if meta.state == "OPEN" else []
    for line in render_checks_section(
        context=context,
        checks=checks,
        show_all=False,
        is_open=(meta.state == "OPEN"),
    ):
        print(line)
    for line in render_pr_actions(context):
        print(line)

    return 0


def cmd_pr_timeline_expand(args: Any) -> int:
    client = GitHubClient()
    pager = TimelinePager(client)
    context, meta = _resolve_context_and_meta(client=client, pager=pager, args=args)
    diff_hunk_lines = _resolve_diff_hunk_lines(args=args, default=DEFAULT_DIFF_HUNK_LINES)
    expand = _parse_expand_options(raw_values=list(getattr(args, "expand", [])))

    page = pager.fetch_page(
        meta=meta,
        context=context,
        page=int(args.page),
        show_resolved_details=expand.resolved,
        show_minimized_details=expand.hidden,
        show_details_blocks=expand.details,
        diff_hunk_lines=diff_hunk_lines,
    )

    for line in render_header(context):
        print(line)
    for line in render_page(int(args.page), context, page):
        print(line)

    return 0


def cmd_pr_event(args: Any) -> int:
    client = GitHubClient()
    pager = TimelinePager(client)
    context, meta = _resolve_context_and_meta(client=client, pager=pager, args=args)
    diff_hunk_lines = _resolve_diff_hunk_lines(args=args, default=0)

    index = int(args.index)
    if index < 1 or index > context.total_count:
        raise RuntimeError(f"invalid event index {index}, expected in 1..{context.total_count}")

    page_number = ((index - 1) // context.page_size) + 1
    page = pager.fetch_page(
        meta=meta,
        context=context,
        page=page_number,
        show_resolved_details=True,
        show_minimized_details=True,
        show_details_blocks=False,
        diff_hunk_lines=diff_hunk_lines,
    )

    page_start = (page_number - 1) * context.page_size + 1
    offset = index - page_start
    if offset < 0 or offset >= len(page.items):
        raise RuntimeError("event index is outside loaded page range")

    for line in render_event_detail(index=index, event=page.items[offset]):
        print(line)
    return 0


def cmd_pr_details_expand(args: Any) -> int:
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
        show_resolved_details=True,
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


def cmd_pr_review_expand(args: Any) -> int:
    client = GitHubClient()
    pager = TimelinePager(client)
    context, meta = _resolve_context_and_meta(client=client, pager=pager, args=args)
    review_ids = parse_review_ids(args.review_ids)
    diff_hunk_lines = _resolve_diff_hunk_lines(args=args, default=DEFAULT_DIFF_HUNK_LINES)
    if diff_hunk_lines is not None:
        print("Δ Diff hunk window is limited; rerun with `--diff-hunk-lines 0` for full review diff context.")
        print()

    matched: dict[str, tuple[int, TimelinePage]] = {}
    for page_number in range(1, context.total_pages + 1):
        page = pager.fetch_page(
            meta=meta,
            context=context,
            page=page_number,
            show_resolved_details=True,
            show_minimized_details=True,
            show_details_blocks=False,
            diff_hunk_lines=diff_hunk_lines,
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


def cmd_pr_checks(args: Any) -> int:
    client = GitHubClient()
    pager = TimelinePager(client)
    context, meta = _resolve_context_and_meta(client=client, pager=pager, args=args)
    checks = client.fetch_checks(meta.ref)
    for line in render_checks_section(
        context=context,
        checks=checks,
        show_all=bool(args.all),
        is_open=(meta.state == "OPEN"),
    ):
        print(line)
    return 0


def cmd_pr_thread_reply(args: Any) -> int:
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


def cmd_pr_thread_resolve(args: Any) -> int:
    client = GitHubClient()
    if args.repo is not None and args.pr is None:
        raise RuntimeError("`--pr` is required when `--repo` is provided")
    if args.pr is not None:
        client.resolve_pull_request(selector=args.pr, repo=args.repo)

    resolved = client.resolve_review_thread(thread_id=str(args.thread_id))
    print(f"thread: {args.thread_id}")
    print(f"status: {'resolved' if resolved else 'unchanged'}")
    return 0


def cmd_pr_thread_unresolve(args: Any) -> int:
    client = GitHubClient()
    if args.repo is not None and args.pr is None:
        raise RuntimeError("`--pr` is required when `--repo` is provided")
    if args.pr is not None:
        client.resolve_pull_request(selector=args.pr, repo=args.repo)

    resolved = client.unresolve_review_thread(thread_id=str(args.thread_id))
    print(f"thread: {args.thread_id}")
    print(f"status: {'still_resolved' if resolved else 'unresolved'}")
    return 0


def cmd_pr_comment_edit(args: Any) -> int:
    client = GitHubClient()
    if args.repo is not None and args.pr is None:
        raise RuntimeError("`--pr` is required when `--repo` is provided")
    if args.pr is not None:
        client.resolve_pull_request(selector=args.pr, repo=args.repo)
    updated_comment_id = client.edit_comment(comment_id=str(args.comment_id), body=str(args.body))
    print(f"comment: {updated_comment_id}")
    print("status: edited")
    return 0


def cmd_pr_review_start(args: Any) -> int:
    client = GitHubClient()
    meta = _resolve_pr_meta(client=client, args=args)
    diff = client.fetch_pr_diff(selector=getattr(args, "pr", None), repo=getattr(args, "repo", None))
    hunks = _extract_diff_hunks(diff)
    max_hunks = max(1, int(args.max_hunks))
    visible = hunks[:max_hunks]
    hidden = len(hunks) - len(visible)
    repo = f"{meta.ref.owner}/{meta.ref.name}"

    print("## Review Start")
    print(f"PR: {meta.ref.number} ({repo})")
    print(f"Total hunks: {len(hunks)}")
    print(f"Δ full diff: `gh pr diff {meta.ref.number} --repo {repo}`")
    comment_template_cmd = display_command_with(
        f"pr review-comment --path '<path>' --line <line> --side RIGHT --body '<review_comment>' --pr {meta.ref.number} --repo {repo}"
    )
    suggestion_template_cmd = display_command_with(
        f"pr review-suggest --path '<path>' --line <line> --side RIGHT --body '<reason>' --suggestion '<replacement>' --pr {meta.ref.number} --repo {repo}"
    )
    print(f"Comment template: `{comment_template_cmd}`")
    print(f"Suggestion template: `{suggestion_template_cmd}`")
    print()

    if not visible:
        print("(no diff hunks found)")
        return 0

    for idx, hunk in enumerate(visible, start=1):
        print(f"### Hunk {idx}")
        print(f"File: {hunk.path}")
        print(f"Header: {hunk.header}")
        print(f"Suggested anchor line (RIGHT): {hunk.anchor_line}")
        comment_cmd = display_command_with(
            f"pr review-comment --path '{hunk.path}' --line {hunk.anchor_line} --side RIGHT --body '<review_comment>' --pr {meta.ref.number} --repo {repo}"
        )
        suggest_cmd = display_command_with(
            f"pr review-suggest --path '{hunk.path}' --line {hunk.anchor_line} --side RIGHT --body '<reason>' --suggestion '<replacement>' --pr {meta.ref.number} --repo {repo}"
        )
        print(f"⏎ comment: `{comment_cmd}`")
        print(f"⏎ suggest: `{suggest_cmd}`")
        print("```diff")
        for line in hunk.lines:
            print(line)
        print("```")
        print()

    if hidden > 0:
        print(f"... {hidden} hunks hidden by --max-hunks")
    return 0


def cmd_pr_review_comment(args: Any) -> int:
    client = GitHubClient()
    meta = _resolve_pr_meta(client=client, args=args)
    thread_id, comment_id = client.add_pull_request_review_thread_comment(
        ref=meta.ref,
        path=str(args.path),
        line=int(args.line),
        side=str(args.side),
        body=str(args.body),
    )
    print(f"thread: {thread_id}")
    if comment_id:
        print(f"comment: {comment_id}")
    print("status: commented")
    return 0


def cmd_pr_review_suggest(args: Any) -> int:
    client = GitHubClient()
    meta = _resolve_pr_meta(client=client, args=args)
    suggestion = str(args.suggestion).rstrip("\n")
    full_body = f"{str(args.body).rstrip()}\n\n```suggestion\n{suggestion}\n```"
    thread_id, comment_id = client.add_pull_request_review_thread_comment(
        ref=meta.ref,
        path=str(args.path),
        line=int(args.line),
        side=str(args.side),
        body=full_body,
    )
    print(f"thread: {thread_id}")
    if comment_id:
        print(f"comment: {comment_id}")
    print("status: suggested")
    return 0


def cmd_pr_review_submit(args: Any) -> int:
    client = GitHubClient()
    meta = _resolve_pr_meta(client=client, args=args)
    body = str(args.body)
    review_id, review_state = client.submit_pull_request_review(
        ref=meta.ref,
        event=str(args.event),
        body=body if body else None,
    )
    print(f"review: {review_id}")
    if review_state:
        print(f"state: {review_state}")
    print("status: submitted")
    return 0


def _resolve_context_and_meta(
    *, client: GitHubClient, pager: TimelinePager, args: Any
) -> tuple[TimelineContext, PullRequestMeta]:
    selector = getattr(args, "pr", None)
    repo = getattr(args, "repo", None)
    if repo is not None and selector is None:
        raise RuntimeError("`--pr` is required when `--repo` is provided")
    page_size = getattr(args, "page_size", None)
    effective_page_size = DEFAULT_PAGE_SIZE if page_size is None else int(page_size)
    diff_hunk_lines = _resolve_diff_hunk_lines(args=args, default=DEFAULT_DIFF_HUNK_LINES)
    meta = client.resolve_pull_request(selector=selector, repo=repo)
    context, _, _ = pager.build_initial(
        meta=meta,
        page_size=effective_page_size,
        diff_hunk_lines=diff_hunk_lines,
    )
    return context, meta


def _resolve_diff_hunk_lines(*, args: Any, default: int) -> int | None:
    raw = getattr(args, "diff_hunk_lines", None)
    if raw is None:
        raw = default
    value = int(raw)
    if value <= 0:
        return None
    return value


def _parse_expand_options(*, raw_values: list[str]) -> _ExpandOptions:
    resolved = False
    hidden = False
    details = False

    aliases: dict[str, str] = {
        "resolved": "resolved",
        "resolve": "resolved",
        "resolved_comments": "resolved",
        "resolved-comments": "resolved",
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
                resolved = True
                hidden = True
                details = True
                continue
            if normalized == "resolved":
                resolved = True
            elif normalized == "hidden":
                hidden = True
            elif normalized == "details":
                details = True

    return _ExpandOptions(resolved=resolved, hidden=hidden, details=details)


def _resolve_pr_meta(*, client: GitHubClient, args: Any) -> PullRequestMeta:
    selector = getattr(args, "pr", None)
    repo = getattr(args, "repo", None)
    if repo is not None and selector is None:
        raise RuntimeError("`--pr` is required when `--repo` is provided")
    return client.resolve_pull_request(selector=selector, repo=repo)


class _DiffHunk:
    def __init__(self, path: str, header: str, anchor_line: int, lines: list[str]) -> None:
        self.path = path
        self.header = header
        self.anchor_line = anchor_line
        self.lines = lines


_HUNK_HEADER_RE = re.compile(r"^@@ -(?P<old>\d+)(?:,\d+)? \+(?P<new>\d+)(?:,\d+)? @@")


def _extract_diff_hunks(diff: str) -> list[_DiffHunk]:
    hunks: list[_DiffHunk] = []
    current_path = ""
    current_hunk_header = ""
    current_hunk_lines: list[str] = []
    current_new_line = 0
    current_anchor = 0

    def flush() -> None:
        nonlocal current_hunk_header, current_hunk_lines, current_anchor
        if current_path and current_hunk_header and current_hunk_lines:
            hunks.append(
                _DiffHunk(
                    path=current_path,
                    header=current_hunk_header,
                    anchor_line=current_anchor if current_anchor > 0 else 1,
                    lines=current_hunk_lines.copy(),
                )
            )
        current_hunk_header = ""
        current_hunk_lines = []
        current_anchor = 0

    for raw in diff.splitlines():
        if raw.startswith("diff --git "):
            flush()
            continue
        if raw.startswith("--- a/"):
            flush()
            continue
        if raw.startswith("+++ b/"):
            flush()
            current_path = raw[len("+++ b/") :]
            continue

        if raw.startswith("@@ "):
            flush()
            current_hunk_header = raw
            current_hunk_lines = [raw]
            match = _HUNK_HEADER_RE.match(raw)
            if match is None:
                current_new_line = 1
                current_anchor = 1
            else:
                current_new_line = int(match.group("new"))
                current_anchor = current_new_line
            continue

        if not current_hunk_header:
            continue

        current_hunk_lines.append(raw)
        if raw.startswith("+"):
            if current_anchor <= 0:
                current_anchor = current_new_line
            current_new_line += 1
        elif raw.startswith(" "):
            current_new_line += 1
        elif raw.startswith("-"):
            continue

    flush()
    return hunks


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
