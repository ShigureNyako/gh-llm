from __future__ import annotations

import json
from datetime import UTC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from string.templatelib import Template

    from gh_llm.models import TimelineContext, TimelineEvent, TimelinePage


def render_header(context: TimelineContext) -> list[str]:
    description = context.body.strip() or "(no description)"
    return [
        "---",
        f"pr: {context.number}",
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
        "## PR Description",
        *description.splitlines(),
        "",
    ]


def render_page(page_number: int, context: TimelineContext, page: TimelinePage) -> list[str]:
    lines = [f"## Timeline Page {page_number}/{context.total_pages}"]
    if not page.items:
        lines.append("(no timeline events)")
        return lines

    start_index = _page_start_index(page_number=page_number, context=context, page=page)
    for offset, item in enumerate(page.items):
        lines.extend(_render_item(index=start_index + offset, event=item, context=context))
    return lines


def render_expand_hints(context: TimelineContext, shown_pages: set[int]) -> list[str]:
    hidden_pages = [page for page in range(1, context.total_pages + 1) if page not in shown_pages]
    if not hidden_pages:
        if context.total_pages == 1:
            return ["Timeline fits on a single page."]
        return ["All timeline pages are already shown."]
    return []


def render_hidden_gap(context: TimelineContext, hidden_pages: list[int]) -> list[str]:
    if not hidden_pages:
        return []
    repo = f"{context.owner}/{context.name}"
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
                t"- `gh-llm pr timeline-expand {page} --pr {context.number} --repo {repo}`"
            )
            for page in hidden_pages
        ],
        "---",
    ]


def _render_item(index: int, event: TimelineEvent, context: TimelineContext) -> list[str]:
    timestamp = event.timestamp.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"{index}. [{timestamp}] {event.kind} by @{event.actor}"]
    lines.extend(_indent_block(event.summary))
    if event.resolved_hidden_count > 0:
        repo = f"{context.owner}/{context.name}"
        lines.append(
            f"   {event.resolved_hidden_count} resolved review comments are collapsed; "
            f"run `gh-llm pr review-expand {event.source_id} --pr {context.number} --repo {repo}`"
        )
    if event.is_truncated:
        lines.append(f"   run `gh-llm pr event {index}` for full content")
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
    lines.extend((event.full_text or event.summary).splitlines() or [event.summary])
    return lines


def _indent_block(text: str) -> list[str]:
    content_lines = text.splitlines() or [text]
    return [f"   {line}" for line in content_lines]
