from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from typing import cast
from urllib.parse import urlparse

from gh_llm.models import PageInfo, PullRequestMeta, PullRequestRef, TimelineEvent, TimelinePage

MAX_INLINE_TEXT = 8000
MAX_INLINE_LINES = 200

TIMELINE_ITEM_TYPES = (
    "ISSUE_COMMENT",
    "PULL_REQUEST_REVIEW",
    "PULL_REQUEST_COMMIT",
    "MERGED_EVENT",
    "CLOSED_EVENT",
    "REOPENED_EVENT",
)

FORWARD_TIMELINE_QUERY = """
query($owner:String!,$name:String!,$number:Int!,$pageSize:Int!,$after:String){
  repository(owner:$owner,name:$name){
    pullRequest(number:$number){
      timelineItems(first:$pageSize,after:$after,itemTypes:[ISSUE_COMMENT,PULL_REQUEST_REVIEW,PULL_REQUEST_COMMIT,MERGED_EVENT,CLOSED_EVENT,REOPENED_EVENT]){
        totalCount
        pageInfo{hasNextPage hasPreviousPage startCursor endCursor}
        nodes{
          __typename
          ... on IssueComment{ id url createdAt body author{login} }
          ... on PullRequestReview{
            id
            submittedAt
            state
            body
            author{login}
          }
          ... on PullRequestCommit{ commit{ oid committedDate messageHeadline message authors(first:1){nodes{name user{login}}} } }
          ... on MergedEvent{ id createdAt actor{login} }
          ... on ClosedEvent{ id createdAt actor{login} }
          ... on ReopenedEvent{ id createdAt actor{login} }
        }
      }
    }
  }
}
""".strip()

BACKWARD_TIMELINE_QUERY = """
query($owner:String!,$name:String!,$number:Int!,$pageSize:Int!,$before:String){
  repository(owner:$owner,name:$name){
    pullRequest(number:$number){
      timelineItems(last:$pageSize,before:$before,itemTypes:[ISSUE_COMMENT,PULL_REQUEST_REVIEW,PULL_REQUEST_COMMIT,MERGED_EVENT,CLOSED_EVENT,REOPENED_EVENT]){
        totalCount
        pageInfo{hasNextPage hasPreviousPage startCursor endCursor}
        nodes{
          __typename
          ... on IssueComment{ id url createdAt body author{login} }
          ... on PullRequestReview{
            id
            submittedAt
            state
            body
            author{login}
          }
          ... on PullRequestCommit{ commit{ oid committedDate messageHeadline message authors(first:1){nodes{name user{login}}} } }
          ... on MergedEvent{ id createdAt actor{login} }
          ... on ClosedEvent{ id createdAt actor{login} }
          ... on ReopenedEvent{ id createdAt actor{login} }
        }
      }
    }
  }
}
""".strip()

REVIEW_THREADS_QUERY = """
query($owner:String!,$name:String!,$number:Int!,$after:String){
  repository(owner:$owner,name:$name){
    pullRequest(number:$number){
      reviewThreads(first:100,after:$after){
        pageInfo{hasNextPage endCursor}
        nodes{
          id
          isResolved
          comments(first:100){
            nodes{
              id
              path
              body
              line
              originalLine
              startLine
              originalStartLine
              diffHunk
              createdAt
              author{login}
              pullRequestReview{id}
            }
          }
        }
      }
    }
  }
}
""".strip()


