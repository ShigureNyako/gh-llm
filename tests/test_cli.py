from __future__ import annotations

import json
import math
import sys
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
        self.pending_review_id: str | None = None

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
                        "reactionGroups": [{"content": "ROCKET", "users": {"totalCount": 1}}],
                    }
                )
            )

        if cmd[:3] == ["gh", "pr", "diff"]:
            return FakeCompletedProcess(
                "\n".join(
                    [
                        "diff --git a/python/test_file.py b/python/test_file.py",
                        "index 1111111..2222222 100644",
                        "--- a/python/test_file.py",
                        "+++ b/python/test_file.py",
                        "@@ -20,2 +20,2 @@ def demo():",
                        "-old_api_call()",
                        "+new_api_call()",
                    ]
                )
                + "\n"
            )

        if cmd[:3] == ["gh", "issue", "view"]:
            return FakeCompletedProcess(
                json.dumps(
                    {
                        "number": 77924,
                        "title": "Issue timeline test",
                        "url": "https://github.com/PaddlePaddle/Paddle/issues/77924",
                        "author": {"login": "ShigureNyako"},
                        "state": "OPEN",
                        "body": "This is issue description",
                        "updatedAt": "2026-02-16T09:00:00Z",
                        "reactionGroups": [{"content": "EYES", "users": {"totalCount": 1}}],
                    }
                )
            )

        if cmd[:3] == ["gh", "api", "user"]:
            return FakeCompletedProcess(json.dumps({"login": "ShigureNyako"}))

        if cmd[:3] != ["gh", "api", "graphql"]:
            return FakeCompletedProcess("", returncode=1, stderr="unexpected command")

        query = _extract_form(cmd, "query")
        first = _extract_field_int(cmd, "pageSize")
        after = _extract_field(cmd, "after")
        before = _extract_field(cmd, "before")

        if "reviewThreads(first:100" in query:
            payload = _review_threads_payload(after=after)
            return FakeCompletedProcess(json.dumps(payload))

        if "statusCheckRollup" in query:
            return FakeCompletedProcess(json.dumps(_checks_payload()))

        if "addPullRequestReviewThreadReply" in query:
            return FakeCompletedProcess(
                json.dumps({"data": {"addPullRequestReviewThreadReply": {"comment": {"id": "PRRC_reply_1"}}}})
            )

        if "addPullRequestReviewThread(input:" in query:
            self.pending_review_id = "PRR_pending_1"
            return FakeCompletedProcess(
                json.dumps(
                    {
                        "data": {
                            "addPullRequestReviewThread": {
                                "thread": {
                                    "id": "PRRT_new_1",
                                    "comments": {"nodes": [{"id": "PRRC_new_1"}]},
                                }
                            }
                        }
                    }
                )
            )

        if "addPullRequestReview(input:" in query:
            return FakeCompletedProcess(
                json.dumps(
                    {
                        "data": {
                            "addPullRequestReview": {
                                "pullRequestReview": {
                                    "id": "PRR_new_1",
                                    "state": "PENDING",
                                }
                            }
                        }
                    }
                )
            )

        if "reviews(last:50)" in query:
            nodes: list[dict[str, Any]] = []
            if self.pending_review_id is not None:
                nodes.append(
                    {
                        "id": self.pending_review_id,
                        "state": "PENDING",
                        "author": {"login": "ShigureNyako"},
                    }
                )
            return FakeCompletedProcess(
                json.dumps({"data": {"repository": {"pullRequest": {"reviews": {"nodes": nodes}}}}})
            )

        if "submitPullRequestReview(input:" in query:
            review_id = self.pending_review_id or "PRR_pending_1"
            self.pending_review_id = None
            return FakeCompletedProcess(
                json.dumps(
                    {
                        "data": {
                            "submitPullRequestReview": {
                                "pullRequestReview": {
                                    "id": review_id,
                                    "state": "COMMENTED",
                                }
                            }
                        }
                    }
                )
            )

        if "pullRequest(number:$number){" in query and "id" in query and "timelineItems" not in query:
            return FakeCompletedProcess(
                json.dumps(
                    {
                        "data": {
                            "repository": {
                                "pullRequest": {
                                    "id": "PR_kwDOA-qtos5xxxx",
                                }
                            }
                        }
                    }
                )
            )

        if "updatePullRequestReviewComment" in query:
            return FakeCompletedProcess(
                json.dumps(
                    {"data": {"updatePullRequestReviewComment": {"pullRequestReviewComment": {"id": "PRRC_self_1"}}}}
                )
            )

        if "updateIssueComment" in query:
            return FakeCompletedProcess(json.dumps({"data": {"updateIssueComment": {"issueComment": {"id": "c3"}}}}))

        if "unresolveReviewThread" in query:
            return FakeCompletedProcess(
                json.dumps({"data": {"unresolveReviewThread": {"thread": {"id": "PRRT_mock_2", "isResolved": False}}}})
            )

        if "resolveReviewThread" in query:
            return FakeCompletedProcess(
                json.dumps({"data": {"resolveReviewThread": {"thread": {"id": "PRRT_mock_1", "isResolved": True}}}})
            )

        if "timelineItems(first:" in query:
            if "issue(number:$number)" in query:
                payload = _issue_forward_page_payload(page_size=first, after=after)
                return FakeCompletedProcess(json.dumps(payload))
            payload = _forward_page_payload(page_size=first, after=after)
            return FakeCompletedProcess(json.dumps(payload))

        if "issue(number:$number)" in query:
            payload = _issue_backward_page_payload(page_size=first, before=before)
            return FakeCompletedProcess(json.dumps(payload))
        payload = _backward_page_payload(page_size=first, before=before)
        return FakeCompletedProcess(json.dumps(payload))


