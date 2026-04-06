---
name: github-conversation
description: Practical workflow for agents to read GitHub PR/issue context and communicate effectively with evidence, clear status, and low noise.
metadata:
   primary-tools:
      - gh-llm
      - gh
---

# GitHub Conversation

## Use this skill when

1. You need to read a PR/issue before replying.
2. You need to reply to comments or review threads.
3. You need to submit a review.
4. You need to post a status update that closes loops.

## Tool split

1. Use `gh-llm` for reading context (timeline, collapsed items, review threads, checks).
2. Use `gh` for simple write actions (comment, labels, assignees, reviewers, close/reopen, merge).
3. If context is incomplete, do not reply yet; expand first.

## Message body fidelity

GitHub stores the body text exactly as sent.

1. Do not write multi-paragraph bodies as literal escape sequences such as `\n` or `\n\n`.
2. If you send `--body 'line1\n\nline2'`, GitHub will usually store the backslashes literally, and the rendered review/comment will show `\n\n`.
3. Use `--body` only for short single-paragraph text.
4. For quotes, bullets, code fences, or multiple paragraphs, prefer `--body-file` with a file or `-` on standard input.
5. For review suggestions that span multiple lines, prefer `--suggestion-file`.

Safe patterns:

```bash
cat <<'EOF' > /tmp/reply.md
> Reviewer point

Fixed in `python/demo.py:42`.
Validation: `pytest test/demo_test.py -q`
EOF

gh-llm pr thread-reply PRRT_xxx --body-file /tmp/reply.md --pr <pr> --repo <owner/repo>
gh-llm pr review-submit --event COMMENT --body-file /tmp/reply.md --pr <pr> --repo <owner/repo>
gh pr comment <pr> --repo <owner/repo> --body-file /tmp/reply.md
```

```bash
cat <<'EOF' | gh-llm pr review-submit --event COMMENT --body-file - --pr <pr> --repo <owner/repo>
Round-up:

- fixed overload selection
- added regression coverage
EOF
```

## Install gh-llm

Prerequisites:

1. `gh` is installed and authenticated (`gh auth status`).
2. Python 3.14+ is available if installing via `uv`.

Install option A (recommended for CLI tool use):

```bash
uv tool install gh-llm
gh-llm --version
```

Install option B (GitHub CLI extension):

```bash
gh extension install ShigureLab/gh-llm
gh llm --version
```

Command prefix mapping:

1. If installed via `uv tool`, use `gh-llm ...`.
2. If installed as `gh` extension, use `gh llm ...`.

## Fast start

### Read a PR

```bash
gh-llm pr view <pr> --repo <owner/repo>
gh-llm pr timeline-expand <page> --pr <pr> --repo <owner/repo>
gh-llm pr review-expand <PRR_id[,PRR_id...]> --pr <pr> --repo <owner/repo>
gh-llm pr checks --pr <pr> --repo <owner/repo>
```

### Read an issue

```bash
gh-llm issue view <issue> --repo <owner/repo>
gh-llm issue timeline-expand <page> --issue <issue> --repo <owner/repo>
```

### Write simple updates

```bash
gh pr comment <pr> --repo <owner/repo> --body '<comment>'
gh pr comment <pr> --repo <owner/repo> --body-file <comment.md>
gh issue comment <issue> --repo <owner/repo> --body '<comment>'
gh issue comment <issue> --repo <owner/repo> --body-file <comment.md>
gh pr edit <pr> --repo <owner/repo> --add-label '<label1>,<label2>'
gh pr edit <pr> --repo <owner/repo> --remove-label '<label1>,<label2>'
gh pr edit <pr> --repo <owner/repo> --add-reviewer '<reviewer1>,<reviewer2>'
gh pr edit <pr> --repo <owner/repo> --add-assignee '<assignee1>,<assignee2>'
```

## Reading workflow (required before replying)

### 1) Build context map

Identify:

1. Current goal of this PR/issue.
2. Open requests not yet addressed.
3. Decisions already made.
4. Linked PRs/issues that affect this thread.

### 2) Expand hidden context

Expand collapsed timeline pages and relevant review threads before replying.

### 3) Check delivery state

For PRs, check:

1. CI/check failures.
2. Mergeability/conflicts.
3. Unresolved review threads.