class GitHubClient:
    def __init__(self) -> None:
        self._review_threads_cache: dict[tuple[str, str, int], dict[str, list[dict[str, object]]]] = {}

    def resolve_pull_request(self, selector: str | None, repo: str | None) -> PullRequestMeta:
        fields = ["number", "title", "url", "author", "state", "isDraft", "body", "updatedAt"]
        cmd = ["gh", "pr", "view"]
        if selector:
            cmd.append(selector)
        if repo:
            cmd.extend(["--repo", repo])
        cmd.extend(["--json", ",".join(fields)])

        payload = _run_command_json(cmd)
        number = _as_int(payload.get("number"), context="number")
        title = _as_optional_str(payload.get("title")) or ""
        url = _as_optional_str(payload.get("url")) or ""
        author = _get_login(payload.get("author"))
        state = _as_optional_str(payload.get("state")) or "UNKNOWN"
        is_draft = bool(payload.get("isDraft"))
        body = _as_optional_str(payload.get("body")) or ""
        updated_at = _as_optional_str(payload.get("updatedAt")) or ""

        owner, name = _parse_owner_repo(url)
        ref = PullRequestRef(owner=owner, name=name, number=number)
        return PullRequestMeta(
            ref=ref,
            title=title,
            url=url,
            author=author,
            state=state,
            is_draft=is_draft,
            body=body,
            updated_at=updated_at,
        )

    def fetch_timeline_forward(
        self, ref: PullRequestRef, page_size: int, after: str | None, *, show_resolved_details: bool = False
    ) -> TimelinePage:
        variables: dict[str, str | int] = {
            "owner": ref.owner,
            "name": ref.name,
            "number": ref.number,
            "pageSize": page_size,
        }
        if after is not None:
            variables["after"] = after

        connection = _run_graphql_connection(FORWARD_TIMELINE_QUERY, variables)
        threads_by_review = self._get_review_threads_by_review(ref)
        return _parse_timeline_page(
            connection,
            ref=ref,
            threads_by_review=threads_by_review,
            show_resolved_details=show_resolved_details,
        )

    def fetch_timeline_backward(
        self, ref: PullRequestRef, page_size: int, before: str | None, *, show_resolved_details: bool = False
    ) -> TimelinePage:
        variables: dict[str, str | int] = {
            "owner": ref.owner,
            "name": ref.name,
            "number": ref.number,
            "pageSize": page_size,
        }
        if before is not None:
            variables["before"] = before

        connection = _run_graphql_connection(BACKWARD_TIMELINE_QUERY, variables)
        threads_by_review = self._get_review_threads_by_review(ref)
        return _parse_timeline_page(
            connection,
            ref=ref,
            threads_by_review=threads_by_review,
            show_resolved_details=show_resolved_details,
        )

    def _get_review_threads_by_review(self, ref: PullRequestRef) -> dict[str, list[dict[str, object]]]:
        key = (ref.owner, ref.name, ref.number)
        cached = self._review_threads_cache.get(key)
        if cached is not None:
            return cached

        by_review: dict[str, list[dict[str, object]]] = {}
        after: str | None = None
        while True:
            variables: dict[str, str | int] = {
                "owner": ref.owner,
                "name": ref.name,
                "number": ref.number,
            }
            if after is not None:
                variables["after"] = after
            payload = _run_graphql_payload(REVIEW_THREADS_QUERY, variables)
            data_obj = _as_dict(payload.get("data"), context="graphql data")
            repo_obj = _as_dict(data_obj.get("repository"), context="repository")
            pr_obj = _as_dict(repo_obj.get("pullRequest"), context="pullRequest")
            threads_obj = _as_dict(pr_obj.get("reviewThreads"), context="reviewThreads")

            for raw_thread in _as_list(threads_obj.get("nodes")):
                thread = _as_dict(raw_thread, context="reviewThread")
                thread_id = _as_optional_str(thread.get("id")) or ""
                is_resolved = bool(thread.get("isResolved"))
                comments_obj = _as_dict_optional(thread.get("comments"))
                if comments_obj is None:
                    continue
                thread_comments: list[dict[str, object]] = []
                review_ids: set[str] = set()
                for raw_comment in _as_list(comments_obj.get("nodes")):
                    comment = _as_dict(raw_comment, context="reviewThread comment")
                    thread_comments.append(comment)
                    review_obj = _as_dict_optional(comment.get("pullRequestReview"))
                    review_id = _as_optional_str(review_obj.get("id")) if review_obj is not None else None
                    if review_id:
                        review_ids.add(review_id)

                if not thread_comments or not review_ids:
                    continue

                thread_payload: dict[str, object] = {
                    "id": thread_id,
                    "isResolved": is_resolved,
                    "comments": thread_comments,
                }
                for review_id in review_ids:
                    by_review.setdefault(review_id, []).append(thread_payload)

            page_info = _as_dict(threads_obj.get("pageInfo"), context="reviewThreads pageInfo")
            has_next = bool(page_info.get("hasNextPage"))
            after = _as_optional_str(page_info.get("endCursor"))
            if not has_next:
                break

        self._review_threads_cache[key] = by_review
        return by_review

    def reply_review_thread(self, thread_id: str, body: str) -> str:
        query = """
mutation($threadId:ID!,$body:String!){
  addPullRequestReviewThreadReply(input:{pullRequestReviewThreadId:$threadId,body:$body}){
    comment{id}
  }
}
""".strip()
        payload = _run_graphql_payload(query, {"threadId": thread_id, "body": body})
        data_obj = _as_dict(payload.get("data"), context="graphql data")
        reply_obj = _as_dict(data_obj.get("addPullRequestReviewThreadReply"), context="addPullRequestReviewThreadReply")
        comment_obj = _as_dict(reply_obj.get("comment"), context="reply comment")
        return _as_optional_str(comment_obj.get("id")) or ""

    def resolve_review_thread(self, thread_id: str) -> bool:
        query = """
mutation($threadId:ID!){
  resolveReviewThread(input:{threadId:$threadId}){
    thread{id isResolved}
  }
}
""".strip()
        payload = _run_graphql_payload(query, {"threadId": thread_id})
        data_obj = _as_dict(payload.get("data"), context="graphql data")
        resolved_obj = _as_dict(data_obj.get("resolveReviewThread"), context="resolveReviewThread")
        thread_obj = _as_dict(resolved_obj.get("thread"), context="resolved thread")
        return bool(thread_obj.get("isResolved"))

    def unresolve_review_thread(self, thread_id: str) -> bool:
        query = """
mutation($threadId:ID!){
  unresolveReviewThread(input:{threadId:$threadId}){
    thread{id isResolved}
  }
}
""".strip()
        payload = _run_graphql_payload(query, {"threadId": thread_id})
        data_obj = _as_dict(payload.get("data"), context="graphql data")
        unresolved_obj = _as_dict(data_obj.get("unresolveReviewThread"), context="unresolveReviewThread")
        thread_obj = _as_dict(unresolved_obj.get("thread"), context="unresolved thread")
        return bool(thread_obj.get("isResolved"))

    def comment_pull_request(self, selector: str | None, repo: str | None, body: str) -> str:
        cmd = ["gh", "pr", "comment"]
        if selector:
            cmd.append(selector)
        if repo:
            cmd.extend(["--repo", repo])
        cmd.extend(["--body", body])
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"command failed: {' '.join(cmd)}")
        return result.stdout.strip()


