from __future__ import annotations

import json
from datetime import UTC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from string.templatelib import Template

    from gh_llm.models import CheckItem, TimelineContext, TimelineEvent, TimelinePage


def render_header(context: TimelineContext) -> list[str]:
    description = context.body.strip() or "(no description)"
    repo = f"{context.owner}/{context.name}"
    is_issue = context.kind == "issue"
    key = "issue" if is_issue else "pr"
    noun_title = "Issue" if is_issue else "PR"
    description_tag = "issue_description" if is_issue else "pr_description"
    description_title = "## Issue Description" if is_issue else "## PR Description"
    edit_cmd = (
        f"gh issue edit {context.number} --repo {repo} --body '<issue_description_markdown>'"
        if is_issue
        else f"gh pr edit {context.number} --repo {repo} --body '<pr_description_markdown>'"
    )
    body_placeholder = (
        "⌨ issue_body: '<issue_description_markdown>'"
        if is_issue
        else "⌨ pr_body: '<pr_description_markdown>'"
    )
    return [
        "---",
        f"{key}: {context.number}",
        f"repo: {context.owner}/{context.name}",
        f"title: {json.dumps(context.title, ensure_ascii=False)}",
        f"url: {context.url}",
        f"author: {context.author}",
        f"state: {context.state}",
        f"draft: {str(context.is_draft).lower()}",
        f"updated_at: {context.updated_at}",
        f"timeline_events: {context.total_count}",
        f"page_size: {context.page_size}",
        f"total_pages: {context.total_pages}",
        "---",
        "",
        *(
            [
                "## Diff Actions",
                f"Δ PR diff: `gh pr diff {context.number} --repo {repo}`",
                "",
            ]
            if not is_issue
            else []
        ),
        description_title,
        *([f"Reactions: {context.pr_reactions_summary}"] if context.pr_reactions_summary else []),
        *(
            [
                body_placeholder,
                f"⏎ Edit {noun_title} description via gh: `{edit_cmd}`",
            ]
            if context.can_edit_pr_body
            else []
        ),
        f"<{description_tag}>",
        *description.splitlines(),
        f"</{description_tag}>",
        "",
    ]


def render_page(page_number: int, context: TimelineContext, page: TimelinePage) -> list[str]:
    lines = [f"## Timeline Page {page_number}/{context.total_pages}"]
    if not page.items:
        lines.append("(no timeline events)")
        return lines

    start_index = _page_start_index(page_number=page_number, context=context, page=page)
    for offset, item in enumerate(page.items):
        lines.extend(
            _render_item(index=start_index + offset, event=item, context=context, command_group=context.kind)
        )
    return lines


def render_expand_hints(context: TimelineContext, shown_pages: set[int]) -> list[str]:
    hidden_pages = [page for page in range(1, context.total_pages + 1) if page not in shown_pages]
    if not hidden_pages:
        if context.total_pages == 1:
            return ["Timeline fits on a single page."]
        return ["All timeline pages are already shown."]
    return []


def render_pr_actions(context: TimelineContext) -> list[str]:
    repo = f"{context.owner}/{context.name}"
    return [
        "",
        "---",
        "PR actions:",
        "⌨ comment_body: '<comment_body>'",
        f"⏎ Comment via gh: `gh pr comment {context.number} --repo {repo} --body '<comment_body>'`",
        f"⏎ Close PR via gh: `gh pr close {context.number} --repo {repo}`",
        "⌨ labels_csv: '<label1>,<label2>'",
        f"⏎ Add labels via gh: `gh pr edit {context.number} --repo {repo} --add-label '<label1>,<label2>'`",
        f"⏎ Remove labels via gh: `gh pr edit {context.number} --repo {repo} --remove-label '<label1>,<label2>'`",
        "⌨ reviewers_csv: '<reviewer1>,<reviewer2>'",
        f"⏎ Request review via gh: `gh pr edit {context.number} --repo {repo} --add-reviewer '<reviewer1>,<reviewer2>'`",
        "⌨ assignees_csv: '<assignee1>,<assignee2>'",
        f"⏎ Assign via gh: `gh pr edit {context.number} --repo {repo} --add-assignee '<assignee1>,<assignee2>'`",
        "---",
    ]


def render_issue_actions(context: TimelineContext) -> list[str]:
    repo = f"{context.owner}/{context.name}"
    return [
        "",
        "---",
        "Issue actions:",
        "⌨ comment_body: '<comment_body>'",
        f"⏎ Comment via gh: `gh issue comment {context.number} --repo {repo} --body '<comment_body>'`",
        f"⏎ Close issue via gh: `gh issue close {context.number} --repo {repo}`",
        "⌨ labels_csv: '<label1>,<label2>'",
        f"⏎ Add labels via gh: `gh issue edit {context.number} --repo {repo} --add-label '<label1>,<label2>'`",
        f"⏎ Remove labels via gh: `gh issue edit {context.number} --repo {repo} --remove-label '<label1>,<label2>'`",
        "⌨ assignees_csv: '<assignee1>,<assignee2>'",
        f"⏎ Assign via gh: `gh issue edit {context.number} --repo {repo} --add-assignee '<assignee1>,<assignee2>'`",
        "---",
    ]


