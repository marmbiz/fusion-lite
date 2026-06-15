# Fusion Lite

Let the subscriptions you already have do the heavy lifting.

Fusion Lite is a local fusion-style orchestrator for people who already use tools like Codex CLI, Claude Code, Gemini, Kimi, Grok, or OpenRouter and want those existing subscriptions to work together as a model panel.

OpenRouter can add cheap diversity, but it is not the center of the architecture. The center is your local stack: the CLIs and API access you already pay for, combined with a judge that turns separate model outputs into a structured Fusion-style report.

## What It Does

- Calls several independent panel models in parallel.
- Uses local CLI subscriptions as panel members or judges.
- Uses OpenRouter budget models as optional cheap diversity.
- Uses a judge model such as Codex, Claude, Gemini, Kimi, or Grok for analysis and final synthesis.
- Captures command, stdout, stderr, status, elapsed time, and compact terminal error details for local CLI adapters.
- Saves the raw panel responses, judge prompt, judge JSON, analysis markdown, final answer, Fusion-style report, and metadata for each run.
- Summarizes panel success, latency, token usage, and known API cost so runs can be compared on quality, speed, and price.
- Uses plain Python and the standard library. No runtime package dependencies.

It is not a wrapper around OpenRouter's `openrouter:fusion` server tool. That tool is useful, but it runs both panel and judge remotely. Fusion Lite keeps the final judge local by default.

## Install

From a local clone:

```bash
git clone https://github.com/martinmoellerbiz/fusion-lite.git
cd fusion-lite
pipx install .
```

For development:

```bash
python3 -m pip install -e .
```

You can also run from the source tree without installing:

```bash
python3 -m fusion_lite --list-panels
./fusion-lite --list-panels
```

## Configure

Create a local `.env` file or export environment variables in your shell:

```bash
cp .env.example .env
```

`.env` loading is intentionally allowlisted to Fusion/provider variables. Export unusual local CLI environment settings in your shell instead of relying on `.env`.

Minimum useful setup:

```bash
OPENROUTER_API_KEY=...
```

Recommended local judge setup:

- Codex CLI authenticated, or
- Claude Code authenticated, or
- both.

Check the environment:

```bash
fusion-lite --doctor
```

`--doctor` reports whether keys and CLI binaries are available. It does not print secrets.

## Quick Start

Default run:

```bash
fusion-lite "Compare these two positioning ideas."
```

The default panel is `openrouter-budget`: pinned low-cost OpenRouter voices with local Claude -> Codex judge fallback.

Cheapest exploratory run:

```bash
fusion-lite --panel openrouter-thrift "Give me a first-pass critique."
```

Use OpenRouter plus local CLI voices as extra panel members:

```bash
fusion-lite --panel hybrid-budget "Where do the models disagree?"
```

Use the Fable-style budget panel from OpenRouter's Fusion notes:

```bash
fusion-lite --panel fable "Do the hard research synthesis."
```

Pin a local judge model alias for the primary judge when your CLI supports it. Fallback judges keep their own default model:

```bash
fusion-lite --panel default --judge claude --judge-model opus "Review this package."
```

Use local CLIs only:

```bash
fusion-lite --panel default "Review this argument."
```

Machine-readable output:

```bash
fusion-lite --json "Give me the answer and disagreement map."
```

By default, Fusion Lite prints a Fusion-style three-step report directly in the terminal:

```bash
fusion-lite --panel fable "Review this package."
```

Terminal only, without keeping the run artifacts:

```bash
fusion-lite --panel fable --no-save "Review this package."
```

During the run, stderr shows the same phase structure:

```text
[fusion-lite] STEP 1/3 SOURCES: running 3 panel sources
[fusion-lite] STEP 2/3 ANALYSIS: judge codex
[fusion-lite] STEP 3/3 RESULT: printing terminal output
```

Print only the final answer when you need the old compact output:

```bash
fusion-lite --panel fable --output final "Review this package."
```

Long-running local CLI calls print progress heartbeats to stderr every 30 seconds by default:

```bash
fusion-lite --panel fable --progress-interval 15 "Review this package."
fusion-lite --panel fable --progress-interval 0 "Run quietly."
```

The heartbeat shows which adapter is still running and elapsed time. It does not expose hidden model reasoning; final content is still written only after the model returns.

For local CLI reliability, Fusion Lite writes `command.txt`, `stdout.txt`, and `stderr.txt` beside each local adapter result. The terminal report also includes compact source and judge errors, including parsed JSON API errors from CLIs like Claude, so `--no-save` runs remain debuggable without digging through artifacts.

Read a prompt from stdin:

```bash
cat brief.md | fusion-lite -
```

Dry-run without model calls:

```bash
fusion-lite --dry-run "release check"
```

## Panels

Built-in presets:

