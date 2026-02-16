from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, Any

from gh_llm import __version__, cli, github_api

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


class FakeCompletedProcess:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


class GhResponder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, cmd: list[str], *, check: bool, capture_output: bool, text: bool) -> FakeCompletedProcess:
        del check, capture_output, text
        self.calls.append(cmd)

        if cmd[:3] == ["gh", "pr", "view"]:
            return FakeCompletedProcess(
                json.dumps(
                    {
                        "number": 77928,
                        "title": "Timeline test",
                        "url": "https://github.com/PaddlePaddle/Paddle/pull/77928",
                        "author": {"login": "ShigureNyako"},
                        "state": "OPEN",
                        "isDraft": False,
                        "body": "This is PR description",
                    }
                )
            )

        if cmd[:3] != ["gh", "api", "graphql"]:
            return FakeCompletedProcess("", returncode=1, stderr="unexpected command")

        query = _extract_form(cmd, "query")
        first = _extract_field_int(cmd, "pageSize")
        after = _extract_field(cmd, "after")
        before = _extract_field(cmd, "before")

        if "reviewThreads(first:100" in query:
            payload = _review_threads_payload(after=after)
            return FakeCompletedProcess(json.dumps(payload))

        if "addPullRequestReviewThreadReply" in query:
            return FakeCompletedProcess(
                json.dumps(
                    {
                        "data": {
                            "addPullRequestReviewThreadReply": {
                                "comment": {"id": "PRRC_reply_1"}
                            }
                        }
                    }
                )
            )

        if "unresolveReviewThread" in query:
            return FakeCompletedProcess(
                json.dumps(
                    {
                        "data": {
                            "unresolveReviewThread": {
                                "thread": {"id": "PRRT_mock_2", "isResolved": False}
                            }
                        }
                    }
                )
            )

        if "resolveReviewThread" in query:
            return FakeCompletedProcess(
                json.dumps(
                    {
                        "data": {
                            "resolveReviewThread": {
                                "thread": {"id": "PRRT_mock_1", "isResolved": True}
                            }
                        }
                    }
                )
            )

        if "timelineItems(first:" in query:
            payload = _forward_page_payload(page_size=first, after=after)
            return FakeCompletedProcess(json.dumps(payload))

        payload = _backward_page_payload(page_size=first, before=before)
        return FakeCompletedProcess(json.dumps(payload))


def test_version() -> None:
    assert __version__ == "0.1.0"


def test_parse_event_indexes_batch() -> None:
    assert cli.parse_event_indexes(["5,11", "8-6"]) == [5, 6, 7, 8, 11]


def test_parse_review_ids_batch() -> None:
    assert cli.parse_review_ids(["PRR_a,PRR_b", "PRR_b", "PRR_c"]) == ["PRR_a", "PRR_b", "PRR_c"]


