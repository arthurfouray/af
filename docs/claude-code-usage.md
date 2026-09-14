# Cutting Fable token/usage burn

Notes behind `.claude/settings.json`. Figures are list prices from the Claude API
model table; behaviour is from the Claude Code docs (`/docs/en/costs`,
`/docs/en/model-config`). Verified 2026-09-14.

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

`effortLevel` / `modelSettings.effort` — effort runs `low` → `medium` → `high` →
`xhigh` → `max`, defaulting to `high`. Per-model saved levels beat the global
`effortLevel`, and a level saved from `/effort` or the `/model` picker persists
across sessions, so a one-off `max` can quietly become your default. Pinning
`high` per model in project settings overrides that. `high` is the
quality/cost balance point; drop to `medium` for routine work where you can
accept some loss, and use the `ultrathink` keyword in a single prompt when one
turn needs more depth — it does not change the session's effort level.

`ultracode: false` — `ultracode` sends `xhigh` effort *and* orchestrates dynamic
workflows. It is a deliberate spend, not a default.

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
compaction starts losing context you need.

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
- `/insights` — HTML report on recent sessions, written to `~/.claude/usage-data/`.

## Scope

These settings are project-scoped. Shared project settings override user
settings, so they apply to this repo regardless of your personal defaults. To get
the same behaviour everywhere, copy the keys into `~/.claude/settings.json`.