| Panel | Use |
| --- | --- |
| `openrouter-budget` | Default. Strong low-cost OpenRouter diversity, local Claude -> Codex judging. |
| `openrouter-thrift` | Very cheap exploratory panel. |
| `fable` | Reliability-first Fable-style panel: Gemini 3 Flash and DeepSeek V4 Pro through OpenRouter, local Kimi, judged by Codex. |
| `hybrid-budget` | OpenRouter budget panel plus optional local Codex and Claude panel voices. |
| `default` | Older local-CLI-first panel: Gemini, Kimi, Grok, optional DeepSeek. |
| `cheap` | Small local panel: Gemini and Kimi. |
| `code` | Code-oriented panel with Codex as primary judge. |
| `research` | Wider local research/strategy panel. |

List available panels:

```bash
fusion-lite --list-panels
```

Use a custom panel file:

```bash
fusion-lite --panel ./my-panel.json "prompt"
```

## Current Panel Model Anchors

OpenRouter prices were checked against the Models API on 2026-06-14. Local CLI entries use your local authenticated subscription instead of OpenRouter billing. Treat this table as a preset rationale, not a guarantee.

| Model | Panel use | Input / output per 1M tokens |
| --- | --- | --- |
| `z-ai/glm-4.7-flash` | thrift | $0.06 / $0.40 |
| `deepseek/deepseek-v4-flash` | thrift | $0.09 / $0.18 |
| `google/gemini-2.5-flash-lite` | thrift | $0.10 / $0.40 |
| `minimax/minimax-m2.5` | thrift | $0.15 / $0.90 |
| `google/gemini-3-flash-preview` | fable | $0.50 / $3.00 |
| local `kimi` CLI | fable | Uses your local Kimi CLI subscription |
| `deepseek/deepseek-v4-pro` | fable, budget | $0.435 / $0.87 |
| `minimax/minimax-m3` | budget | $0.30 / $1.20 |
| `google/gemini-3.1-flash-lite` | budget | $0.25 / $1.50 |
| `moonshotai/kimi-k2.5` | budget | $0.375 / $2.025 |
| `z-ai/glm-5.1` | budget | $0.98 / $3.08 |

The `~...-latest` aliases are convenient, but they can silently change price and behavior. The default panels use pinned model IDs.

## Run Artifacts

Every run writes an audit trail under `.fusion-lite/runs/<timestamp>_<panel>/` by default:

- `prompt.txt`
- `panel/<model>/prompt.txt`
- `panel/<model>/response.md`
- `panel/<model>/result.json`
- `panel_results.json`
- `judge/<judge>/prompt.txt`
- `judge/<judge>/result.json`
- `judge/<judge>/raw.txt`
- `judge.json`
- `analysis.md`
- `final.md`
- `fusion_report.md`
- `metadata.json`

Change the output location:

```bash
fusion-lite --runs-dir ./runs "prompt"
FUSION_LITE_RUNS_DIR=./runs fusion-lite "prompt"
```

## Adapters

Supported adapters:

- `openrouter_chat`: OpenRouter Chat Completions on the fixed official endpoint, enabled by `OPENROUTER_API_KEY`.
- `codex_cli`: `codex exec ...`
- `claude_cli`: `claude -p ...`
- `gemini_cli`: `gemini -p ...`
- `kimi_cli`: `kimi --print ...`
- `grok_cli`: `grok -p ...`
- `deepseek_api`: direct DeepSeek API on the fixed official endpoint, enabled by `DEEPSEEK_API_KEY`.

Panel models run without tools. Local CLI calls are run in read-only or plan-style modes where supported.

## Judge Output

The judge returns structured JSON and a readable `analysis.md` with:

- task class;
- agreement;
- key differences;
- partial coverage;
- unique insights;
- blind spots with panel/judge provenance;
- mechanism check;
- consensus risks;
- minority report;
- judge-inferred blind spots;
- unsupported or risky claims;
- conversion verdict;
- strongest objection;
- top strengths and improvements;
- synthesis strategy;
- action delta, repeated near the final result in report mode;
- schema warnings for missing or malformed judge fields;
- answer sufficiency;
- disagreement score;
- escalation recommendation;
- cost/quality notes;
- final answer.

The terminal prints the Fusion-style report by default. Use `--output final` for the compact final answer, or `--json` for machine-readable output.

`metadata.json` also includes aggregate panel metrics: success/error counts,
parallel wall-time estimate, total model compute seconds, token usage, known API
cost, and per-model usage summaries when adapters report them.

## Public Release Checks

```bash
python3 scripts/validate_release.py
```

This compiles the package, validates panel JSON/schema constraints, scans tracked files for obvious secrets, checks pinned CI actions and `.env` key allowlisting, checks `--list-panels`, checks the default dry-run, and confirms `--doctor` does not print secret values.