def test_version() -> None:
    assert __version__ == "0.1.3"


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
    assert "## Description" in out
    assert "This is PR description" in out
    assert "Reactions: 🚀 x1" in out
    assert "gh pr edit 77928 --repo PaddlePaddle/Paddle --body '<pr_description_markdown>'" in out
    assert "Δ PR diff: `gh pr diff 77928 --repo PaddlePaddle/Paddle`" in out
    assert "## Timeline Page 1/4" in out
    assert "Reactions: 👍 x2" in out
    assert "## Timeline Page 3/4" in out
    assert "## Timeline Page 4/4" in out
    assert "Hidden timeline page: 2" in out
    assert "---" in out
    assert "gh-llm pr timeline-expand 2 --pr 77928 --repo PaddlePaddle/Paddle" in out
    assert "## Actions" in out
    assert "## Checks" in out
    assert "[IN_PROGRESS/NONE] unit-tests (check-run)" in out
    assert "passed checks hidden." in out
    assert "gh pr comment 77928 --repo PaddlePaddle/Paddle --body '<comment_body>'" in out
    assert "gh pr close 77928 --repo PaddlePaddle/Paddle" in out
    assert "gh pr edit 77928 --repo PaddlePaddle/Paddle --add-label '<label1>,<label2>'" in out
    assert "gh pr edit 77928 --repo PaddlePaddle/Paddle --remove-label '<label1>,<label2>'" in out
    assert "gh pr edit 77928 --repo PaddlePaddle/Paddle --add-reviewer '<reviewer1>,<reviewer2>'" in out
    assert "gh pr edit 77928 --repo PaddlePaddle/Paddle --add-assignee '<assignee1>,<assignee2>'" in out
    assert "link:" not in out
    assert (
        "Edit comment via gh-llm: `gh-llm pr comment-edit c3 --body '<comment_body>' --pr 77928 --repo PaddlePaddle/Paddle`"
        in out
    )

    pre_expand_calls = len(responder.calls)
    code = cli.run(["pr", "timeline-expand", "2", "--pr", "77928", "--repo", "PaddlePaddle/Paddle", "--page-size", "2"])
    assert code == 0

    out = capsys.readouterr().out
    assert "## Timeline Page 2/4" in out
    assert "commit 2" in out
    assert (
        "Δ commit diff: `gh api repos/PaddlePaddle/Paddle/commits/oid-2 -H 'Accept: application/vnd.github.v3.diff'`"
        in out
    )

    code = cli.run(["pr", "timeline-expand", "3", "--pr", "77928", "--repo", "PaddlePaddle/Paddle", "--page-size", "2"])
    assert code == 0
    out = capsys.readouterr().out
    assert "## Timeline Page 3/4" in out
    assert "(review hidden: outdated)" in out
    assert "Review comments (1/3 shown):" not in out
    assert "Thread[1] PRRT_mock_1" not in out
    assert "1 resolved review comments are collapsed;" not in out
    assert "1 hidden review comments are collapsed (reason: outdated);" in out
    assert "gh-llm pr review-expand PRR_mock --pr 77928 --repo PaddlePaddle/Paddle" in out
    assert "thread_id: PRRT_mock_1" not in out
    assert "Reply via gh: `gh api graphql" not in out
    assert "Resolve via gh: `gh api graphql" not in out

    code = cli.run(
        ["pr", "review-expand", "PRR_mock", "--pr", "77928", "--repo", "PaddlePaddle/Paddle", "--page-size", "2"]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "## Timeline Event" in out
    assert "lgtm" in out
    assert "Review comments (3/3 shown):" in out
    assert "PRRT_mock_1" in out
    assert "The error message could be more helpful." in out
    assert "Reactions: ❤️ x1" in out
    assert "Suggested Change:" in out
    assert "@@ python/test_file.py:L22 @@" in out
    assert "+new_api_call()" in out
    assert (
        "Edit comment via gh-llm: `gh-llm pr comment-edit PRRC_self_1 --body '<comment_body>' --pr 77928 --repo PaddlePaddle/Paddle`"
        in out
    )
    assert "Unresolve via gh-llm:" in out

    code = cli.run(["pr", "checks", "--pr", "77928", "--repo", "PaddlePaddle/Paddle", "--all"])
    assert code == 0
    out = capsys.readouterr().out
    assert "## Checks" in out
    assert "[COMPLETED/SUCCESS] lint (check-run)" in out
    assert "gh run view 101 --log --repo PaddlePaddle/Paddle" in out
    assert "gh run view 202 --job 303 --log --repo PaddlePaddle/Paddle" in out

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
            "comment-edit",
            "c3",
            "--body",
            "updated body",
            "--pr",
            "77928",
            "--repo",
            "PaddlePaddle/Paddle",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "comment: c3" in out
    assert "status: edited" in out

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


def test_web_like_extra_timeline_events_are_rendered(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    responder = GhResponder()
    monkeypatch.setattr(github_api.subprocess, "run", responder.run)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setattr(sys.modules[__name__], "_events", _events_with_web_like_extras)

    code = cli.run(["pr", "timeline-expand", "4", "--pr", "77928", "--repo", "PaddlePaddle/Paddle", "--page-size", "2"])
    assert code == 0
    out = capsys.readouterr().out
    assert "reference" in out
    assert 'PR #77887 "Test referenced PR" by @alice' in out
    assert "gh-llm pr view 77887 --repo PaddlePaddle/Paddle" in out

    code = cli.run(["pr", "timeline-expand", "5", "--pr", "77928", "--repo", "PaddlePaddle/Paddle", "--page-size", "2"])
    assert code == 0
    out = capsys.readouterr().out
    assert "cross-reference" in out
    assert "cross-reference by @triager (Tri Ager)" in out
    assert 'issue #12345 "Test issue" by @bob (Bob)' in out
    assert "gh-llm issue view 12345 --repo PaddlePaddle/Paddle" in out

    code = cli.run(["pr", "timeline-expand", "6", "--pr", "77928", "--repo", "PaddlePaddle/Paddle", "--page-size", "2"])
    assert code == 0
    out = capsys.readouterr().out
    assert "label/remove" in out
    assert "push/force" in out


def test_issue_view_and_expand_use_real_cursor_pagination(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    responder = GhResponder()
    monkeypatch.setattr(github_api.subprocess, "run", responder.run)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    code = cli.run(["issue", "view", "77924", "--repo", "PaddlePaddle/Paddle", "--page-size", "2"])
    assert code == 0
    out = capsys.readouterr().out
    assert "issue: 77924" in out
    assert "## Description" in out
    assert "This is issue description" in out
    assert "Reactions: 👀 x1" in out
    assert "gh issue edit 77924 --repo PaddlePaddle/Paddle --body '<issue_description_markdown>'" in out
    assert "## Diff Actions" not in out
    assert "## Timeline Page 1/3" in out
    assert "## Timeline Page 2/3" in out
    assert "## Timeline Page 3/3" in out
    assert "Hidden timeline page" not in out
    assert "(comment hidden: outdated)" in out
    assert "run `gh-llm issue event 1 --issue 77924 --repo PaddlePaddle/Paddle` for full content" in out
    assert "## Actions" in out
    assert "gh issue comment 77924 --repo PaddlePaddle/Paddle --body '<comment_body>'" in out
    assert "gh issue close 77924 --repo PaddlePaddle/Paddle" in out
    assert "gh issue edit 77924 --repo PaddlePaddle/Paddle --add-label '<label1>,<label2>'" in out
    assert "gh issue edit 77924 --repo PaddlePaddle/Paddle --remove-label '<label1>,<label2>'" in out
    assert "gh issue edit 77924 --repo PaddlePaddle/Paddle --add-assignee '<assignee1>,<assignee2>'" in out
    assert (
        "Edit comment via gh-llm: `gh-llm issue comment-edit ic2 --body '<comment_body>' --issue 77924 --repo PaddlePaddle/Paddle`"
        in out
    )
    assert "cross-reference by @alice (Alice)" in out
    assert "gh-llm pr view 77900 --repo PaddlePaddle/Paddle" in out
    assert "issue/closed by @ShigureNyako" in out

    code = cli.run(
        ["issue", "timeline-expand", "2", "--issue", "77924", "--repo", "PaddlePaddle/Paddle", "--page-size", "2"]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "## Timeline Page 2/3" in out

    code = cli.run(["issue", "event", "1", "--issue", "77924", "--repo", "PaddlePaddle/Paddle", "--page-size", "2"])
    assert code == 0
    out = capsys.readouterr().out
    assert "## Timeline Event 1" in out
    assert "ISSUE_END_MARKER" in out


def test_pr_review_actions_for_llm_flow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    responder = GhResponder()
    monkeypatch.setattr(github_api.subprocess, "run", responder.run)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    code = cli.run(["pr", "review-start", "--pr", "77928", "--repo", "PaddlePaddle/Paddle"])
    assert code == 0
    out = capsys.readouterr().out
    assert "## Review Start" in out
    assert "Total hunks: 1" in out
    assert "gh pr diff 77928 --repo PaddlePaddle/Paddle" in out
    assert "gh-llm pr review-comment --path 'python/test_file.py' --line 20 --side RIGHT" in out
    assert "gh-llm pr review-suggest --path 'python/test_file.py' --line 20 --side RIGHT" in out
    assert "@@ -20,2 +20,2 @@ def demo():" in out

    code = cli.run(
        [
            "pr",
            "review-comment",
            "--path",
            "python/test_file.py",
            "--line",
            "20",
            "--side",
            "RIGHT",
            "--body",
            "please simplify",
            "--pr",
            "77928",
            "--repo",
            "PaddlePaddle/Paddle",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "thread: PRRT_new_1" in out
    assert "comment: PRRC_new_1" in out
    assert "status: commented" in out

    code = cli.run(
        [
            "pr",
            "review-suggest",
            "--path",
            "python/test_file.py",
            "--line",
            "20",
            "--side",
            "RIGHT",
            "--body",
            "nits",
            "--suggestion",
            "new_api_call()",
            "--pr",
            "77928",
            "--repo",
            "PaddlePaddle/Paddle",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "status: suggested" in out

    code = cli.run(
        [
            "pr",
            "review-submit",
            "--event",
            "REQUEST_CHANGES",
            "--body",
            "please address comments",
            "--pr",
            "77928",
            "--repo",
            "PaddlePaddle/Paddle",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "review: PRR_pending_1" in out
    assert "state: COMMENTED" in out
    assert "status: submitted" in out


def test_graphql_eof_retries_with_backoff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    responder = GhResponder()
    state = {"failed_once": False}

    def flaky_run(cmd: list[str], *, check: bool, capture_output: bool, text: bool) -> FakeCompletedProcess:
        if cmd[:3] == ["gh", "api", "graphql"] and not state["failed_once"]:
            state["failed_once"] = True
            return FakeCompletedProcess("", returncode=1, stderr='Post "https://api.github.com/graphql": EOF')
        return responder.run(cmd, check=check, capture_output=capture_output, text=text)

    def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(github_api.subprocess, "run", flaky_run)
    monkeypatch.setattr(github_api.time, "sleep", no_sleep)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    code = cli.run(["pr", "view", "77928", "--repo", "PaddlePaddle/Paddle", "--page-size", "2"])
    assert code == 0
    out = capsys.readouterr().out
    assert "## Timeline Page 1/4" in out
    assert state["failed_once"] is True


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


def _issue_forward_page_payload(page_size: int, after: str | None) -> dict[str, Any]:
    events = _issue_events()
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
                "issue": {
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


def _issue_backward_page_payload(page_size: int, before: str | None) -> dict[str, Any]:
    events = _issue_events()
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
                "issue": {
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
                                            "body": "The error message could be more helpful.\n```suggestion\nnew_api_call()\n```",
                                            "line": 22,
                                            "originalLine": 22,
                                            "startLine": None,
                                            "originalStartLine": None,
                                            "diffHunk": "@@ -22,1 +22,1 @@\n-old_api_call()",
                                            "createdAt": "2026-02-14T14:50:02Z",
                                            "outdated": False,
                                            "isMinimized": False,
                                            "minimizedReason": None,
                                            "author": {"login": "reviewer"},
                                            "reactionGroups": [],
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
                                            "outdated": False,
                                            "isMinimized": False,
                                            "minimizedReason": None,
                                            "author": {"login": "reviewer"},
                                            "reactionGroups": [{"content": "HEART", "users": {"totalCount": 1}}],
                                            "pullRequestReview": {"id": "PRR_mock"},
                                        },
                                        {
                                            "id": "PRRC_self_1",
                                            "path": "python/test_file.py",
                                            "body": "self reply",
                                            "line": 23,
                                            "originalLine": 23,
                                            "startLine": None,
                                            "originalStartLine": None,
                                            "diffHunk": "@@ -23,1 +23,1 @@\n-old\n+new",
                                            "createdAt": "2026-02-14T14:50:03Z",
                                            "outdated": True,
                                            "isMinimized": False,
                                            "minimizedReason": None,
                                            "author": {"login": "ShigureNyako"},
                                            "reactionGroups": [],
                                            "pullRequestReview": {"id": "PRR_mock"},
                                        },
                                    ]
                                },
                            },
                        ],
                    }
                }
            }
        }
    }


def _checks_payload() -> dict[str, Any]:
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "statusCheckRollup": {
                                        "contexts": {
                                            "nodes": [
                                                {
                                                    "__typename": "CheckRun",
                                                    "name": "lint",
                                                    "status": "COMPLETED",
                                                    "conclusion": "SUCCESS",
                                                    "detailsUrl": "https://github.com/PaddlePaddle/Paddle/actions/runs/101",
                                                    "databaseId": 101,
                                                },
                                                {
                                                    "__typename": "CheckRun",
                                                    "name": "unit-tests",
                                                    "status": "IN_PROGRESS",
                                                    "conclusion": None,
                                                    "detailsUrl": "https://github.com/PaddlePaddle/Paddle/actions/runs/202/job/303",
                                                    "databaseId": 102,
                                                },
                                                {
                                                    "__typename": "StatusContext",
                                                    "context": "cla/check",
                                                    "state": "SUCCESS",
                                                    "targetUrl": "https://example.com/cla",
                                                    "description": "CLA check",
                                                },
                                            ]
                                        }
                                    }
                                }
                            }
                        ]
                    }
                }
            }
        }
    }