def _run_graphql_connection(query: str, variables: dict[str, str | int]) -> dict[str, object]:
    payload = _run_graphql_payload(query, variables)
    data_obj = _as_dict(payload.get("data"), context="graphql data")
    repo_obj = _as_dict(data_obj.get("repository"), context="repository")
    pr_obj = _as_dict(repo_obj.get("pullRequest"), context="pullRequest")
    return _as_dict(pr_obj.get("timelineItems"), context="timelineItems")


def _run_graphql_payload(query: str, variables: dict[str, str | int]) -> dict[str, object]:
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        cmd.extend(["-F", f"{key}={value}"])
    return _run_command_json(cmd)


def _run_command_json(cmd: list[str]) -> dict[str, object]:
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"command failed: {' '.join(cmd)}")
    parsed: object = json.loads(result.stdout)
    if not isinstance(parsed, dict):
        raise RuntimeError("unexpected non-object JSON response")
    raw = cast("dict[object, object]", parsed)
    return {str(k): v for k, v in raw.items()}


def _parse_timeline_page(
    connection: dict[str, object],
    *,
    ref: PullRequestRef,
    threads_by_review: dict[str, list[dict[str, object]]],
    show_resolved_details: bool,
) -> TimelinePage:
    total_count = _as_int_default(connection.get("totalCount"), default=0)
    page_info_obj = _as_dict(connection.get("pageInfo"), context="pageInfo")
    page_info = PageInfo(
        has_next_page=bool(page_info_obj.get("hasNextPage")),
        has_previous_page=bool(page_info_obj.get("hasPreviousPage")),
        start_cursor=_as_optional_str(page_info_obj.get("startCursor")),
        end_cursor=_as_optional_str(page_info_obj.get("endCursor")),
    )

    items: list[TimelineEvent] = []
    for node in _as_list(connection.get("nodes")):
        parsed = _parse_node(
            _as_dict(node, context="timeline node"),
            ref=ref,
            threads_for_review=threads_by_review,
            show_resolved_details=show_resolved_details,
        )
        if parsed is not None:
            items.append(parsed)

    items.sort(key=lambda value: value.timestamp)
    return TimelinePage(items=items, total_count=total_count, page_info=page_info)


