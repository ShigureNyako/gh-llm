# Python lib starter

Just a template for quickly creating a python library.

<p align="center">
   <a href="https://python.org/" target="_blank"><img alt="PyPI - Python Version" src="https://img.shields.io/pypi/pyversions/moelib?logo=python&style=flat-square"></a>
   <a href="https://pypi.org/project/moelib/" target="_blank"><img src="https://img.shields.io/pypi/v/moelib?style=flat-square" alt="pypi"></a>
   <a href="https://pypi.org/project/moelib/" target="_blank"><img alt="PyPI - Downloads" src="https://img.shields.io/pypi/dm/moelib?style=flat-square"></a>
   <a href="LICENSE"><img alt="LICENSE" src="https://img.shields.io/github/license/ShigureLab/moelib?style=flat-square"></a>
   <br/>
   <a href="https://github.com/astral-sh/uv"><img alt="uv" src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json&style=flat-square"></a>
   <a href="https://github.com/astral-sh/ruff"><img alt="ruff" src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=flat-square"></a>
   <a href="https://gitmoji.dev"><img alt="Gitmoji" src="https://img.shields.io/badge/gitmoji-%20😜%20😍-FFDD67?style=flat-square"></a>
</p>

Before the work starts, replace the `moelib` with the name of your library.

## gh-llm prototype

This repo includes a `gh-llm` CLI prototype for PR timeline reading with **real GitHub cursor pagination**.

```bash
# Show PR overview and timeline page 1 + last page (server-side pagination)
gh-llm pr view 123 --repo owner/repo

# Expand a timeline page by number (loads more from GitHub API)
gh-llm pr timeline-expand 2 --pr 77900 --repo owner/repo

# Get full content of one timeline event by index
gh-llm pr event 42 --pr 77900 --repo owner/repo

# Expand resolved review comments for one or more review events
gh-llm pr review-expand PRR_xxx,PRR_yyy --pr 77900 --repo owner/repo
```

Behavior:

- Unified interface:
  `gh-llm pr view [<number>|<url>|<branch>] [--repo owner/repo] [--page-size N]`
  and `gh-llm pr timeline-expand <page> --pr ... --repo ... [--page-size N]`.
- PR metadata is rendered as frontmatter at the top, followed by the PR description body.
- Timeline data comes from GraphQL `timelineItems` cursor pagination (`first/after` and `last/before`).
- `pr view` fetches and renders page 1 + last page first, then prints actionable expand commands.
- When the last page is short, `pr view` also shows the previous page to preserve enough tail context.
- `pr timeline-expand N` fetches page `N` on-demand via server-side pagination and updates local cursor checkpoints.
- Long event bodies are truncated only when very long; use `gh-llm pr event <index>` to fetch full text.
- Resolved review comments are folded by default in timeline pages; use `gh-llm pr review-expand <PRR_ids>` to expand them in bulk.
- No local session state is required between commands. The tool only uses collision-safe keyed cache for acceleration.
- Timeline includes commit/review/comment and state events (merged/closed/reopened), with ordering matching GitHub timeline flow.
