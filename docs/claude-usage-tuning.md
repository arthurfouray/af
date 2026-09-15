# Cutting Claude usage without losing quality

Reference for tuning Claude Code sessions (Fable 5.1 / Opus) against a rolling 5-hour usage
window. Not auto-loaded into sessions — open it when you want to change settings.

## What the meter actually tracks

Usage tracks **tokens**, weighted by model price. Current list prices:

| Model | Input $/MTok | Output $/MTok | Relative to Fable 5.1 |
|---|---|---|---|
| Claude Fable 5.1 (`claude-fable-5-1`) | $10 | $50 | 1× |
| Claude Opus 5 (`claude-opus-5`) | $5 | $25 | 0.5× |
| Claude Sonnet 5 (`claude-sonnet-5`) | $2 | $10 | 0.2× |
| Claude Haiku 4.5 (`claude-haiku-4-5`) | $1 | $5 | 0.1× |

Opus 5 in **fast mode** is billed at $10/$50 — the same rate as Fable 5.1, i.e. **2× standard
Opus** for the same model.

Three facts drive everything below:

1. **Output costs 5× input.** Thinking tokens are billed as output. On Fable 5.1 that is
   $50/MTok, so reasoning depth — not context size — is usually the largest line item.
2. **Cached input is nearly free.** A cache read on Fable 5.1 is $0.25/MTok, 1/40th of fresh
   input. A stable system prompt and an untouched conversation prefix cost almost nothing to
   re-send; *new* tool output and file reads cost full price, on that turn and every turn after.
3. **Fable 5.1 cannot turn thinking off.** `thinking: {type: "disabled"}` returns a 400. The only
   depth lever is `effort` (`low` → `max`).

### Sanity-checking the burn rate

10 minutes is 3.3% of a 5-hour window. So "3% in 10 minutes" is roughly **one window per 5 hours
of continuous generation** — the expected rate if the model is actively working the whole time on
the most expensive model available. It is too fast if much of that time was you reading, typing,
or waiting: that means each turn is re-billing a large context or thinking harder than the task
needs. The levers below target exactly those two.

## Levers, highest payoff first

### 1. Model per task (up to 80%)

Fable 5.1 is 2× Opus 5 and 5× Sonnet 5 per token. Reserve Fable 5.1 for genuinely hard,
long-horizon work; `/model opus` for normal engineering; `/model sonnet` for mechanical edits,
test running, and log triage. Lower effort on a newer model frequently beats high effort on an
older one, so step down the model before you compromise on effort.

Caches are model-scoped: switching mid-session forfeits the cached prefix. Pick at session start.

### 2. Fast mode (50% on Opus)

`/fast` doubles the per-token price for faster output, and it persists across sessions. Check
`/status`; leave it off unless you are latency-bound. `"fastModePerSessionOptIn": true` (set in
this repo's `.claude/settings.json`) stops it from silently carrying over.

### 3. Effort level (30–50% of output tokens)

Claude Code defaults to `xhigh`. `/effort high` is close to free in quality on most work;
`/effort medium` is right for routine edits, refactors, and log reading. Keep `xhigh`/`max` for
debugging something genuinely subtle. Lower effort also produces fewer, more consolidated tool
calls and less preamble, which compounds the saving.

Persist a default with `"effortLevel"` in settings (`low`/`medium`/`high`/`xhigh`; `max` is
session-only via `/effort`).

### 4. Session hygiene (highly variable, often the biggest real-world win)

Every turn re-bills the whole conversation. Uncached context is what makes a long session expensive:

- `/clear` between unrelated tasks. A fresh session on the next task is cheaper than continuing.
- `/compact` when a long session is still on-topic but has accumulated dead tool output.
- Don't dump whole files or full CI logs into context — `grep -n` then `sed -n 'A,Bp'`.
- Avoid re-reading a file you just edited; the edit already told you it applied.
- Answer-shaped questions ("what does X do?") are cheaper in a new session than at the end of a
  long one.

### 5. Subagents, workflows, agent teams

Each subagent runs its own context and its own model. One fan-out workflow can cost more than the
task that spawned it. Use them for real parallel breadth; run them on Sonnet unless the subtask
needs judgment. Settings: `CLAUDE_CODE_SUBAGENT_MODEL`, `teammateDefaultModel`,
`workflowSizeGuideline`.

### 6. Fixed per-turn overhead

Smaller than the above, because it caches well, but it is paid on every cache miss:

- **MCP connectors.** Each connected connector contributes tool schemas. Disconnect the ones you
  do not use for this project (`/mcp`, or `"disableClaudeAiConnectors": true` to drop claude.ai
  connectors entirely for a project).
- **Skill listing.** Sent every turn, budgeted at 1% of the context window by default. Trim with
  `"skillListingBudgetFraction"` / `"skillListingMaxDescChars"`, or hide unused skills with
  `"skillOverrides"`. `"disableBundledSkills": true` removes the bundled set outright.
- **CLAUDE.md.** It is re-sent every turn, so keep it short — a 200-line CLAUDE.md is a standing tax.

## Recommended user-level settings

Merge into `~/.claude/settings.json` (applies to every project; this repo's
`.claude/settings.json` only covers sessions here):

```json
{
  "effortLevel": "high",
  "fastModePerSessionOptIn": true,
  "skillListingBudgetFraction": 0.005,
  "skillListingMaxDescChars": 600,
  "teammateDefaultModel": "sonnet",
  "workflowSizeGuideline": "small",
  "env": {
    "CLAUDE_CODE_SUBAGENT_MODEL": "sonnet"
  }
}
```

Optional, more aggressive: `"disableBundledSkills": true`, `"disableWorkflows": true`,
`"disableClaudeAiConnectors": true`, `"autoMemoryEnabled": false`. Each removes a capability —
add them only if you do not use it.

## What does *not* help

- Turning off `showThinkingSummaries` or `verbose` — display settings; the tokens are billed
  either way.
- Forcing short replies — response prose is a rounding error next to thinking and context.
- Disabling `autoCompactEnabled` — compaction *reduces* what gets re-sent on long sessions.