def _parse_node(
    node: dict[str, object],
    *,
    ref: PullRequestRef,
    threads_for_review: dict[str, list[dict[str, object]]],
    show_resolved_details: bool,
) -> TimelineEvent | None:
    typename = str(node.get("__typename") or "")
    if typename == "IssueComment":
        body = _as_optional_str(node.get("body"))
        summary, is_truncated = _clip_text(body, "(no comment body)")
        return TimelineEvent(
            timestamp=_parse_datetime(_as_optional_str(node.get("createdAt"))),
            kind="comment",
            actor=_get_login(node.get("author")),
            summary=summary,
            source_id=_as_optional_str(node.get("id")) or "comment",
            full_text=body,
            is_truncated=is_truncated,
        )

    if typename == "PullRequestReview":
        state = _as_optional_str(node.get("state")) or "COMMENTED"
        review_id = _as_optional_str(node.get("id")) or "review"
        full_review, resolved_hidden_count = _build_review_text(
            node=node,
            ref=ref,
            state=state,
            threads_for_review=threads_for_review.get(review_id, []),
            show_resolved_details=show_resolved_details,
        )
        summary, is_truncated = _clip_text(full_review, f"review state: {state.lower()}")
        return TimelineEvent(
            timestamp=_parse_datetime(_as_optional_str(node.get("submittedAt"))),
            kind=f"review/{state.lower()}",
            actor=_get_login(node.get("author")),
            summary=summary,
            source_id=review_id,
            full_text=full_review,
            is_truncated=is_truncated,
            resolved_hidden_count=resolved_hidden_count,
        )

    if typename == "PullRequestCommit":
        commit = _as_dict(node.get("commit"), context="commit")
        full_message = _as_optional_str(commit.get("message"))
        message = _first_non_empty_line(full_message) or _as_optional_str(commit.get("messageHeadline"))
        oid = _as_optional_str(commit.get("oid")) or "commit"
        actor = _get_commit_actor(commit)
        summary, is_truncated = _clip_text(message, "(empty commit message)")
        return TimelineEvent(
            timestamp=_parse_datetime(_as_optional_str(commit.get("committedDate"))),
            kind="commit",
            actor=actor,
            summary=summary,
            source_id=oid,
            full_text=full_message or message,
            is_truncated=is_truncated,
        )

    if typename in {"MergedEvent", "ClosedEvent", "ReopenedEvent"}:
        kind_map = {
            "MergedEvent": "pr/merged",
            "ClosedEvent": "pr/closed",
            "ReopenedEvent": "pr/reopened",
        }
        summary_map = {
            "MergedEvent": "pull request merged",
            "ClosedEvent": "pull request closed",
            "ReopenedEvent": "pull request reopened",
        }
        return TimelineEvent(
            timestamp=_parse_datetime(_as_optional_str(node.get("createdAt"))),
            kind=kind_map[typename],
            actor=_get_login(node.get("actor")),
            summary=summary_map[typename],
            source_id=_as_optional_str(node.get("id")) or kind_map[typename],
        )

    return None


def _get_commit_actor(commit: dict[str, object]) -> str:
    authors = _as_dict(commit.get("authors"), context="commit authors")
    nodes = _as_list(authors.get("nodes"))
    if not nodes:
        return "unknown"
    first = _as_dict(nodes[0], context="commit author")
    user = _as_dict_optional(first.get("user"))
    if user is not None:
        login = _as_optional_str(user.get("login"))
        if login:
            return login
    name = _as_optional_str(first.get("name"))
    return name or "unknown"