def test_view_and_expand_use_real_cursor_pagination(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    responder = GhResponder()
    monkeypatch.setattr(github_api.subprocess, "run", responder.run)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    code = cli.run(["pr", "view", "77928", "--repo", "PaddlePaddle/Paddle", "--page-size", "2"])
    assert code == 0

    out = capsys.readouterr().out
    assert "## PR Description" in out
    assert "This is PR description" in out
    assert "## Diff Actions" in out
    assert "Δ PR diff: `gh pr diff 77928 --repo PaddlePaddle/Paddle`" in out
    assert "## Timeline Page 1/4" in out
    assert "## Timeline Page 3/4" in out
    assert "## Timeline Page 4/4" in out
    assert "Hidden timeline page: 2" in out
    assert "---" in out
    assert "gh-llm pr timeline-expand 2 --pr 77928 --repo PaddlePaddle/Paddle" in out
    assert "PR actions:" in out
    assert "gh pr comment 77928 --repo PaddlePaddle/Paddle --body '<comment_body>'" in out
    assert "gh pr close 77928 --repo PaddlePaddle/Paddle" in out
    assert "gh pr edit 77928 --repo PaddlePaddle/Paddle --add-label '<label1>,<label2>'" in out
    assert "gh pr edit 77928 --repo PaddlePaddle/Paddle --remove-label '<label1>,<label2>'" in out
    assert "gh pr edit 77928 --repo PaddlePaddle/Paddle --add-reviewer '<reviewer1>,<reviewer2>'" in out
    assert "gh pr edit 77928 --repo PaddlePaddle/Paddle --add-assignee '<assignee1>,<assignee2>'" in out
    assert "link:" not in out

    pre_expand_calls = len(responder.calls)
    code = cli.run(
        ["pr", "timeline-expand", "2", "--pr", "77928", "--repo", "PaddlePaddle/Paddle", "--page-size", "2"]
    )
    assert code == 0

    out = capsys.readouterr().out
    assert "## Timeline Page 2/4" in out
    assert "commit 2" in out
    assert "Δ commit diff: `gh api repos/PaddlePaddle/Paddle/commits/oid-2 -H 'Accept: application/vnd.github.v3.diff'`" in out

    code = cli.run(
        ["pr", "timeline-expand", "3", "--pr", "77928", "--repo", "PaddlePaddle/Paddle", "--page-size", "2"]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "## Timeline Page 3/4" in out
    assert "Review comments (1/2 shown):" in out
    assert "Thread[1] PRRT_mock_1" in out
    assert "[1] python/test_file.py:L21 by @reviewer" in out
    assert "[2] python/test_file.py:L22 by @reviewer" not in out
    assert "Diff Hunk:" in out
    assert "1 resolved review comments are collapsed;" in out
    assert "gh-llm pr review-expand PRR_mock --pr 77928 --repo PaddlePaddle/Paddle" in out
    assert "thread_id: PRRT_mock_1" in out
    assert "Reply via gh-llm:" in out
    assert "Resolve via gh-llm:" in out
    assert "Unresolve via gh-llm:" not in out
    assert "Reply via gh: `gh api graphql" not in out
    assert "Resolve via gh: `gh api graphql" not in out

    code = cli.run(
        ["pr", "review-expand", "PRR_mock", "--pr", "77928", "--repo", "PaddlePaddle/Paddle", "--page-size", "2"]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "## Timeline Event" in out
    assert "Suggested Change:" in out
    assert "@@ python/test_file.py:L22 @@" in out
    assert "+new_api_call()" in out
    assert "Unresolve via gh-llm:" in out

    code = cli.run(
        [
            "pr",
            "thread-reply",
            "PRRT_mock_1",
            "--body",
            "please update",
            "--pr",
            "77928",
            "--repo",
            "PaddlePaddle/Paddle",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "thread: PRRT_mock_1" in out
    assert "reply_comment_id: PRRC_reply_1" in out
    assert "status: replied" in out

    code = cli.run(
        [
            "pr",
            "thread-resolve",
            "PRRT_mock_1",
            "--pr",
            "77928",
            "--repo",
            "PaddlePaddle/Paddle",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "thread: PRRT_mock_1" in out
    assert "status: resolved" in out

    code = cli.run(
        [
            "pr",
            "thread-unresolve",
            "PRRT_mock_2",
            "--pr",
            "77928",
            "--repo",
            "PaddlePaddle/Paddle",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "thread: PRRT_mock_2" in out
    assert "status: unresolved" in out

    expand_calls = responder.calls[pre_expand_calls:]
    assert any(call[:3] == ["gh", "pr", "view"] for call in expand_calls)
    assert any(call[:3] == ["gh", "api", "graphql"] for call in expand_calls)

    code = cli.run(["pr", "event", "2", "--pr", "77928", "--repo", "PaddlePaddle/Paddle", "--page-size", "2"])
    assert code == 0
    out = capsys.readouterr().out
    assert "## Timeline Event 2" in out
    assert "END_MARKER" in out


def _extract_form(cmd: list[str], key: str) -> str:
    for idx, token in enumerate(cmd):
        if token == "-f" and idx + 1 < len(cmd):
            candidate = cmd[idx + 1]
            if candidate.startswith(f"{key}="):
                return candidate.split("=", 1)[1]
    return ""


def _extract_field(cmd: list[str], key: str) -> str | None:
    for idx, token in enumerate(cmd):
        if token == "-F" and idx + 1 < len(cmd):
            candidate = cmd[idx + 1]
            if candidate.startswith(f"{key}="):
                return candidate.split("=", 1)[1]
    return None


def _extract_field_int(cmd: list[str], key: str) -> int:
    raw = _extract_field(cmd, key)
    if raw is None:
        return 0
    return int(raw)


def _forward_page_payload(page_size: int, after: str | None) -> dict[str, Any]:
    events = _events()
    total_pages = math.ceil(len(events) / TEST_BASE_PAGE_SIZE)
    page_map = {None: 1, **{f"cursor-{idx}": idx + 1 for idx in range(1, total_pages)}}
    page = page_map[after]
    start, canonical_end = _page_bounds(page=page, total_count=len(events), base_page_size=TEST_BASE_PAGE_SIZE)
    end = min(start + page_size, canonical_end)
    chunk = events[start:end]

    end_cursor = f"cursor-{page}" if page < total_pages else None
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "timelineItems": {
                        "totalCount": len(events),
                        "pageInfo": {
                            "hasNextPage": page < total_pages,
                            "hasPreviousPage": page > 1,
                            "startCursor": f"back-{page - 1}" if page > 1 else None,
                            "endCursor": end_cursor,
                        },
                        "nodes": chunk,
                    }
                }
            }
        }
    }


def _backward_page_payload(page_size: int, before: str | None) -> dict[str, Any]:
    events = _events()
    total_pages = math.ceil(len(events) / TEST_BASE_PAGE_SIZE)
    page_map = {None: total_pages, **{f"back-{idx}": idx for idx in range(1, total_pages)}}
    page = page_map[before]
    start, canonical_end = _page_bounds(page=page, total_count=len(events), base_page_size=TEST_BASE_PAGE_SIZE)
    end = min(start + page_size, canonical_end)
    chunk = events[start:end]

    start_cursor = f"back-{page - 1}" if page > 1 else None
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "timelineItems": {
                        "totalCount": len(events),
                        "pageInfo": {
                            "hasNextPage": page < total_pages,
                            "hasPreviousPage": page > 1,
                            "startCursor": start_cursor,
                            "endCursor": f"cursor-{page}" if page < total_pages else None,
                        },
                        "nodes": chunk,
                    }
                }
            }
        }
    }


def _review_threads_payload(after: str | None) -> dict[str, Any]:
    if after is not None:
        return {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                            "nodes": [],
                        }
                    }
                }
            }
        }
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [
                            {
                                "id": "PRRT_mock_2",
                                "isResolved": True,
                                "comments": {
                                    "nodes": [
                                        {
                                            "id": "rc2",
                                            "path": "python/test_file.py",
                                            "body": "```suggestion\nnew_api_call()\n```",
                                            "line": 22,
                                            "originalLine": 22,
                                            "startLine": None,
                                            "originalStartLine": None,
                                            "diffHunk": "@@ -22,1 +22,1 @@\n-old_api_call()",
                                            "createdAt": "2026-02-14T14:50:02Z",
                                            "author": {"login": "reviewer"},
                                            "pullRequestReview": {"id": "PRR_mock"},
                                        }
                                    ]
                                },
                            },
                            {
                                "id": "PRRT_mock_1",
                                "isResolved": False,
                                "comments": {
                                    "nodes": [
                                        {
                                            "id": "rc1",
                                            "path": "python/test_file.py",
                                            "body": "use clear variable names",
                                            "line": 21,
                                            "originalLine": 21,
                                            "startLine": None,
                                            "originalStartLine": None,
                                            "diffHunk": "@@ -20,2 +20,2 @@\n-old_name\n+new_name",
                                            "createdAt": "2026-02-14T14:50:01Z",
                                            "author": {"login": "reviewer"},
                                            "pullRequestReview": {"id": "PRR_mock"},
                                        }
                                    ]
                                },
                            }
                        ],
                    }
                }
            }
        }
    }


