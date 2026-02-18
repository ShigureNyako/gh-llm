# gh-llm

CLI tooling for LLM-first GitHub reading and review workflows.

<p align="center">
  <a href="https://python.org/" target="_blank"><img alt="PyPI - Python Version" src="https://img.shields.io/pypi/pyversions/gh-llm?logo=python&style=flat-square"></a>
  <a href="https://pypi.org/project/gh-llm/" target="_blank"><img src="https://img.shields.io/pypi/v/gh-llm?style=flat-square" alt="pypi"></a>
  <a href="https://pypi.org/project/gh-llm/" target="_blank"><img alt="PyPI - Downloads" src="https://img.shields.io/pypi/dm/gh-llm?style=flat-square"></a>
  <a href="LICENSE"><img alt="LICENSE" src="https://img.shields.io/github/license/ShigureLab/gh-llm?style=flat-square"></a>
  <br/>
  <a href="https://github.com/astral-sh/uv"><img alt="uv" src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json&style=flat-square"></a>
  <a href="https://github.com/astral-sh/ruff"><img alt="ruff" src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=flat-square"></a>
  <a href="https://gitmoji.dev"><img alt="Gitmoji" src="https://img.shields.io/badge/gitmoji-%20😜%20😍-FFDD67?style=flat-square"></a>
</p>

## Core Goal

`gh-llm` is primarily built to help an LLM quickly capture the same key context a human reviewer would get on GitHub Web, and provide actionable next commands at exactly the right places.

## Key Ideas

- Timeline-first rendering:
  merge comments, reviews, commits, labels, references, force-push, and state changes into one ordered stream that mirrors GitHub Web reading.
- Real cursor pagination:
  use GitHub GraphQL `first/after` and `last/before`, so page expansion always pulls real server-side data instead of fake local slicing.
- Progressive context loading:
  show first + last page first (high-signal summary), then expand hidden pages/events only when needed.
- Action-oriented output:
  place ready-to-run `gh` / `gh-llm` commands at decision points (expand, view detail, reply, resolve, review).
- Stateless interaction model:
  no fragile local session state required between commands.

## Requirements

- Python `3.14+`
- `gh` installed and authenticated (`gh auth status`)

## Install

### As CLI (recommended)

```bash
uv tool install gh-llm
gh-llm --help
```

### As gh extension

```bash
gh extension install ShigureLab/gh-llm
gh llm --help
```

The extension entrypoint forwards to local repository path via `uv run --project <extension_repo_path> gh-llm ...`.
`gh llm ...` and `gh-llm ...` are equivalent command surfaces.

## Quick Start

### PR Reading

```bash
# Show first + last timeline pages with actionable hints
gh-llm pr view 77900 --repo PaddlePaddle/Paddle
gh llm pr view 77900 --repo PaddlePaddle/Paddle

# Show selected regions only
gh-llm pr view 77900 --repo PaddlePaddle/Paddle --show timeline,checks

# Expand one hidden timeline page
gh-llm pr timeline-expand 2 --pr 77900 --repo PaddlePaddle/Paddle

# Auto-expand folded content in default/timeline view
gh-llm pr view 77900 --repo PaddlePaddle/Paddle --expand resolved,outdated,minimized
gh-llm pr timeline-expand 2 --pr 77900 --repo PaddlePaddle/Paddle --expand all

# Show full content for one comment node id
gh-llm pr comment-expand IC_xxx --pr 77900 --repo PaddlePaddle/Paddle

# Expand resolved review details in batch
gh-llm pr review-expand PRR_xxx,PRR_yyy --pr 77900 --repo PaddlePaddle/Paddle

# Checks
gh-llm pr checks --pr 77900 --repo PaddlePaddle/Paddle
gh-llm pr checks --pr 77900 --repo PaddlePaddle/Paddle --all
```

### Issue Reading

```bash
gh-llm issue view 77924 --repo PaddlePaddle/Paddle
gh-llm issue timeline-expand 2 --issue 77924 --repo PaddlePaddle/Paddle
gh-llm issue comment-expand IC_xxx --issue 77924 --repo PaddlePaddle/Paddle
gh-llm issue view 77924 --repo PaddlePaddle/Paddle --expand minimized,details
gh-llm issue view 77924 --repo PaddlePaddle/Paddle --show meta,description
```

`--expand` values:

- PR: `resolved`, `outdated`, `minimized`, `details`, `all`
- Issue: `minimized`, `details`, `all`
- Supports comma-separated values and repeated flags.

`--show` values:

- PR: `meta`, `description`, `timeline`, `checks`, `actions`, `all`
- Issue: `meta`, `description`, `timeline`, `actions`, `all`
- Supports comma-separated values and repeated flags.
- `summary` is supported as an alias for `meta,description`.

### Comment / Thread Actions

```bash
# Edit comment
gh-llm pr comment-edit IC_xxx --body '<new_body>' --pr 77900 --repo PaddlePaddle/Paddle
gh-llm issue comment-edit IC_xxx --body '<new_body>' --issue 77924 --repo PaddlePaddle/Paddle

# Reply / resolve / unresolve review thread
gh-llm pr thread-reply PRRT_xxx --body '<reply>' --pr 77900 --repo PaddlePaddle/Paddle
gh-llm pr thread-resolve PRRT_xxx --pr 77900 --repo PaddlePaddle/Paddle
gh-llm pr thread-unresolve PRRT_xxx --pr 77900 --repo PaddlePaddle/Paddle
```

## PR Review Workflow

### 1) Start from diff hunks

```bash
gh-llm pr review-start --pr 77938 --repo PaddlePaddle/Paddle
```

It prints per-hunk anchor lines and ready-to-run comment/suggestion commands.

### 2) Add inline comment

```bash
gh-llm pr review-comment \
  --path 'paddle/phi/api/include/compat/torch/library.h' \
  --line 106 \
  --side RIGHT \
  --body 'Please add a regression test for duplicate keyword arguments.' \
  --pr 77938 --repo PaddlePaddle/Paddle
```

### 3) Add inline suggestion

```bash
gh-llm pr review-suggest \
  --path 'path/to/file' \
  --line 123 \
  --side RIGHT \
  --body 'Suggested update' \
  --suggestion 'replacement_code_here' \
  --pr 77938 --repo PaddlePaddle/Paddle
```

### 4) Submit review

```bash
gh-llm pr review-submit \
  --event COMMENT \
  --body 'Overall feedback...' \
  --pr 77938 --repo PaddlePaddle/Paddle
```

Submit behavior:

- If you already have a pending review on this PR, `review-submit` submits that pending review.
- Otherwise, it creates and submits a new review.

This supports the normal flow where one review contains multiple inline comments.

## Render Conventions

- PR/Issue metadata is rendered as frontmatter.
- Description uses `<description>...</description>`.
- Comment body uses `<comment>...</comment>` to avoid markdown fence ambiguity.
- Hidden timeline sections are separated by `---` and include expand commands.

## Development

```bash
uv run ruff check
uv run pyright
uv run pytest -q
```

## License

MIT