def _get_login(value: object) -> str:
    obj = _as_dict_optional(value)
    if obj is None:
        return "unknown"
    login = _as_optional_str(obj.get("login"))
    return login or "unknown"


def _parse_owner_repo(pr_url: str) -> tuple[str, str]:
    parsed = urlparse(pr_url)
    parts = [segment for segment in parsed.path.split("/") if segment]
    if len(parts) < 2:
        raise RuntimeError(f"failed to parse owner/repo from url: {pr_url}")
    return parts[0], parts[1]


def _clip_text(text: str | None, fallback: str, limit: int = MAX_INLINE_TEXT) -> tuple[str, bool]:
    if not text:
        return fallback, False
    trimmed = text.strip()
    if not trimmed:
        return fallback, False
    lines = [line.rstrip() for line in trimmed.splitlines()]
    normalized = "\n".join(lines)
    if len(normalized) <= limit and len(lines) <= MAX_INLINE_LINES:
        return normalized, False

    clipped = normalized[:limit].rstrip()
    clipped_lines = clipped.splitlines()[:MAX_INLINE_LINES]
    return "\n".join(clipped_lines).rstrip() + "...", True


def _first_non_empty_line(text: str | None) -> str | None:
    if text is None:
        return None
    for raw in text.splitlines():
        line = raw.strip()
        if line:
            return line
    return None


def _build_review_text(
    node: dict[str, object],
    ref: PullRequestRef,
    state: str,
    *,
    threads_for_review: list[dict[str, object]],
    show_resolved_details: bool,
) -> tuple[str, int]:
    body = (_as_optional_str(node.get("body")) or "").strip()
    total_count = sum(len(_as_list(_as_dict(thread, context="thread").get("comments"))) for thread in threads_for_review)
    detail_lines: list[str] = []
    resolved_hidden_count = 0
    rendered_comments = 0
    rendered_thread_index = 0
    for raw_thread in threads_for_review:
        thread = _as_dict(raw_thread, context="review thread")
        is_resolved = bool(thread.get("isResolved"))
        thread_id = _as_optional_str(thread.get("id")) or "(unknown thread id)"
        comment_nodes = _as_list(thread.get("comments"))
        if is_resolved and not show_resolved_details:
            resolved_hidden_count += len(comment_nodes)
            continue
        rendered_thread_index += 1
        detail_lines.extend(
            _render_review_thread_block(
                thread_id=thread_id,
                is_resolved=is_resolved,
                thread_index=rendered_thread_index,
                comments=comment_nodes,
                ref=ref,
            )
        )
        rendered_comments += len(comment_nodes)

    chunks: list[str] = []
    if body:
        chunks.append(body)
    if total_count > 0:
        chunks.append(f"Review comments ({rendered_comments}/{total_count} shown):")
        if detail_lines:
            chunks.extend(detail_lines)
        hidden_count = total_count - rendered_comments
        if hidden_count > 0:
            chunks.append(f"... {hidden_count} review comments hidden.")
    elif threads_for_review:
        chunks.append("Review comments (0/0 shown):")
        chunks.append("(review threads exist but contain no comment nodes)")

    if not chunks:
        return f"review state: {state.lower()}", resolved_hidden_count
    return "\n".join(chunks), resolved_hidden_count


def _render_review_thread_block(
    *,
    thread_id: str,
    is_resolved: bool,
    thread_index: int,
    comments: list[object],
    ref: PullRequestRef,
) -> list[str]:
    lines = [f"- Thread[{thread_index}] {thread_id}"]
    for comment_index, raw_comment in enumerate(comments, start=1):
        comment = _as_dict(raw_comment, context="review comment")
        lines.extend(
            _render_review_comment_block(
                comment=comment,
                index=comment_index,
                include_diff_hunk=(comment_index == 1),
            )
        )
    lines.append(f"  🆔 thread_id: {thread_id}")
    lines.append("  ⌨ reply_body: '<reply>'")
    lines.append(
        f"  ⏎ Reply via gh-llm: `gh-llm pr thread-reply {thread_id} --body '<reply>' --pr {ref.number} --repo {ref.owner}/{ref.name}`"
    )
    if is_resolved:
        lines.append(
            f"  ⏎ Unresolve via gh-llm: `gh-llm pr thread-unresolve {thread_id} --pr {ref.number} --repo {ref.owner}/{ref.name}`"
        )
    else:
        lines.append(
            f"  ⏎ Resolve via gh-llm: `gh-llm pr thread-resolve {thread_id} --pr {ref.number} --repo {ref.owner}/{ref.name}`"
        )
    return lines


