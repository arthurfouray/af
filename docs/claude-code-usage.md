# Cutting Fable token/usage burn

Notes behind `.claude/settings.json`. Figures are list prices from the Claude API
model table; behaviour is from the Claude Code docs (`/docs/en/costs`,
`/docs/en/model-config`) and the settings JSON Schema
(`https://json.schemastore.org/claude-code-settings.json`). Verified 2026-09-14.

## The budget you are spending

Subscription usage resets on a rolling **five-hour window**, shared across Claude
Code, Claude chat, and Cowork. At **3% per 10 minutes**, five hours of continuous
work costs ~90% of the window — nearly all of it, with no slack for a cache miss
or a long-running loop. Getting to ~1% per 10 minutes puts a full working session
at ~30% of the window.

## What Fable costs relative to the alternatives

| Model | Input $/MTok | Output $/MTok |
|---|---|---|
| Claude Fable 5.1 | $10.00 | $50.00 |
| Claude Opus 5 | $5.00 | $25.00 |
| Claude Sonnet 5 | $2.00 | $10.00 |
| Claude Haiku 4.5 | $1.00 | $5.00 |

Fable is **2× Opus 5** and **5× Sonnet 5** per token. Model choice is the single
largest lever; nothing below comes close to it. Thinking tokens bill as output
tokens, at the $50 rate.

## What does *not* work on Fable

Fable always uses extended thinking and it cannot be turned off. These are no-ops
on Fable, so don't reach for them:

- `MAX_THINKING_TOKENS` (including `=0`)
- `alwaysThinkingEnabled`
- the `Option+T` / `Alt+T` session toggle
- `CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING`

On Fable the only in-model control is the **effort level**.

## What the committed settings do

### Effort

`effortLevel: "high"` plus `modelSettings.<model>.effortLevel: "high"` — the
valid levels are `low`, `medium`, `high`, `xhigh`. (`max` is accepted only by
`maxEffortLevel`, not by `effortLevel`.) Per-model settings beat the global
`effortLevel`, and a level saved from `/effort` or the `/model` picker persists
across sessions, so a one-off `xhigh` can quietly become your default. Pinning
`high` per model in project settings overrides that. `high` is the quality/cost
balance point and is kept deliberately — the brief was to spend less *without*
losing quality. Use the `ultrathink` keyword in a single prompt when one turn
needs more depth; it does not change the session's effort level.

`maxEffortLevel: "high"` (global and per model) is the actual drift guard. It is
a client-side ceiling, and across settings files **the lowest value wins**, so a
`max` saved in your user settings cannot raise this repo above `high`.

Keys are named `effortLevel` / `maxEffortLevel` inside `modelSettings`. A prose
example in the docs shows `"effort"`; the JSON Schema does not define that key,
so a `"effort"` entry is silently ignored.

### Context size

`autoCompactWindow: 200000` — this is the big one. On 1M-context models like
Fable, Claude Code does not auto-compact until **~967K tokens**. Every request
re-sends the whole conversation, so an uncapped session drifts toward paying for
a ~900K-token context on *every turn*:

| Context carried | Per request, cache hit ($0.25/MTok) | Per request, cache miss ($10/MTok) |
|---|---|---|
| ~900K (default) | ~$0.22 | ~$9.00 |
| 200K (this repo) | ~$0.05 | ~$2.00 |

The cap is a safety net, not a constant cost — most sessions never reach 200K.
It only bites on the long sessions that cause runaway usage. Raise it if
compaction starts losing context you need (schema range: 100000–1000000).

### Fan-out

`workflowKeywordTriggerEnabled: false` — stops the literal word "ultracode" in a
prompt from launching a multi-agent workflow. Workflows fan out to many agents at
Fable prices; that should be an explicit request, not a keyword accident.

`workflowSizeGuideline: "small"` — if a workflow *is* run deliberately, keep it
under ~5 agents.

(The `ultracode` setting itself is session-scoped — passed via `--settings` or a
control request — so putting `ultracode: false` in project settings does nothing.
An earlier draft of this file claimed otherwise.)

### Tool output

`bashOutputMaxChars: 8000` and `taskOutputMaxChars: 8000` (defaults 30000 and
32000; both clamp to 4000–128000). Oversized output is **written to a file and
the path returned**, so nothing is lost — you opt back in by reading the part you
want instead of paying for the whole dump on every subsequent turn.

### Prompt surface

`enableAllProjectMcpServers: false` — no project MCP server is auto-approved.
Each server's instructions load into the system prompt and are re-sent every
turn. This repo needs none of them.

`promptSuggestionEnabled: false` — drops the background suggestion calls.

### Permissions

