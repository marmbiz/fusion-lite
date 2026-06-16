# Fusion Lite

<p align="center">
  <strong>Let the subscriptions you already have do the heavy lifting.</strong>
</p>

<p align="center">
  <a href="https://github.com/marmbiz/fusion-lite/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/marmbiz/fusion-lite/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-blue">
  <img alt="No runtime dependencies" src="https://img.shields.io/badge/runtime_dependencies-0-brightgreen">
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-black">
</p>

<p align="center">
  <code>Codex</code> + <code>Claude</code> + <code>Gemini</code> + <code>Kimi</code> + <code>Grok</code> + optional <code>OpenRouter</code><br>
  one local terminal report, one judge, one audit trail.
</p>

Fusion Lite is a local fusion-style multi-model CLI. It runs a prompt through a
panel of models, asks a judge model to compare the answers, and prints a
structured report with consensus, disagreements, blind spots, unique insights,
cost notes, and a final synthesis.

It is built around a simple idea:

> You already pay for strong AI tools. Use them together instead of paying again
> for every model call through one hosted router.

OpenRouter is supported and useful for cheap panel diversity. It is not the
center of the architecture. The center is your local stack: the CLIs and API
access you already use.

## Quick Demo

```bash
fusion-lite --panel fable "Review this launch positioning."
```

```text
[fusion-lite] STEP 1/3 SOURCES: running 3 panel sources
[fusion-lite] STEP 2/3 ANALYSIS: judge codex
[fusion-lite] STEP 3/3 RESULT: printing terminal output

# Fusion Report

## Sources
| Source | Status | Time | Notes |
| --- | --- | --- | --- |
| or_gemini_3_flash | ok | 18.2s | remote OpenRouter voice |
| local_kimi | ok | 41.7s | local CLI subscription |
| or_deepseek_v4_pro | ok | 22.4s | remote OpenRouter voice |

## Analysis
- Agreement: what the panel consistently sees.
- Key Differences: where model judgments diverge.
- Blind Spots: what the panel failed to check.
- Unique Insights: useful minority observations.
- Action Delta: the next concrete change.

## Final Answer
The judge synthesizes the panel into a direct answer you can act on.
```

## Why Fusion Lite Exists

OpenRouter Fusion is a hosted server-side fusion product. Fusion Lite is the
local counterpart for people who already have CLI subscriptions and want control
over orchestration, judging, artifacts, and cost.

| If you currently... | Fusion Lite lets you... |
| --- | --- |
| Ask Codex, Claude, Kimi, or Gemini one at a time | Run them as a panel from one command |
| Copy model answers into another chat manually | Generate a structured judge report automatically |
| Pay for subscriptions that sit idle during API-only workflows | Reuse those local subscriptions as panel members or judges |
| Need to see what happened after a run | Keep prompt, response, stderr, judge JSON, final answer, and metadata |
| Want OpenRouter diversity without moving everything remote | Mix OpenRouter voices with local CLI voices |

## What Makes It Different

| Feature | Fusion Lite | OpenRouter Fusion | Manual multi-model prompting |
| --- | --- | --- | --- |
| Runs locally | Yes | No | Partly |
| Uses existing CLI subscriptions | Yes | No | Yes |
| Optional OpenRouter panel voices | Yes | Yes | Yes |
| Structured judge schema | Yes | Hosted/internal | No |
| Terminal-first workflow | Yes | No | No |
| Saved local audit trail | Yes | No | Manual |
| No runtime package dependencies | Yes | N/A | N/A |

Fusion Lite is not a wrapper around OpenRouter's `openrouter:fusion` server
tool. That tool can be useful, but it runs the fusion process remotely. Fusion
Lite keeps orchestration and judging local by default.

## Features

- Parallel panel runs across local CLIs and API adapters.
- Local judge support for Codex, Claude, Gemini, Kimi, and Grok.
- Optional OpenAI, OpenRouter, and DeepSeek API adapters.
- Built-in panel presets for cheap exploration, research, code, and Fable-style review.
- Fusion-style terminal report by default.
- Machine-readable JSON output for automation.
- Saved audit trail for every run.
- Compact live progress for long-running CLI calls.
- Redacted command artifacts so prompts are not leaked through command logs.
- Panel schema validation to reject unsafe custom panel fields.
- Fixed official OpenRouter and DeepSeek API endpoints.
- `.env` key allowlisting for safer local configuration.
- Zero runtime package dependencies.