def _events() -> list[dict[str, Any]]:
    long_comment = ("LONG_TEXT " * 220) + "END_MARKER"
    return [
        {
            "__typename": "IssueComment",
            "id": "c1",
            "url": "https://example.com/c1",
            "createdAt": "2026-02-14T14:31:36Z",
            "body": long_comment,
            "author": {"login": "bot"},
        },
        {
            "__typename": "PullRequestCommit",
            "commit": {
                "oid": "oid-1",
                "committedDate": "2026-02-14T14:31:11Z",
                "messageHeadline": "commit 1",
                "authors": {"nodes": [{"name": "A", "user": {"login": "a"}}]},
            },
        },
        {
            "__typename": "PullRequestCommit",
            "commit": {
                "oid": "oid-2",
                "committedDate": "2026-02-14T14:43:46Z",
                "messageHeadline": "commit 2",
                "authors": {"nodes": [{"name": "B", "user": {"login": "b"}}]},
            },
        },
        {
            "__typename": "IssueComment",
            "id": "c2",
            "url": "https://example.com/c2",
            "createdAt": "2026-02-14T14:44:36Z",
            "body": "comment 2",
            "author": {"login": "user2"},
        },
        {
            "__typename": "PullRequestReview",
            "id": "PRR_mock",
            "submittedAt": "2026-02-14T14:51:00Z",
            "state": "APPROVED",
            "body": "lgtm",
            "author": {"login": "reviewer"},
        },
        {
            "__typename": "MergedEvent",
            "id": "m1",
            "createdAt": "2026-02-14T15:10:00Z",
            "actor": {"login": "merger"},
        },
        {
            "__typename": "IssueComment",
            "id": "c3",
            "url": "https://example.com/c3",
            "createdAt": "2026-02-14T15:11:00Z",
            "body": "tail event",
            "author": {"login": "tail"},
        },
    ]


TEST_BASE_PAGE_SIZE = 2


def _page_bounds(page: int, total_count: int, base_page_size: int) -> tuple[int, int]:
    start = (page - 1) * base_page_size
    end = min(start + base_page_size, total_count)
    return start, end