def _render_review_comment_block(
    comment: dict[str, object], index: int, *, include_diff_hunk: bool = True
) -> list[str]:
    path = _as_optional_str(comment.get("path")) or "(unknown path)"
    line = _as_line_ref(comment)
    author = _get_login(comment.get("author"))
    created_at = _as_optional_str(comment.get("createdAt")) or "unknown time"
    body = (_as_optional_str(comment.get("body")) or "").strip()
    diff_hunk = (_as_optional_str(comment.get("diffHunk")) or "").strip()
    suggestion_lines = _extract_suggestion_lines(body)
    rendered_body = "\n".join(suggestion_lines) if suggestion_lines else body

    lines = [f"- [{index}] {path}{line} by @{author} at {created_at}"]
    if rendered_body:
        lines.append("  Comment:")
        lines.extend(_indented_fenced_block("text", rendered_body, indent="  "))
    if diff_hunk and include_diff_hunk:
        lines.append("  Diff Hunk:")
        lines.extend(_indented_fenced_block("diff", diff_hunk, indent="  "))

    suggestion_diff = _suggestion_to_diff(path=path, line_ref=line, body=body)
    if suggestion_diff:
        lines.append("  Suggested Change:")
        lines.extend(_indented_fenced_block("diff", suggestion_diff, indent="  "))

    if not body and not diff_hunk:
        lines.append("  (empty review comment)")
    return lines


def _as_line_ref(comment: dict[str, object]) -> str:
    line = _as_int_default(comment.get("line"), default=0)
    original_line = _as_int_default(comment.get("originalLine"), default=0)
    start_line = _as_int_default(comment.get("startLine"), default=0)
    original_start_line = _as_int_default(comment.get("originalStartLine"), default=0)

    if line > 0:
        return f":L{line}"
    if original_line > 0:
        return f":L{original_line}"
    if start_line > 0:
        return f":L{start_line}"
    if original_start_line > 0:
        return f":L{original_start_line}"
    return ""


def _indented_fenced_block(language: str, content: str, indent: str = "") -> list[str]:
    out = [f"{indent}```{language}"]
    out.extend(f"{indent}{line}" for line in content.splitlines())
    out.append(f"{indent}```")
    return out


def _suggestion_to_diff(path: str, line_ref: str, body: str) -> str | None:
    suggestion_lines = _extract_suggestion_lines(body)
    if not suggestion_lines:
        return None
    header = f"@@ {path}{line_ref} @@"
    plus_lines = [f"+{line}" for line in suggestion_lines]
    return "\n".join([header, *plus_lines])


def _extract_suggestion_lines(text: str) -> list[str]:
    lines = text.splitlines()
    start = -1
    end = -1
    for idx, line in enumerate(lines):
        if line.strip().startswith("```suggestion"):
            start = idx + 1
            continue
        if start >= 0 and line.strip().startswith("```"):
            end = idx
            break
    if start < 0:
        return []
    if end < 0:
        end = len(lines)
    return [line.rstrip() for line in lines[start:end]]


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, tz=UTC)
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _as_dict(value: object, *, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RuntimeError(f"invalid {context} structure")
    raw = cast("dict[object, object]", value)
    return {str(k): v for k, v in raw.items()}


def _as_dict_optional(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        raw = cast("dict[object, object]", value)
        return {str(k): v for k, v in raw.items()}
    return None


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return cast("list[object]", value)
    return []


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _as_int(value: object, *, context: str) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError as error:
            raise RuntimeError(f"invalid integer for {context}: {value}") from error
    raise RuntimeError(f"invalid integer value for {context}")


def _as_int_default(value: object, *, default: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default