def render_checks_section(
    *,
    context: TimelineContext,
    checks: list[CheckItem],
    show_all: bool,
    is_open: bool,
) -> list[str]:
    repo = f"{context.owner}/{context.name}"
    if not is_open:
        return [
            "## Checks",
            f"Closed PR: checks are hidden by default. ⏎ run `gh-llm pr checks --pr {context.number} --repo {repo} --all`",
            "",
        ]

    visible = checks if show_all else [item for item in checks if not item.passed]
    hidden_count = max(0, len(checks) - len(visible))
    lines = ["## Checks"]
    if not visible:
        if checks:
            lines.append("All checks passed.")
        else:
            lines.append("(no checks found)")
    else:
        for idx, item in enumerate(visible, start=1):
            lines.append(f"{idx}. [{item.status}] {item.name} ({item.kind})")
            if item.run_id is not None:
                if item.job_id is not None:
                    lines.append(
                        f"   ⏎ details: `gh run view {item.run_id} --job {item.job_id} --repo {repo}`"
                    )
                    lines.append(
                        f"   ⏎ logs: `gh run view {item.run_id} --job {item.job_id} --log --repo {repo}`"
                    )
                else:
                    lines.append(
                        f"   ⏎ details: `gh run view {item.run_id} --repo {repo}`"
                    )
                    lines.append(
                        f"   ⏎ logs: `gh run view {item.run_id} --log --repo {repo}`"
                    )
            elif item.details_url:
                lines.append(f"   ⏎ details: `{item.details_url}`")
    if show_all:
        lines.append(
            f"⏎ show only non-passed: `gh-llm pr checks --pr {context.number} --repo {repo}`"
        )
    elif hidden_count > 0:
        lines.append(
            f"{hidden_count} passed checks hidden. ⏎ show all: `gh-llm pr checks --pr {context.number} --repo {repo} --all`"
        )
    else:
        lines.append(
            f"⏎ show all: `gh-llm pr checks --pr {context.number} --repo {repo} --all`"
        )
    lines.append("")
    return lines


def render_hidden_gap(context: TimelineContext, hidden_pages: list[int]) -> list[str]:
    if not hidden_pages:
        return []
    repo = f"{context.owner}/{context.name}"
    selector_name = "issue" if context.kind == "issue" else "pr"
    hidden_label = (
        f"Hidden timeline page: {hidden_pages[0]}"
        if len(hidden_pages) == 1
        else f"Hidden timeline pages: {hidden_pages[0]}..{hidden_pages[-1]}"
    )
    return [
        "---",
        hidden_label,
        *[
            _render_template(
                t"- ⏎ `gh-llm {context.kind} timeline-expand {page} --{selector_name} {context.number} --repo {repo}`"
            )
            for page in hidden_pages
        ],
        "---",
    ]


def _render_item(index: int, event: TimelineEvent, context: TimelineContext, command_group: str) -> list[str]:
    timestamp = event.timestamp.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    selector_name = "issue" if command_group == "issue" else "pr"
    lines = [f"{index}. [{timestamp}] {event.kind} by @{event.actor}"]
    if event.kind == "comment":
        lines.append("   Comment:")
        lines.extend(_indented_tag_block("comment", event.summary, indent="   "))
        if event.reactions_summary:
            lines.append(f"   Reactions: {event.reactions_summary}")
        if event.editable_comment_id:
            lines.append(f"   ◌ comment_id: {event.editable_comment_id}")
            lines.append("   ⌨ comment_body: '<comment_body>'")
            lines.append(
                f"   ⏎ Edit comment via gh-llm: `gh-llm {command_group} comment-edit {event.editable_comment_id} --body '<comment_body>' --{selector_name} {context.number} --repo {context.owner}/{context.name}`"
            )
    else:
        lines.extend(_indent_block(event.summary))
    if event.resolved_hidden_count > 0:
        repo = f"{context.owner}/{context.name}"
        lines.append(
            f"   {event.resolved_hidden_count} resolved review comments are collapsed; "
            f"⏎ run `gh-llm pr review-expand {event.source_id} --pr {context.number} --repo {repo}`"
        )
    if event.is_truncated:
        lines.append(f"   ⏎ run `gh-llm {command_group} event {index}` for full content")
    if event.kind == "push/commit":
        lines.append(
            f"   Δ commit diff: `gh api repos/{context.owner}/{context.name}/commits/{event.source_id} -H 'Accept: application/vnd.github.v3.diff'`"
        )
    return lines


def _render_template(template: Template) -> str:
    rendered: list[str] = []
    for index, segment in enumerate(template.strings):
        rendered.append(segment)
        if index < len(template.interpolations):
            rendered.append(str(template.interpolations[index].value))
    return "".join(rendered)


def _page_start_index(page_number: int, context: TimelineContext, page: TimelinePage) -> int:
    if page_number == context.total_pages and context.total_count % context.page_size != 0:
        return max(1, context.total_count - len(page.items) + 1)
    return (page_number - 1) * context.page_size + 1


def render_event_detail(index: int, event: TimelineEvent) -> list[str]:
    timestamp = event.timestamp.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"## Timeline Event {index}",
        f"- Type: {event.kind}",
        f"- Actor: @{event.actor}",
        f"- Time: {timestamp}",
        f"- Source ID: {event.source_id}",
        "",
    ]
    detail = event.full_text or event.summary
    if event.kind == "comment":
        lines.extend(["<comment>", *detail.splitlines(), "</comment>"])
        if event.reactions_summary:
            lines.append(f"Reactions: {event.reactions_summary}")
    else:
        lines.extend(detail.splitlines() or [event.summary])
    return lines


def _indent_block(text: str) -> list[str]:
    content_lines = text.splitlines() or [text]
    return [f"   {line}" for line in content_lines]


def _indented_tag_block(tag: str, content: str, indent: str = "") -> list[str]:
    out = [f"{indent}<{tag}>"]
    out.extend(f"{indent}{line}" for line in content.splitlines())
    out.append(f"{indent}</{tag}>")
    return out