def _base_events() -> list[dict[str, Any]]:
    long_comment = ("LONG_TEXT " * 220) + "END_MARKER"
    return [
        {
            "__typename": "IssueComment",
            "id": "c1",
            "url": "https://example.com/c1",
            "createdAt": "2026-02-14T14:31:36Z",
            "body": long_comment,
            "author": {"login": "bot"},
            "reactionGroups": [{"content": "THUMBS_UP", "users": {"totalCount": 2}}],
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
            "reactionGroups": [],
        },
        {
            "__typename": "PullRequestReview",
            "id": "PRR_mock",
            "submittedAt": "2026-02-14T14:51:00Z",
            "state": "APPROVED",
            "body": "lgtm",
            "isMinimized": True,
            "minimizedReason": "OUTDATED",
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
            "body": "self comment",
            "author": {"login": "ShigureNyako"},
            "reactionGroups": [],
        },
    ]


def _events_with_web_like_extras() -> list[dict[str, Any]]:
    base = _base_events()
    return [
        *base,
        {
            "__typename": "ReferencedEvent",
            "id": "r1",
            "createdAt": "2026-02-14T15:12:00Z",
            "actor": {"login": "other"},
            "isCrossRepository": False,
            "subject": {
                "__typename": "PullRequest",
                "number": 77887,
                "title": "Test referenced PR",
                "author": {"login": "alice", "name": "Alice"},
                "repository": {"nameWithOwner": "PaddlePaddle/Paddle"},
            },
        },
        {
            "__typename": "CrossReferencedEvent",
            "id": "cr1",
            "createdAt": "2026-02-14T15:12:45Z",
            "actor": {"login": "triager", "name": "Tri Ager"},
            "isCrossRepository": False,
            "source": {
                "__typename": "Issue",
                "number": 12345,
                "title": "Test issue",
                "author": {"login": "bob", "name": "Bob"},
                "repository": {"nameWithOwner": "PaddlePaddle/Paddle"},
            },
        },
        {
            "__typename": "LabeledEvent",
            "id": "l1",
            "createdAt": "2026-02-14T15:13:00Z",
            "actor": {"login": "triager"},
            "label": {"name": "kind/docs"},
        },
        {
            "__typename": "UnlabeledEvent",
            "id": "u1",
            "createdAt": "2026-02-14T15:14:00Z",
            "actor": {"login": "triager"},
            "label": {"name": "needs-review"},
        },
        {
            "__typename": "HeadRefForcePushedEvent",
            "id": "f1",
            "createdAt": "2026-02-14T15:15:00Z",
            "actor": {"login": "author1"},
            "ref": {"name": "feature-branch"},
            "beforeCommit": {"oid": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
            "afterCommit": {"oid": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
        },
    ]


def _events() -> list[dict[str, Any]]:
    return _base_events()


def test_display_command_env_is_used_in_actions(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GH_LLM_DISPLAY_CMD", "gh llm")
    monkeypatch.setattr(github_api.subprocess, "run", GhResponder().run)

    code = cli.run(["pr", "view", "77928", "--repo", "PaddlePaddle/Paddle", "--page-size", "2"])
    assert code == 0

    out = capsys.readouterr().out
    assert "gh llm pr timeline-expand 2 --pr 77928 --repo PaddlePaddle/Paddle" in out
    assert "gh llm pr review-expand PRR_mock --pr 77928 --repo PaddlePaddle/Paddle" in out


def test_pr_timeline_expand_with_expand_option(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(github_api.subprocess, "run", GhResponder().run)

    code = cli.run(
        [
            "pr",
            "timeline-expand",
            "3",
            "--pr",
            "77928",
            "--repo",
            "PaddlePaddle/Paddle",
            "--page-size",
            "2",
            "--expand",
            "resolved,hidden",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "Review comments (3/3 shown):" in out
    assert "resolved review comments are collapsed" not in out
    assert "hidden review comments are collapsed" not in out


def test_issue_timeline_expand_with_expand_hidden(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(github_api.subprocess, "run", GhResponder().run)

    code = cli.run(
        [
            "issue",
            "timeline-expand",
            "1",
            "--issue",
            "77924",
            "--repo",
            "PaddlePaddle/Paddle",
            "--page-size",
            "2",
            "--expand",
            "hidden",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "(comment hidden: outdated)" not in out


def test_pr_view_show_timeline_only(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(github_api.subprocess, "run", GhResponder().run)

    code = cli.run(
        [
            "pr",
            "view",
            "77928",
            "--repo",
            "PaddlePaddle/Paddle",
            "--page-size",
            "2",
            "--show",
            "timeline",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "## Timeline Page 1/4" in out
    assert "## Actions" not in out
    assert "## Description" not in out


def test_issue_view_show_summary_only(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(github_api.subprocess, "run", GhResponder().run)

    code = cli.run(
        [
            "issue",
            "view",
            "77924",
            "--repo",
            "PaddlePaddle/Paddle",
            "--page-size",
            "2",
            "--show",
            "meta,description",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "## Description" in out
    assert "## Timeline Page" not in out
    assert "## Actions" not in out


TEST_BASE_PAGE_SIZE = 2


def _issue_events() -> list[dict[str, Any]]:
    long_comment = ("ISSUE_LONG_TEXT " * 220) + "ISSUE_END_MARKER"
    return [
        {
            "__typename": "IssueComment",
            "id": "ic1",
            "url": "https://example.com/ic1",
            "createdAt": "2026-02-13T10:00:00Z",
            "body": long_comment,
            "isMinimized": True,
            "minimizedReason": "OUTDATED",
            "author": {"login": "bot"},
            "reactionGroups": [{"content": "THUMBS_UP", "users": {"totalCount": 1}}],
        },
        {
            "__typename": "LabeledEvent",
            "id": "il1",
            "createdAt": "2026-02-13T11:00:00Z",
            "actor": {"login": "triager"},
            "label": {"name": "kind/question"},
        },
        {
            "__typename": "CrossReferencedEvent",
            "id": "icr1",
            "createdAt": "2026-02-13T12:00:00Z",
            "actor": {"login": "alice", "name": "Alice"},
            "isCrossRepository": False,
            "source": {
                "__typename": "PullRequest",
                "number": 77900,
                "title": "Related PR",
                "author": {"login": "bob", "name": "Bob"},
                "repository": {"nameWithOwner": "PaddlePaddle/Paddle"},
            },
        },
        {
            "__typename": "IssueComment",
            "id": "ic2",
            "url": "https://example.com/ic2",
            "createdAt": "2026-02-13T13:00:00Z",
            "body": "self issue comment",
            "isMinimized": False,
            "minimizedReason": None,
            "author": {"login": "ShigureNyako"},
            "reactionGroups": [],
        },
        {
            "__typename": "ClosedEvent",
            "id": "iclose1",
            "createdAt": "2026-02-13T14:00:00Z",
            "actor": {"login": "ShigureNyako"},
        },
    ]


def _page_bounds(page: int, total_count: int, base_page_size: int) -> tuple[int, int]:
    start = (page - 1) * base_page_size
    end = min(start + base_page_size, total_count)
    return start, end
