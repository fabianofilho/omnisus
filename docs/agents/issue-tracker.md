# Issue tracker: GitHub

Issues and plans for this repo live in the GitHub Issues of `raphaelfh/omnisus`.
Use `gh`, the GitHub web UI, or any GitHub tool (for example the GitHub MCP
server in Claude Code on the web). Labels are in `triage-labels.md`.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs
as feature requests; triage skills such as `/triage` read this flag.)_

When set to `yes`, external PRs (author association `CONTRIBUTOR`,
`FIRST_TIME_CONTRIBUTOR` or `NONE`) go through the same labels and states as
issues.

GitHub shares one number space across issues and PRs, so a bare `#42` may be
either: check whether it is a PR first, then fall back to the issue.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Read the GitHub issue with its comments and labels.
