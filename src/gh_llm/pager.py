from __future__ import annotations

import math
from typing import TYPE_CHECKING

from gh_llm.models import TimelineContext

if TYPE_CHECKING:
    from gh_llm.github_api import GitHubClient
    from gh_llm.models import PullRequestMeta, TimelinePage

DEFAULT_PAGE_SIZE = 8


class TimelinePager:
    def __init__(self, client: GitHubClient) -> None:
        self._client = client

    def build_initial(
        self, meta: PullRequestMeta, page_size: int, *, show_resolved_details: bool = False
    ) -> tuple[TimelineContext, TimelinePage, TimelinePage | None]:
        _validate_page_size(page_size)

        first_page = self._client.fetch_timeline_forward(
            meta.ref, page_size=page_size, after=None, show_resolved_details=show_resolved_details
        )
        total_count = first_page.total_count
        total_pages = _page_count(total_count, page_size)

        context = TimelineContext(
            owner=meta.ref.owner,
            name=meta.ref.name,
            number=meta.ref.number,
            page_size=page_size,
            total_count=total_count,
            total_pages=total_pages,
            title=meta.title,
            url=meta.url,
            author=meta.author,
            state=meta.state,
            is_draft=meta.is_draft,
            body=meta.body,
            updated_at=meta.updated_at,
            forward_after_by_page={1: None},
            backward_before_by_page={total_pages: None},
        )
        self._remember_forward(context, page=1, cursor_used=None, page_result=first_page)

        if total_pages == 1:
            return context, first_page, None

        last_page_size = _page_size_for_page(
            page=total_pages, total_count=total_count, total_pages=total_pages, default_size=page_size
        )
        last_page = self._client.fetch_timeline_backward(
            meta.ref, page_size=last_page_size, before=None, show_resolved_details=show_resolved_details
        )
        self._remember_backward(context, page=total_pages, cursor_used=None, page_result=last_page)
        return context, first_page, last_page

    def fetch_page(
        self, meta: PullRequestMeta, context: TimelineContext, page: int, *, show_resolved_details: bool = False
    ) -> TimelinePage:
        _validate_page(page, context.total_pages)

        from_start = page - 1
        from_end = context.total_pages - page
        if from_start <= from_end:
            return self._walk_forward(meta, context, page, show_resolved_details=show_resolved_details)
        return self._walk_backward(meta, context, page, show_resolved_details=show_resolved_details)

    def _walk_forward(
        self, meta: PullRequestMeta, context: TimelineContext, target_page: int, *, show_resolved_details: bool
    ) -> TimelinePage:
        start_page = max(page for page in context.forward_after_by_page if page <= target_page)
        cursor = context.forward_after_by_page[start_page]

        page = start_page
        while True:
            result = self._client.fetch_timeline_forward(
                meta.ref, page_size=context.page_size, after=cursor, show_resolved_details=show_resolved_details
            )
            self._remember_forward(context, page=page, cursor_used=cursor, page_result=result)
            if page == target_page:
                return result
            cursor = result.page_info.end_cursor
            if cursor is None:
                raise RuntimeError("timeline forward cursor unexpectedly missing")
            page += 1

    def _walk_backward(
        self, meta: PullRequestMeta, context: TimelineContext, target_page: int, *, show_resolved_details: bool
    ) -> TimelinePage:
        start_page = min(page for page in context.backward_before_by_page if page >= target_page)
        cursor = context.backward_before_by_page[start_page]

        page = start_page
        while True:
            current_page_size = _page_size_for_page(
                page=page,
                total_count=context.total_count,
                total_pages=context.total_pages,
                default_size=context.page_size,
            )
            result = self._client.fetch_timeline_backward(
                meta.ref,
                page_size=current_page_size,
                before=cursor,
                show_resolved_details=show_resolved_details,
            )
            self._remember_backward(context, page=page, cursor_used=cursor, page_result=result)
            if page == target_page:
                return result
            cursor = result.page_info.start_cursor
            if cursor is None:
                raise RuntimeError("timeline backward cursor unexpectedly missing")
            page -= 1

    def _remember_forward(
        self, context: TimelineContext, page: int, cursor_used: str | None, page_result: TimelinePage
    ) -> None:
        context.forward_after_by_page[page] = cursor_used
        if page_result.page_info.has_next_page and page_result.page_info.end_cursor:
            context.forward_after_by_page[page + 1] = page_result.page_info.end_cursor

    def _remember_backward(
        self, context: TimelineContext, page: int, cursor_used: str | None, page_result: TimelinePage
    ) -> None:
        context.backward_before_by_page[page] = cursor_used
        if page_result.page_info.has_previous_page and page_result.page_info.start_cursor:
            context.backward_before_by_page[page - 1] = page_result.page_info.start_cursor


def _page_count(total: int, page_size: int) -> int:
    if total == 0:
        return 1
    return math.ceil(total / page_size)


def _validate_page(page: int, total_pages: int) -> None:
    if page < 1 or page > total_pages:
        raise ValueError(f"invalid page {page}, expected in 1..{total_pages}")


def _validate_page_size(page_size: int) -> None:
    if page_size <= 0:
        raise ValueError("page-size must be greater than 0")


def _page_size_for_page(page: int, total_count: int, total_pages: int, default_size: int) -> int:
    if page == total_pages:
        remainder = total_count % default_size
        if remainder != 0:
            return remainder
    return default_size