## Install

From a clone:

```bash
git clone https://github.com/marmbiz/fusion-lite.git
cd fusion-lite
pipx install .
```

For development:

```bash
python3 -m pip install -e .
```

Run from the source tree without installing:

```bash
python3 -m fusion_lite --list-panels
./fusion-lite --list-panels
```

## Configure

Create a local `.env` file or export environment variables in your shell:

```bash
cp .env.example .env
```

Minimum useful setup for OpenRouter-backed panels:

```bash
OPENROUTER_API_KEY=...
```

For OpenAI data-sharing/free-daily-token panels, use an API key from the
project where data sharing is enabled:

```bash
OPENAI_API_KEY=...
OPENAI_PROJECT=proj_...
```

Recommended local setup:

- Codex CLI authenticated.
- Claude Code authenticated.
- Any optional CLIs you want as panel voices: `gemini`, `kimi`, `grok`.

Check what Fusion Lite can see:

```bash
fusion-lite --doctor
```

`--doctor` reports available keys and binaries without printing secrets.

`.env` loading is intentionally allowlisted to Fusion/provider variables. Export
unusual local CLI environment settings in your shell instead of relying on
`.env`.

## Usage

Default run:

```bash
fusion-lite "Compare these two positioning ideas."
```

Cheapest exploratory OpenRouter run:

```bash
fusion-lite --panel openrouter-thrift "Give me a first-pass critique."
```

Use OpenRouter plus local CLI voices:

```bash
fusion-lite --panel hybrid-budget "Where do the models disagree?"
```

Use the Fable-style reliability panel:

```bash
fusion-lite --panel fable "Do the hard research synthesis."
```

Use local CLIs only:

```bash
fusion-lite --panel default "Review this argument."
```

Pin the judge and judge model when your CLI supports it:

```bash
fusion-lite --panel default --judge claude --judge-model opus "Review this package."
```

Read from stdin:

```bash
cat brief.md | fusion-lite -
```

Print only the final answer:

```bash
fusion-lite --panel fable --output final "Review this package."
```

Return machine-readable JSON:

```bash
fusion-lite --json "Give me the answer and disagreement map."
```

Dry-run without model calls:

```bash
fusion-lite --dry-run "release check"
```

Delete run artifacts after printing:

```bash
fusion-lite --panel fable --no-save "Review this package."
```

Adjust progress heartbeats:

```bash
fusion-lite --panel fable --progress-interval 15 "Review this package."
fusion-lite --panel fable --progress-interval 0 "Run quietly."
```

The heartbeat shows which adapter is still running and elapsed time. It does
not expose hidden model reasoning; final content is written only after a model
returns.

## Built-In Panels

| Panel | Best for | Shape |
| --- | --- | --- |
| `openrouter-budget` | Default low-cost analysis | OpenRouter diversity, local Claude -> Codex judge fallback |
| `openrouter-thrift` | Cheapest exploration | Very low-cost OpenRouter voices |
| `openai-free-daily` | Non-confidential OpenAI quality tests | GPT-5.4, o3, and GPT-5.4 mini through OpenAI API |
| `openai-free-daily-code` | Non-confidential code/repo reviews | `openai-free-daily` plus GPT-5.1 Codex mini |
| `openrouter-free-opinion` | Free OpenRouter exploratory critique | Free general/reasoning endpoints, excluding content-safety specialists |
| `fable` | Stronger synthesis | Gemini 3 Flash and DeepSeek V4 Pro via OpenRouter, local Kimi, judged by Codex |
| `hybrid-budget` | Mixed local/remote panel | OpenRouter budget voices plus optional local Codex and Claude |
| `default` | Local-first review | Gemini, Kimi, Grok, optional DeepSeek, Claude judge |
| `cheap` | Small local pass | Gemini and Kimi |
| `code` | Code review | Code-oriented panel with Codex as primary judge |
| `research` | Wider research/strategy | Broader local panel |

List panels:

```bash
fusion-lite --list-panels
```

Use your own panel file:

```bash
fusion-lite --panel ./my-panel.json "prompt"
```

Custom panel JSON is schema-validated. Unknown fields such as custom API
endpoints are rejected.

## Current Model Anchors

