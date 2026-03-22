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

### Environment preflight / troubleshooting

When `gh-llm` fails with unclear transport or auth symptoms (for example GraphQL `EOF`, timeout, or an environment mismatch between `gh-llm` and `gh llm`), run:

```bash
gh-llm doctor
gh llm doctor
```

`doctor` prints the current entrypoint, resolved executable paths, active-host `gh auth status`, a REST probe, a minimal GraphQL probe, and proxy-related environment variables. Use this before guessing whether the issue is auth, network, proxy, or GitHub-side.

## Fast start

### Preflight an unfamiliar repo

```bash
gh-llm repo preflight --repo <owner/repo>
```

Use this before forking or opening a PR when you need the default branch, onboarding docs (`CONTRIBUTING*`, `AGENTS.md`, PR template, `CODEOWNERS`), branch-protection summary, and likely next commands in one place.

### Read a PR

```bash
gh-llm pr view <pr> --repo <owner/repo>
gh-llm pr timeline-expand <page> --pr <pr> --repo <owner/repo>
gh-llm pr review-expand <PRR_id[,PRR_id...]> --pr <pr> --repo <owner/repo>
gh-llm pr checks --pr <pr> --repo <owner/repo>
```

### Prepare a PR body

```bash
gh-llm pr body-template --repo <owner/repo>

gh-llm pr body-template \
  --repo <owner/repo> \
  --requirements 'Motivation,Validation,Related Issues' \
  --output /tmp/pr_body.md
```

Use this before `gh pr create` when you need to load a repo PR template, append required sections, and produce a ready-to-edit body file.

### Read an issue

```bash
gh-llm issue view <issue> --repo <owner/repo>
gh-llm issue timeline-expand <page> --issue <issue> --repo <owner/repo>
```

### Write simple updates

```bash
gh pr comment <pr> --repo <owner/repo> --body '<comment>'
gh issue comment <issue> --repo <owner/repo> --body '<comment>'
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

### 2) Be verifiable

When making technical claims, include at least one concrete reference:

1. `path:line`
2. commit hash
3. check/log link
4. reproduction command

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

## Review workflow

### Review a PR as reviewer

1. Read the whole PR first, not just one hunk:

```bash
gh-llm pr view <pr> --repo <owner/repo>
gh-llm pr checks --pr <pr> --repo <owner/repo>
gh-llm pr review-start --pr <pr> --repo <owner/repo>
```

2. For large PRs, narrow the diff instead of guessing:

```bash
gh-llm pr review-start --pr <pr> --repo <owner/repo> --files 6-12
gh-llm pr review-start --pr <pr> --repo <owner/repo> --path 'path/to/file'
gh-llm pr review-start --pr <pr> --repo <owner/repo> --path 'path/to/file' --hunks 2-4
gh-llm pr review-start --pr <pr> --repo <owner/repo> --context-lines 3
```

3. Before writing a new comment, check whether the same location already has unresolved review threads.
4. Use one pending review for one review round. Prefer multiple inline comments plus one final summary, not many separate top-level reviews.
5. Use `review-suggest` only when the exact replacement is clear and small enough to be safely suggested inline.
6. Use `review-comment` for questions, design concerns, missing tests, missing context, or changes too large for a suggestion block.
7. Distinguish severity clearly:
   - blocking: correctness, behavior regression, missing required tests, broken API/ABI, unsafe edge case
   - non-blocking: readability, style, naming, optional refactor, small follow-up
8. Every blocking point should make the next action obvious: what is wrong, where it is, and what kind of fix is expected.

### Submit review comments

Use inline comments during reading:

```bash
gh-llm pr review-comment \
  --path 'path/to/file' \
  --line <line> \
  --side RIGHT \
  --body '<comment>' \
  --pr <pr> --repo <owner/repo>

gh-llm pr review-suggest \
  --path 'path/to/file' \
  --line <line> \
  --side RIGHT \
  --body '<why>' \
  --suggestion '<replacement>' \
  --pr <pr> --repo <owner/repo>
```

Then submit one review:

```bash
gh-llm pr review-submit --event COMMENT --body '<summary>' --pr <pr> --repo <owner/repo>
gh-llm pr review-submit --event REQUEST_CHANGES --body '<summary>' --pr <pr> --repo <owner/repo>
gh-llm pr review-submit --event APPROVE --body '<summary>' --pr <pr> --repo <owner/repo>
```

Use the final review summary to group the round:

1. what is blocking
2. what is optional
3. what is already good

### As PR author

1. Expand all relevant review content before changing code:

```bash
gh-llm pr view <pr> --repo <owner/repo>
gh-llm pr review-expand <PRR_id[,PRR_id...]> --pr <pr> --repo <owner/repo>
gh-llm pr thread-expand <PRRT_id> --pr <pr> --repo <owner/repo>
```

2. Address review items one by one, but reply in batches when possible to avoid noisy back-and-forth.
3. Reply to each resolved point with concrete status:
   - what changed
   - where it changed
   - why a point was not adopted, if applicable
4. Resolve a thread only after the fix or decision is actually complete.
5. If a reviewer's suggestion is substantially adopted, add proper co-author credit in the follow-up commit.
6. After a batch of fixes, post one concise round-up so the reviewer can re-check efficiently.

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