## Reply workflow

### 1) Reply to one thread with one intent

A single reply should answer the target point only.
Do not mix unrelated updates.
For multi-paragraph replies, use `--body-file` instead of embedding `\n\n` inside `--body`.

### 2) Be verifiable

When making technical claims, include at least one concrete reference:

1. `path:line`
2. commit hash
3. check/log link
4. reproduction command

### 2.5) Distinguish observed facts from intended actions

Only treat a GitHub write action as completed after the command returns a success status or object id.

1. Do not say "I already left an inline comment" unless the command output confirms it.
2. For `review-comment`, wait for `status: commented` and record the returned `thread` / `comment` id.
3. For `review-suggest`, wait for `status: suggested` and record the returned `thread` / `comment` id.
4. For `thread-reply`, wait for `status: replied` and record the returned `thread` / `reply_comment_id`.
5. If a write command was only drafted, described, or planned, say so explicitly instead of implying it already happened.

### 3) Quote only when needed

Use `>` when:

1. the original comment has multiple points
2. the thread is long and reference is ambiguous
3. you are answering a specific sentence fragment

For short one-to-one replies, no quote is needed.

### 4) State status clearly

Use plain status language:

1. fixed
2. partially fixed
3. not fixed yet
4. intentionally unchanged

If partially fixed or unchanged, include reason and next step.

### 5) Preserve quoting and paragraph breaks

When you need `>` quotes, bullets, numbered lists, or fenced code blocks, write the body through `--body-file`.
Do not hand-escape markdown structure inside a shell string unless the content is genuinely one line.

## Review workflow

### As reviewer

1. Separate blocking vs non-blocking points.
2. Give actionable suggestions.
3. Point to exact location when possible.
4. Avoid generic criticism without concrete evidence.
5. When opening new inline feedback on code, start from `gh-llm pr review-start` to get real commentable locations before drafting the command.
6. Use `review-suggest` when you can propose a small exact replacement at one location; use `review-comment` when the change is broader, uncertain, or needs discussion first.
7. After posting inline feedback, report the returned `thread` / `comment` ids as the operation result.

### Review conclusion

The review outcome should be explicit whenever the current state is already clear.

1. Use `APPROVE` when the change is ready to merge from your side.
2. Use `REQUEST_CHANGES` when blocking issues remain.
3. Use `COMMENT` mainly for non-blocking notes, partial context gathering, or intermediate status updates before the final conclusion is clear.
4. Do not leave the review state implicit if your evidence already supports approval or blocking.
5. In the review body, state the conclusion in plain language as well, especially when using `REQUEST_CHANGES`.

### As PR author

1. Expand and read all relevant review content.
2. Address items one by one.
3. Reply to each addressed thread.
4. Resolve a thread only after fix/decision is actually complete.
5. Post one concise round-up after a batch of fixes.
6. For thread replies, review summaries, and inline comments with more than one paragraph, use `--body-file`.

### Inline feedback choice

Prefer the smallest tool that matches the intent:

1. `thread-reply`: respond inside an existing review thread.
2. `review-comment`: raise a new inline point without an exact replacement.
3. `review-suggest`: propose a concrete patch the author can apply directly.

Use `review-suggest` by default when all of the following are true:

1. the change is local to one hunk
2. the replacement text is known exactly
3. the explanation fits in one short rationale paragraph

Do not force `review-suggest` when the fix spans multiple files, requires design discussion, or depends on behavior you have not verified.

## Issue workflow

### Opening an issue

Include:

1. Problem statement.
2. Minimal reproduction.
3. Expected vs actual behavior.
4. Environment details.
5. Logs/traceback/screenshots.
6. Related links.

### Maintaining a busy issue

1. Ask for missing repro info instead of guessing.
2. Link duplicates to the canonical thread.
3. Keep one canonical status update comment.

## Quality gates before posting

1. Is context complete (including expanded hidden/collapsed content)?
2. Does the message move the thread forward?
3. Are key claims backed by verifiable evidence?
4. Does tone and granularity match this repository?

## Co-author and credit

When a reviewer's concrete code change is substantially adopted, add:

```text
Co-authored-by: <Reviewer Name> <reviewer_email>
```

Use GitHub-linked email if attribution on GitHub is desired.