OpenRouter prices were checked against the Models API on 2026-06-14. Local CLI
entries use your authenticated subscription instead of OpenRouter billing. Treat
this table as preset rationale, not a pricing guarantee.

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

The `~...-latest` aliases are convenient, but they can silently change price
and behavior. The default panels use pinned model IDs.

## How A Run Works

```text
User prompt
    |
    v
Panel prompt
    |
    +--> model A
    +--> model B
    +--> model C
    |
    v
Judge prompt with all usable outputs
    |
    v
Structured analysis JSON
    |
    v
Terminal Fusion report + saved artifacts
```

The judge is instructed to be a mechanism judge, not just a summarizer. It
looks for consensus, disagreement, missing checks, unsupported claims,
conversion risk, and the cheapest next escalation.

## Run Artifacts

Every run writes an audit trail under `.fusion-lite/runs/<timestamp>_<panel>/`
by default:

```text
prompt.txt
panel/<model>/prompt.txt
panel/<model>/response.md
panel/<model>/result.json
panel_results.json
judge/<judge>/prompt.txt
judge/<judge>/result.json
judge/<judge>/raw.txt
judge.json
analysis.md
final.md
fusion_report.md
metadata.json
```

Change the output location:

```bash
fusion-lite --runs-dir ./runs "prompt"
FUSION_LITE_RUNS_DIR=./runs fusion-lite "prompt"
```

For local CLI reliability, Fusion Lite writes `command.txt`, `stdout.txt`, and
`stderr.txt` beside each local adapter result. The terminal report also includes
compact source and judge errors, including parsed JSON API errors from CLIs like
Claude, so `--no-save` runs remain debuggable without digging through artifacts.

## Adapters

| Adapter | Backing tool | Notes |
| --- | --- | --- |
| `openrouter_chat` | OpenRouter Chat Completions | Fixed official endpoint, needs `OPENROUTER_API_KEY` |
| `openai_api` | OpenAI Responses API | Fixed official endpoint, needs `OPENAI_API_KEY`; use only non-confidential prompts when data sharing is enabled |
| `codex_cli` | `codex exec ...` | Local CLI subscription |
| `claude_cli` | `claude -p ...` | Local CLI subscription |
| `gemini_cli` | `gemini -p ...` | Local CLI subscription |
| `kimi_cli` | `kimi --print ...` | Local CLI subscription |
| `grok_cli` | `grok -p ...` | Local CLI subscription |
| `deepseek_api` | DeepSeek API | Fixed official endpoint, needs `DEEPSEEK_API_KEY` |

Panel models run without tools. Local CLI calls are run in read-only or
plan-style modes where supported.

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

The terminal prints the Fusion-style report by default. Use `--output final` for
the compact final answer, or `--json` for machine-readable output.

`metadata.json` also includes aggregate panel metrics: success/error counts,
parallel wall-time estimate, total model compute seconds, token usage, known API
cost, and per-model usage summaries when adapters report them.

## Security And Privacy

Fusion Lite is local orchestration, not local inference. Prompts are still sent
to whichever model providers or CLIs you configure.

| Surface | What to know |
| --- | --- |
| Run artifacts | Prompt and model outputs are saved locally unless `--no-save` is used |
| API adapters | OpenRouter and DeepSeek use fixed official endpoints |
| Custom panels | Unknown fields and endpoint overrides are rejected |
| `.env` | Only known Fusion/provider keys are loaded |
| Local CLIs | `codex`, `claude`, `gemini`, `kimi`, and `grok` are resolved from `PATH` |
| Public release | `scripts/validate_release.py` scans tracked files for obvious secrets |

Do not run confidential prompts unless the configured providers and local
environment are acceptable for that data. See `SECURITY.md` for the full policy.

## Public Release Checks

```bash
python3 scripts/validate_release.py
```

This compiles the package, validates panel JSON/schema constraints, scans
tracked files for obvious secrets, checks pinned CI actions and `.env` key
allowlisting, checks `--list-panels`, checks the default dry-run, and confirms
`--doctor` does not print secret values.

## Project Status

Fusion Lite is alpha software. The core contract is intentionally small:

- run a panel;
- preserve enough evidence to debug it;
- judge the panel with a stronger or trusted local model;
- print a useful terminal report.

The next improvements should stay in that lane: adapter reliability, better
panel presets, stronger tests, and clearer report ergonomics.
