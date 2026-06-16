# Changelog

## 0.1.1 - 2026-06-15

- Add judge JSON schema normalization with visible schema warnings for missing or malformed judge fields.
- Enforce blind-spot provenance by marking panel-derived vs. judge-inferred blind spots.
- Add evidence support for key differences and repeat Action Delta near the final report result.
- Add a release-version helper and checklist steps that derive the Git tag from validated project/package/changelog versions.
- Add release validation for source/packaged panel drift and broader `--doctor` secret-output checks.
- Add macOS to the CI matrix and make generated-artifact release checks explicit.
- Prevent panel JSON from overriding OpenRouter/DeepSeek API endpoints, add panel schema validation, redact Codex prompts in command artifacts, and harden CI action pinning.
- Restrict `.env` loading to known Fusion/provider keys instead of importing arbitrary process variables.
- Add OpenAI Responses API support plus a non-confidential `openai-free-daily` panel for data-sharing/free-daily-token projects.
- Make `openai-free-daily` quality-first with GPT-5.4, o3, and GPT-5.4 mini; add `openai-free-daily-code` for Codex-mini code/repo reviews.
- Add `openrouter-free-opinion` for exploratory critique using free OpenRouter general/reasoning endpoints.

## 0.1.0 - 2026-06-14

- Initial public release scaffold.
- Add OpenRouter budget, thrift, and hybrid panels.
- Add Fable-style panel with Gemini 3 Flash, local Kimi CLI, local Claude Sonnet, and DeepSeek V4 Pro, judged by local Claude Opus.
- Disable reasoning for the Fable panel's OpenRouter members so long review prompts produce answer text instead of reasoning-only token exhaustion.
- Add local CLI adapters for Codex, Claude, Gemini, Kimi, Grok, and direct DeepSeek API.
- Add local Claude/Codex judge fallback.
- Scope `--judge-model` to the primary judge only, so a Claude Opus judge does not accidentally force `opus` onto the Codex fallback.
- Add progress heartbeats for long-running local CLI calls, including Claude Opus judging.
- Add local CLI reliability diagnostics: command/stdout/stderr artifacts, compact terminal error reporting, Claude `--max-turns`, Kimi iteration caps, Kimi resume-line cleanup, and Kimi default-model provenance.
- Raise the Fable panel's local Kimi timeout to 600s after full codebase-audit testing showed 360s was too tight for large prompts.
- Make the Fable panel reliability-first by removing quota-sensitive local Claude Sonnet and Claude Opus judge from the default Fable path; Codex now judges the stable three-source panel.
- Add mechanism-judge synthesis fields: mechanism checks, consensus-risk detection, promoted minority views, judge-inferred blind spots, synthesis strategy, and action delta.
- Add `fusion_report.md` and `--output report` for a Fusion-style three-step view: sources, analysis, result.
- Make the Fusion-style report the default terminal output; use `--output final` for compact answer-only output.
- Add live terminal phase markers for sources, analysis, and result.
- Add `--no-save` for terminal-only runs that delete artifacts after printing.
- Add per-run panel metrics, token usage, known API cost summaries, and judge sufficiency/escalation fields.
- Save raw panel responses, judge JSON, analysis markdown, final answer, and metadata per run.
- Add `--doctor`, `--runs-dir`, `--list-panels`, `--show-panel`, and `--dry-run`.
