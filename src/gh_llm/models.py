from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True)
class PullRequestRef:
    owner: str
    name: str
    number: int


@dataclass(frozen=True)
class PullRequestMeta:
    ref: PullRequestRef
    title: str
    url: str
    author: str
    state: str
    is_draft: bool
    body: str
    updated_at: str


@dataclass(frozen=True)
class PageInfo:
    has_next_page: bool
    has_previous_page: bool
    start_cursor: str | None
    end_cursor: str | None


@dataclass(frozen=True)
class TimelineEvent:
    timestamp: datetime
    kind: str
    actor: str
    summary: str
    source_id: str
    full_text: str | None = None
    is_truncated: bool = False
    resolved_hidden_count: int = 0


@dataclass(frozen=True)
class TimelinePage:
    items: list[TimelineEvent]
    total_count: int
    page_info: PageInfo


@dataclass
class TimelineContext:
    owner: str
    name: str
    number: int
    page_size: int
    total_count: int
    total_pages: int
    title: str
    url: str
    author: str
    state: str
    is_draft: bool
    body: str
    updated_at: str
    forward_after_by_page: dict[int, str | None] = field(default_factory=lambda: cast("dict[int, str | None]", {}))
    backward_before_by_page: dict[int, str | None] = field(default_factory=lambda: cast("dict[int, str | None]", {}))

    def to_dict(self) -> dict[str, object]:
        return {
            "owner": self.owner,
            "name": self.name,
            "number": self.number,
            "page_size": self.page_size,
            "total_count": self.total_count,
            "total_pages": self.total_pages,
            "title": self.title,
            "url": self.url,
            "author": self.author,
            "state": self.state,
            "is_draft": self.is_draft,
            "body": self.body,
            "updated_at": self.updated_at,
            "forward_after_by_page": {str(k): v for k, v in self.forward_after_by_page.items()},
            "backward_before_by_page": {str(k): v for k, v in self.backward_before_by_page.items()},
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> TimelineContext:
        return cls(
            owner=_as_str(value.get("owner"), "unknown"),
            name=_as_str(value.get("name"), "unknown"),
            number=_as_int(value.get("number"), 0),
            page_size=_as_int(value.get("page_size"), 8),
            total_count=_as_int(value.get("total_count"), 0),
            total_pages=_as_int(value.get("total_pages"), 1),
            title=_as_str(value.get("title"), ""),
            url=_as_str(value.get("url"), ""),
            author=_as_str(value.get("author"), "unknown"),
            state=_as_str(value.get("state"), "UNKNOWN"),
            is_draft=bool(value.get("is_draft")),
            body=_as_str(value.get("body"), ""),
            updated_at=_as_str(value.get("updated_at"), ""),
            forward_after_by_page={
                int(k): None if v is None else str(v)
                for k, v in _ensure_dict(value.get("forward_after_by_page")).items()
            },
            backward_before_by_page={
                int(k): None if v is None else str(v)
                for k, v in _ensure_dict(value.get("backward_before_by_page")).items()
            },
        )


def _ensure_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        raw = cast("dict[object, object]", value)
        return {str(k): v for k, v in raw.items()}
    return {}


def _as_int(value: object, default: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _as_str(value: object, default: str) -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)