`permissions.allow` pre-approves the read-only tools this repo actually uses
(`Read`, `Glob`, `Grep`, read-only `git`, `ls`, `wc`, `file`, `find`, `jq`,
`base64`, `gzip`, `mkdir -p`). Fewer permission round-trips means fewer turns,
and each turn re-sends the whole context.

`permissions.deny` blocks `Read` on `payload/*.b64` and
`payload/final_chunks/*.b64` outright.

### Hooks

Two `PreToolUse` hooks enforce the CLAUDE.md rule "never read the `.b64` files
directly". The payload files total ~26 KB of base64 — roughly 2K unreadable
tokens each, and re-sent on every subsequent turn once they are in context.

- **matcher `Read`** — denies any `file_path` ending in `.b64`.
- **matcher `Bash`** — denies a dump utility *invoked* on a `.b64` path. The
  regex anchors to command position (start of line, or after `;`, `&`, `|`,
  `do`, `then`) and its path span excludes newlines, so mentioning a filename
  inside a string, and the repo's own decode/re-encode pipelines, both pass.

Both hooks return a `permissionDecision: "deny"` whose reason repeats the decode
command, so the block teaches the fix rather than just failing.

Test matrix used: 5 `Read` cases and 14 `Bash` cases, including both commands
quoted verbatim in CLAUDE.md. All pass.

## Levers deliberately not used

Each of these saves tokens but trades away accuracy, so they are left at their
defaults:

- `skillListingMaxDescChars` / `skillListingBudgetFraction` — truncating skill
  descriptions degrades skill selection.
- `promptCacheTtl` / `subagentPromptCacheTtl` — unset already gives 1h on a
  subscription; pinning a value can force costlier cache writes on an API key.
- `disableBundledSkills` — removes capability, not overhead.
- `cleanupPeriodDays` — reclaims disk, not tokens.
- `precomputeCompactionEnabled` — makes compaction slower, not cheaper.
- Dropping `effortLevel` to `medium` — the largest remaining lever, and the one
  that most directly costs quality. Left to you, per task, via `/effort`.

## Optional opt-in

`disableClaudeAiConnectors: true` is the next-largest prompt-size lever: every
connected claude.ai MCP server injects an instruction block into the system
prompt on every turn, and a session with a dozen connectors carries a lot of
text it never uses.

It is **not** committed because any-source-true wins (a project can opt out, but
a project-level `false` cannot undo a user-level `true`), and because a remote
Claude Code session reaches GitHub entirely through the `github` MCP server —
turning connectors off there can remove your ability to open or update a PR.
Add it to `.claude/settings.local.json` if you work locally with a `gh` CLI:

```json
{ "disableClaudeAiConnectors": true }
```

## Habits that beat any setting

1. **`/clear` between unrelated tasks.** Free, and it resets the per-turn cost of
   every later message. `/compact` is *not* free — summarizing a large context is
   itself a large request. Use `/rename` then `/resume` if you need the session back.
2. **Match the model to the job.** `/model` to Sonnet 5 for mechanical work, Fable
   only for genuinely hard reasoning. Model-specific limit messages ("you've hit
   your Opus limit") let you keep working by switching; session/weekly limits don't.
3. **Mind the cache.** Cache reads cost $0.25/MTok against $10/MTok cold — a 40×
   difference. The cached prefix lives **1 hour** on a subscription, dropping to
   **5 minutes** once you're drawing on usage credits. Coming back to a big session
   after lunch reprocesses the whole thing at full price.
4. **Watch idle burn.** Scheduled tasks and `/loop` fire on their interval even
   when the session is idle, each sending the full context. Agent teams use ~7×
   the tokens of a standard session.
5. **Ask narrowly.** "Add validation to `login` in auth.ts" reads two files;
   "improve this codebase" reads fifty.

## Diagnosing before tuning further

- `/usage` — plan bars plus a breakdown attributing recent usage to skills,
  subagents, plugins, and individual MCP servers, and **behaviour flags** for
  anything accounting for ≥10% (long context, cache misses). Press `d`/`w` for
  24h vs 7d. Start here; it names the actual culprit.
- `/context` — what is occupying the context window right now.
- `/mcp` — disable servers you aren't using. Tool definitions are deferred by
  default, so this matters less than it used to, but server instructions still load.
- `/hooks` — review, edit, or disable the two hooks above.
- `/insights` — HTML report on recent sessions, written to `~/.claude/usage-data/`.

## Scope

These settings are project-scoped. Shared project settings override user
settings, so they apply to this repo regardless of your personal defaults. To get
the same behaviour everywhere, copy the keys into `~/.claude/settings.json`.
Note that `maxEffortLevel` is the exception: the lowest value across all settings
files wins, so a user-level ceiling still applies on top of this one.
