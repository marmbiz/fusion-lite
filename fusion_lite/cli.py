from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import shutil
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any

from .adapters import AdapterResult, render_command, run_adapter, shell_join
from .prompts import build_judge_prompt, build_panel_prompt
from . import __version__


SOURCE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PANELS_DIR = SOURCE_ROOT / "panels"
PACKAGE_PANELS_DIR = "panels"
DEFAULT_RUNS_DIR = Path(".fusion-lite") / "runs"
DEFAULT_JUDGE_TIMEOUT = 240
JUDGE_LIST_FIELDS = (
    "agreement",
    "key_differences",
    "partial_coverage",
    "unique_insights",
    "blind_spots",
    "mechanism_check",
    "consensus_risks",
    "minority_report",
    "judge_inferred_blind_spots",
    "unsupported_or_risky_claims",
    "model_quality",
    "top_strengths",
    "top_improvements",
    "action_delta",
    "cost_quality_notes",
)
JUDGE_DICT_FIELDS = (
    "conversion_verdict",
    "strongest_objection",
    "consensus_vs_disputes",
    "synthesis_strategy",
    "escalation_recommendation",
)
JUDGE_SCALAR_DEFAULTS: dict[str, Any] = {
    "task_class": "other",
    "answer_sufficiency": "partial",
    "disagreement_score": None,
    "confidence": "low",
    "final_answer": "",
}
ALLOWED_PANEL_FIELDS = {
    "name",
    "description",
    "price_basis",
    "judge",
    "judge_model",
    "judge_timeout_seconds",
    "fallback_judge",
    "members",
}
ALLOWED_PANEL_MEMBER_FIELDS = {
    "id",
    "adapter",
    "model",
    "optional",
    "timeout_seconds",
    "provider_sort",
    "temperature",
    "max_tokens",
    "reasoning",
    "max_steps_per_turn",
    "max_ralph_iterations",
    "max_retries_per_step",
    "thinking",
    "agent",
    "effort",
    "max_turns",
}
ALLOWED_PANEL_ADAPTERS = {
    "gemini_cli",
    "kimi_cli",
    "grok_cli",
    "claude_cli",
    "codex_cli",
    "deepseek_api",
    "openrouter_chat",
}
ALLOWED_JUDGES = {"claude", "codex", "gemini", "kimi", "grok"}
DOTENV_ALLOWED_KEYS = {
    "ANTHROPIC_API_KEY",
    "CLAUDE_API_KEY",
    "DEEPSEEK_API_KEY",
    "FUSION_LITE_RUNS_DIR",
    "GEMINI_API_KEY",
    "GROK_API_KEY",
    "KIMI_API_KEY",
    "MOONSHOT_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENROUTER_HTTP_REFERER",
    "OPENROUTER_SITE_URL",
    "OPENROUTER_TITLE",
    "XAI_API_KEY",
}


def main(argv: list[str] | None = None) -> int:
    load_dotenv_candidates()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"fusion-lite {__version__}")
        return 0

    if args.doctor:
        print_doctor()
        return 0

    if args.list_panels:
        list_panels()
        return 0

    user_prompt = read_prompt(args.prompt)
    if not user_prompt.strip():
        parser.error("prompt is required; pass text, '-' for stdin, or pipe stdin")

    panel_config = load_panel(args.panel)
    if args.show_panel or args.dry_run:
        print_panel(panel_config, args)
        if args.dry_run:
            return 0

    runs_root = resolve_runs_dir(args.runs_dir)
    run_dir = make_run_dir(panel_config["name"], runs_root)
    (run_dir / "panel").mkdir(parents=True, exist_ok=True)
    write_text(run_dir / "prompt.txt", user_prompt)
    write_json(run_dir / "panel_config.json", panel_config)

    started = time.monotonic()
    members = panel_config.get("members", [])
    panel_prompt = build_panel_prompt(user_prompt)
    emit_live_step(args, "STEP 1/3 SOURCES", f"running {len(members)} panel sources")
    panel_results = run_panel(members, panel_prompt, run_dir, args.timeout, args.progress_interval)
    write_json(run_dir / "panel_results.json", panel_results)
    panel_summary = summarize_panel_results(panel_results)
    usage_summary = summarize_usage(panel_results)
    emit_live_step(
        args,
        "STEP 1/3 SOURCES",
        f"complete {panel_summary.get('ok', 0)}/{panel_summary.get('total', len(panel_results))}; slowest={panel_summary.get('slowest_model')}",
    )

    ok_results = [result for result in panel_results if result["status"] == "ok" and result.get("content", "").strip()]
    if not ok_results:
        write_json(
            run_dir / "metadata.json",
            {
                "status": "error",
                "error": "no panel model returned usable content",
                "panel_summary": panel_summary,
                "usage_summary": usage_summary,
                "elapsed_seconds": round(time.monotonic() - started, 3),
            },
        )
        print(f"No panel model returned usable content. See {run_dir}", file=sys.stderr)
        cleanup_run_dir(args, run_dir)
        return 2

    judge_candidates = choose_judges(args.judge, panel_config, no_fallback=args.no_judge_fallback)
    judge_model = choose_judge_model(args.judge_model, panel_config)
    judge_prompt = build_judge_prompt(user_prompt, ok_results)
    judge_timeout = choose_judge_timeout(args, panel_config)
    emit_live_step(args, "STEP 2/3 ANALYSIS", f"judge {' -> '.join(judge_candidates)}")
    judge_json, judge_used, judge_attempts = run_judges(
        judge_candidates,
        judge_prompt,
        run_dir,
        judge_timeout,
        judge_model,
        args.progress_interval,
    )
    emit_live_step(args, "STEP 2/3 ANALYSIS", f"complete judge_used={judge_used or 'none'}")
    if judge_json is None:
        judge_json = {
            "task_class": "other",
            "confidence": "low",
            "answer_sufficiency": "partial",
            "disagreement_score": None,
            "escalation_recommendation": {
                "should_escalate": True,
                "reason": "All judges failed, so the final answer is only a fallback synthesis from panel outputs.",
                "cheapest_next_step": "use a stronger panel",
            },
            "cost_quality_notes": ["Judge failure prevents reliable quality calibration."],
            "missing_checks": ["All judges failed; final answer uses fallback synthesis from panel outputs."],
            "final_answer": fallback_final_answer(ok_results),
            "judge_attempts": judge_attempts,
        }

    judge_json = normalize_judge_json(judge_json)
    final_answer = str(judge_json.get("final_answer") or "").strip() or fallback_final_answer(ok_results)
    metadata = {
        "status": "ok",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "panel": panel_config["name"],
        "judge_requested": judge_candidates[0],
        "judge_model_requested": judge_model,
        "judge_used": judge_used,
        "judge_attempts": judge_attempts,
        "run_dir": str(run_dir),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "panel_status": {result["id"]: result["status"] for result in panel_results},
        "panel_summary": panel_summary,
        "usage_summary": usage_summary,
    }
    fusion_report = render_fusion_report(user_prompt, panel_results, judge_json, metadata)

    write_json(run_dir / "judge.json", judge_json)
    write_text(run_dir / "analysis.md", render_analysis_markdown(judge_json) + "\n")
    write_text(run_dir / "final.md", final_answer + "\n")
    write_text(run_dir / "fusion_report.md", fusion_report + "\n")
    write_json(run_dir / "metadata.json", metadata)

    emit_live_step(args, "STEP 3/3 RESULT", "printing terminal output")
    if args.json:
        print(json.dumps({"metadata": metadata, "judge": judge_json, "final_answer": final_answer, "fusion_report": fusion_report}, ensure_ascii=False, indent=2))
    elif args.output == "report":
        print(fusion_report)
    else:
        print(final_answer)
        if not args.quiet and not args.no_save:
            print(f"\n[fusion-lite] saved run: {run_dir}", file=sys.stderr)
    cleanup_run_dir(args, run_dir)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a local multi-model Fusion Lite prompt.")
    parser.add_argument("prompt", nargs="*", help="Prompt text. Use '-' to read from stdin.")
    parser.add_argument("--panel", default="openrouter-budget", help="Panel name or path to a panel JSON file.")
    parser.add_argument("--judge", default="auto", choices=["auto", "claude", "codex", "gemini", "kimi", "grok"], help="Judge adapter.")
    parser.add_argument("--judge-model", help="Optional model name or alias for the selected judge adapter, e.g. 'sonnet' for Claude.")
    parser.add_argument("--timeout", type=int, default=180, help="Timeout per panel model in seconds.")
    parser.add_argument("--judge-timeout", type=int, help=f"Timeout for the judge call in seconds. Defaults to the panel setting or {DEFAULT_JUDGE_TIMEOUT}.")
    parser.add_argument("--progress-interval", type=int, default=30, help="Seconds between local CLI progress heartbeats; use 0 to disable.")
    parser.add_argument("--no-judge-fallback", action="store_true", help="Do not fall back to the paired frontier judge.")
    parser.add_argument("--output", choices=["report", "final"], default="report", help="Print a Fusion-style terminal report or only the final answer.")
    parser.add_argument("--no-save", action="store_true", help="Delete run artifacts after printing terminal output.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON instead of only the final answer.")
    parser.add_argument("--quiet", action="store_true", help="Do not print the saved run path to stderr.")
    parser.add_argument("--dry-run", action="store_true", help="Show selected panel commands without running models.")
    parser.add_argument("--show-panel", action="store_true", help="Show selected panel before running.")
    parser.add_argument("--list-panels", action="store_true", help="List available panels and exit.")
    parser.add_argument("--runs-dir", help="Directory for saved run artifacts. Defaults to ./.fusion-lite/runs or FUSION_LITE_RUNS_DIR.")
    parser.add_argument("--doctor", action="store_true", help="Check local CLI adapters and API-key environment without running a prompt.")
    parser.add_argument("--version", action="store_true", help="Print the Fusion Lite version and exit.")
    return parser


def read_prompt(parts: list[str]) -> str:
    if parts == ["-"]:
        return sys.stdin.read()
    if parts:
        return " ".join(parts)
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def load_panel(name_or_path: str) -> dict[str, Any]:
    path = Path(name_or_path)
    if not path.exists():
        path = Path.cwd() / "panels" / f"{name_or_path}.json"
    if not path.exists() and SOURCE_PANELS_DIR.exists():
        path = SOURCE_PANELS_DIR / f"{name_or_path}.json"
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        data.setdefault("name", path.stem)
        validate_panel_config(data, str(path))
        return data

    packaged = read_packaged_panel(name_or_path)
    if packaged is None:
        raise SystemExit(f"Panel not found: {name_or_path}")
    packaged.setdefault("name", name_or_path)
    validate_panel_config(packaged, f"packaged panel {name_or_path}")
    return packaged


def read_packaged_panel(name: str) -> dict[str, Any] | None:
    try:
        panel_file = resources.files("fusion_lite").joinpath(PACKAGE_PANELS_DIR, f"{name}.json")
        if not panel_file.is_file():
            return None
        return json.loads(panel_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, ModuleNotFoundError, json.JSONDecodeError):
        return None


def validate_panel_config(panel: dict[str, Any], source: str = "panel") -> None:
    if not isinstance(panel, dict):
        raise SystemExit(f"Invalid {source}: panel must be a JSON object")
    unknown_panel_fields = sorted(set(panel) - ALLOWED_PANEL_FIELDS)
    if unknown_panel_fields:
        raise SystemExit(f"Invalid {source}: unknown top-level fields: {', '.join(unknown_panel_fields)}")

    for key in ("name", "description"):
        if key in panel and not isinstance(panel[key], str):
            raise SystemExit(f"Invalid {source}: `{key}` must be a string")
    if panel.get("judge") is not None and panel["judge"] not in ALLOWED_JUDGES:
        raise SystemExit(f"Invalid {source}: unsupported judge `{panel['judge']}`")
    if panel.get("fallback_judge") is not None and panel["fallback_judge"] not in ALLOWED_JUDGES:
        raise SystemExit(f"Invalid {source}: unsupported fallback_judge `{panel['fallback_judge']}`")
    if panel.get("judge_model") is not None and not isinstance(panel["judge_model"], str):
        raise SystemExit(f"Invalid {source}: `judge_model` must be a string")
    if panel.get("judge_timeout_seconds") is not None:
        validate_nonnegative_int(panel["judge_timeout_seconds"], source, "judge_timeout_seconds")

    members = panel.get("members")
    if not isinstance(members, list) or not members:
        raise SystemExit(f"Invalid {source}: `members` must be a non-empty list")
    seen_ids: set[str] = set()
    for index, member in enumerate(members):
        validate_panel_member(member, source, index, seen_ids)


def validate_panel_member(member: Any, source: str, index: int, seen_ids: set[str]) -> None:
    label = f"{source} member[{index}]"
    if not isinstance(member, dict):
        raise SystemExit(f"Invalid {label}: member must be an object")
    unknown_fields = sorted(set(member) - ALLOWED_PANEL_MEMBER_FIELDS)
    if unknown_fields:
        raise SystemExit(f"Invalid {label}: unknown fields: {', '.join(unknown_fields)}")

    member_id = member.get("id")
    if not isinstance(member_id, str) or not member_id.strip():
        raise SystemExit(f"Invalid {label}: `id` must be a non-empty string")
    if member_id in seen_ids:
        raise SystemExit(f"Invalid {label}: duplicate id `{member_id}`")
    seen_ids.add(member_id)

    adapter = member.get("adapter")
    if adapter not in ALLOWED_PANEL_ADAPTERS:
        raise SystemExit(f"Invalid {label}: unsupported adapter `{adapter}`")
    for key in ("model", "provider_sort", "agent", "effort"):
        if member.get(key) is not None and not isinstance(member[key], str):
            raise SystemExit(f"Invalid {label}: `{key}` must be a string")
    for key in ("optional", "thinking"):
        if member.get(key) is not None and not isinstance(member[key], bool):
            raise SystemExit(f"Invalid {label}: `{key}` must be a boolean")
    for key in ("timeout_seconds", "max_tokens", "max_steps_per_turn", "max_ralph_iterations", "max_retries_per_step", "max_turns"):
        if member.get(key) is not None:
            validate_nonnegative_int(member[key], label, key)
    if member.get("temperature") is not None and (isinstance(member["temperature"], bool) or not isinstance(member["temperature"], (int, float))):
        raise SystemExit(f"Invalid {label}: `temperature` must be a number")
    if member.get("reasoning") is not None and not isinstance(member["reasoning"], dict):
        raise SystemExit(f"Invalid {label}: `reasoning` must be an object")


def validate_nonnegative_int(value: Any, source: str, key: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SystemExit(f"Invalid {source}: `{key}` must be a non-negative integer")


def load_judge_spec(judge_id: str, judge_model: str | None = None) -> dict[str, Any]:
    specs = {
        "claude": {"id": "judge_claude", "adapter": "claude_cli", "role": "judge"},
        "codex": {"id": "judge_codex", "adapter": "codex_cli", "role": "judge"},
        "gemini": {"id": "judge_gemini", "adapter": "gemini_cli", "model": "gemini-2.5-flash", "role": "judge"},
        "kimi": {"id": "judge_kimi", "adapter": "kimi_cli", "role": "judge"},
        "grok": {"id": "judge_grok", "adapter": "grok_cli", "role": "judge"},
    }
    spec = dict(specs[judge_id])
    if judge_model:
        spec["model"] = judge_model
    return spec


def choose_judge(arg: str, panel_config: dict[str, Any]) -> str:
    if arg != "auto":
        return arg
    return str(panel_config.get("judge") or "claude")


def choose_judges(arg: str, panel_config: dict[str, Any], no_fallback: bool) -> list[str]:
    primary = choose_judge(arg, panel_config)
    if no_fallback:
        return [primary]
    fallback = str(panel_config.get("fallback_judge") or paired_frontier_judge(primary))
    if fallback and fallback != primary:
        return [primary, fallback]
    return [primary]


def choose_judge_model(arg: str | None, panel_config: dict[str, Any]) -> str | None:
    return arg or panel_config.get("judge_model")


def choose_judge_timeout(args: argparse.Namespace, panel_config: dict[str, Any]) -> int:
    if args.judge_timeout is not None:
        return int(args.judge_timeout)
    if panel_config.get("judge_timeout_seconds"):
        return int(panel_config["judge_timeout_seconds"])
    return DEFAULT_JUDGE_TIMEOUT


def paired_frontier_judge(primary: str) -> str:
    if primary == "claude":
        return "codex"
    if primary == "codex":
        return "claude"
    return "codex"


def run_judges(
    judge_candidates: list[str],
    judge_prompt: str,
    run_dir: Path,
    timeout: int,
    judge_model: str | None = None,
    progress_interval: int = 0,
) -> tuple[dict[str, Any] | None, str | None, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    last_ok_text = ""
    for index, judge_id in enumerate(judge_candidates):
        candidate_model = judge_model if index == 0 else None
        judge_spec = load_judge_spec(judge_id, candidate_model)
        if progress_interval:
            judge_spec["progress_interval_seconds"] = progress_interval
        judge_dir = run_dir / "judge" / safe_name(judge_id)
        judge_dir.mkdir(parents=True, exist_ok=True)
        write_text(judge_dir / "prompt.txt", judge_prompt)
        judge_result = run_adapter(judge_spec, judge_prompt, judge_dir, timeout)
        write_json(judge_dir / "result.json", asdict(judge_result))
        write_text(judge_dir / "raw.txt", judge_result.content or "")
        parsed = parse_judge_json(judge_result.content) if judge_result.status == "ok" else None
        attempts.append(
            {
                "judge": judge_id,
                "status": judge_result.status,
                "parsed_json": parsed is not None,
                "model": judge_result.model,
                "error": judge_result.error,
                "elapsed_seconds": round(judge_result.elapsed_seconds, 3),
                "usage": summarize_single_usage(judge_result.usage),
            }
        )
        if judge_result.status == "ok" and parsed is not None:
            parsed["judge_used"] = judge_id
            parsed["judge_attempts"] = attempts
            return parsed, judge_id, attempts
        if judge_result.status == "ok" and judge_result.content.strip():
            last_ok_text = judge_result.content.strip()

    if last_ok_text:
        return (
            {
                "task_class": "other",
                "confidence": "medium",
                "answer_sufficiency": "partial",
                "disagreement_score": None,
                "escalation_recommendation": {
                    "should_escalate": True,
                    "reason": "The judge produced text, but not valid structured JSON for calibration.",
                    "cheapest_next_step": "rerun with more context",
                },
                "cost_quality_notes": ["Judge parse failure prevents reliable disagreement and sufficiency scoring."],
                "missing_checks": ["Judge did not return valid JSON; raw judge text saved under judge/<judge>/raw.txt."],
                "final_answer": last_ok_text,
                "parse_error": "invalid judge JSON",
                "judge_attempts": attempts,
            },
            None,
            attempts,
        )
    return None, None, attempts


def normalize_judge_json(judge_json: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(judge_json)
    warnings: list[str] = []

    for key in JUDGE_LIST_FIELDS:
        if key not in normalized:
            normalized[key] = []
            warnings.append(f"missing `{key}`; defaulted to []")
        elif not isinstance(normalized[key], list):
            normalized[key] = []
            warnings.append(f"`{key}` was not a list; defaulted to []")

    for key in JUDGE_DICT_FIELDS:
        if key not in normalized:
            normalized[key] = {}
            warnings.append(f"missing `{key}`; defaulted to {{}}")
        elif not isinstance(normalized[key], dict):
            normalized[key] = {}
            warnings.append(f"`{key}` was not an object; defaulted to {{}}")

    for key, default in JUDGE_SCALAR_DEFAULTS.items():
        if key not in normalized:
            normalized[key] = default
            warnings.append(f"missing `{key}`; defaulted to {default!r}")

    normalize_blind_spot_sources(normalized, warnings)
    existing_warnings = normalized.get("schema_warnings")
    if isinstance(existing_warnings, list):
        warnings = [str(item) for item in existing_warnings if item not in (None, "")] + warnings
    elif existing_warnings not in (None, "", [], {}):
        warnings.insert(0, "`schema_warnings` was not a list; preserved as warning text")
        warnings.insert(1, str(existing_warnings))
    normalized["schema_warnings"] = warnings
    return normalized


def normalize_blind_spot_sources(judge_json: dict[str, Any], warnings: list[str]) -> None:
    for key, default_source in (
        ("blind_spots", "panel"),
        ("judge_inferred_blind_spots", "judge_inferred"),
    ):
        items = judge_json.get(key)
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            source = item.get("source")
            if source in {"panel", "judge_inferred"}:
                continue
            item["source"] = default_source
            warnings.append(f"`{key}`[{index}] missing valid source; set to `{default_source}`")


def run_panel(members: list[dict[str, Any]], prompt: str, run_dir: Path, timeout: int, progress_interval: int = 0) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(members))) as executor:
        future_map = {}
        for member in members:
            member_spec = dict(member)
            if progress_interval:
                member_spec["progress_interval_seconds"] = progress_interval
            member_dir = run_dir / "panel" / safe_name(str(member_spec.get("id") or member_spec["adapter"]))
            member_dir.mkdir(parents=True, exist_ok=True)
            write_text(member_dir / "prompt.txt", prompt)
            member_timeout = int(member_spec.get("timeout_seconds") or timeout)
            future = executor.submit(run_adapter, member_spec, prompt, member_dir, member_timeout)
            future_map[future] = member_dir
        for future in concurrent.futures.as_completed(future_map):
            member_dir = future_map[future]
            try:
                result: AdapterResult = future.result()
            except Exception as exc:  # noqa: BLE001 - one adapter must not kill the run
                result = AdapterResult(
                    id=member_dir.name,
                    adapter="unknown",
                    model=None,
                    status="error",
                    content="",
                    elapsed_seconds=0.0,
                    error=str(exc),
                )
            result_dict = asdict(result)
            write_json(member_dir / "result.json", result_dict)
            if result.content:
                write_text(member_dir / "response.md", result.content + "\n")
            results.append(result_dict)
    return sorted(results, key=lambda item: item["id"])


def summarize_panel_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    statuses: dict[str, int] = {}
    elapsed_by_model: dict[str, float] = {}
    content_chars: dict[str, int] = {}
    for result in results:
        status = str(result.get("status") or "unknown")
        statuses[status] = statuses.get(status, 0) + 1
        model_id = str(result.get("id") or "unknown")
        elapsed = numeric_value(result.get("elapsed_seconds")) or 0.0
        elapsed_by_model[model_id] = round(elapsed, 3)
        content_chars[model_id] = len(str(result.get("content") or ""))

    elapsed_values = list(elapsed_by_model.values())
    slowest_model = max(elapsed_by_model, key=elapsed_by_model.get) if elapsed_by_model else None
    return {
        "total": len(results),
        "ok": statuses.get("ok", 0),
        "skipped": statuses.get("skipped", 0),
        "error": statuses.get("error", 0),
        "statuses": statuses,
        "wall_seconds_estimate": round(max(elapsed_values), 3) if elapsed_values else 0.0,
        "compute_seconds": round(sum(elapsed_values), 3),
        "slowest_model": slowest_model,
        "elapsed_seconds_by_model": elapsed_by_model,
        "content_chars_by_model": content_chars,
    }


def summarize_usage(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_model: dict[str, dict[str, Any]] = {}
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    known_cost = 0.0
    cost_models = 0
    usage_models = 0

    for result in results:
        usage = result.get("usage")
        if not isinstance(usage, dict) or not usage:
            continue
        model_id = str(result.get("id") or result.get("model") or "unknown")
        item = summarize_single_usage(usage)
        if not item:
            continue
        by_model[model_id] = item
        usage_models += 1
        prompt_tokens += int(item.get("prompt_tokens") or 0)
        completion_tokens += int(item.get("completion_tokens") or 0)
        total_tokens += int(item.get("total_tokens") or 0)
        if item.get("cost_usd") is not None:
            known_cost += float(item["cost_usd"])
            cost_models += 1

    return {
        "models_with_usage": usage_models,
        "models_with_known_cost": cost_models,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "known_cost_usd": round(known_cost, 8) if cost_models else None,
        "by_model": by_model,
    }


def summarize_single_usage(usage: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(usage, dict) or not usage:
        return {}
    prompt_tokens = int(numeric_value(usage.get("prompt_tokens")) or 0)
    completion_tokens = int(numeric_value(usage.get("completion_tokens")) or 0)
    total_tokens = int(numeric_value(usage.get("total_tokens")) or prompt_tokens + completion_tokens)
    cost = usage_cost_usd(usage)
    summary: dict[str, Any] = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }
    if cost is not None:
        summary["cost_usd"] = round(cost, 8)
    return summary


def usage_cost_usd(usage: dict[str, Any]) -> float | None:
    for key in ("cost", "total_cost", "cost_usd"):
        value = numeric_value(usage.get(key))
        if value is not None:
            return value
    cost_details = usage.get("cost_details")
    if isinstance(cost_details, dict):
        for key in ("upstream_inference_cost", "total_cost", "cost"):
            value = numeric_value(cost_details.get(key))
            if value is not None:
                return value
    return None


def numeric_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def parse_judge_json(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    candidates = [fenced.group(1)] if fenced else []
    candidates.append(stripped)
    for candidate in candidates:
        for index, char in enumerate(candidate):
            if char != "{":
                continue
            try:
                parsed = json.loads(candidate[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return None


def fallback_final_answer(ok_results: list[dict[str, Any]]) -> str:
    lines = ["Fusion Lite fallback answer: the judge failed, so here are the usable panel outputs."]
    for result in ok_results:
        lines.append(f"\n## {result['id']}\n{result.get('content', '').strip()}")
    return "\n".join(lines).strip()


def render_fusion_report(
    user_prompt: str,
    panel_results: list[dict[str, Any]],
    judge_json: dict[str, Any],
    metadata: dict[str, Any],
) -> str:
    lines = ["# Fusion Lite Report", ""]
    lines.extend(render_report_prompt(user_prompt, metadata))
    lines.extend(render_report_sources(panel_results, metadata))
    lines.extend(render_report_analysis(judge_json))
    lines.extend(render_report_result(judge_json, metadata))
    return "\n".join(lines).rstrip()


def render_report_prompt(user_prompt: str, metadata: dict[str, Any]) -> list[str]:
    prompt = user_prompt.strip()
    lines = ["## Prompt", ""]
    lines.append(f"- Panel: `{metadata.get('panel')}`")
    if metadata.get("judge_used"):
        lines.append(f"- Judge: `{metadata.get('judge_used')}`")
    if metadata.get("judge_model_requested"):
        lines.append(f"- Requested judge model: `{metadata.get('judge_model_requested')}`")
    lines.append(f"- Full prompt: `prompt.txt`")
    lines.extend(["", truncate_text(prompt, 1200), ""])
    return lines


def render_report_sources(panel_results: list[dict[str, Any]], metadata: dict[str, Any]) -> list[str]:
    lines = ["## STEP 1/3 SOURCES", ""]
    if not panel_results:
        return lines + ["No panel sources were recorded.", ""]

    lines.append("| Source | Model | Status | Time | Size | Cost |")
    lines.append("| --- | --- | --- | ---: | ---: | ---: |")
    for result in sorted(panel_results, key=lambda item: str(item.get("id") or "")):
        source = str(result.get("id") or result.get("adapter") or "unknown")
        model = str(result.get("model") or result.get("adapter") or source)
        status = render_status(str(result.get("status") or "unknown"))
        elapsed = numeric_value(result.get("elapsed_seconds")) or 0.0
        size = len(str(result.get("content") or ""))
        usage = summarize_single_usage(result.get("usage") or {})
        cost = usage.get("cost_usd")
        cost_text = f"${cost:.6f}" if isinstance(cost, (int, float)) else "-"
        lines.append(f"| `{source}` | `{model}` | {status} | {elapsed:.1f}s | {size:,} chars | {cost_text} |")

    error_lines = []
    for result in sorted(panel_results, key=lambda item: str(item.get("id") or "")):
        status = str(result.get("status") or "")
        error = str(result.get("error") or "").strip()
        if status in {"error", "skipped"} and error:
            source = str(result.get("id") or result.get("adapter") or "unknown")
            error_lines.append(f"- `{source}`: {truncate_text(error, 600)}")
    if error_lines:
        lines.extend(["", "**Source Errors**"])
        lines.extend(error_lines)

    panel_summary = metadata.get("panel_summary") if isinstance(metadata.get("panel_summary"), dict) else {}
    usage_summary = metadata.get("usage_summary") if isinstance(metadata.get("usage_summary"), dict) else {}
    lines.extend(
        [
            "",
            f"- Complete sources: {panel_summary.get('ok', 0)}/{panel_summary.get('total', len(panel_results))}",
            f"- Wall-time estimate: {panel_summary.get('wall_seconds_estimate', 0)}s",
            f"- Known remote cost: {format_cost(usage_summary.get('known_cost_usd'))}",
            "",
        ]
    )
    return lines


def render_report_analysis(judge_json: dict[str, Any]) -> list[str]:
    lines = ["## STEP 2/3 ANALYSIS", ""]
    cards = [
        ("Agreement", "agreement"),
        ("Key Differences", "key_differences"),
        ("Partial Coverage", "partial_coverage"),
        ("Unique Insights", "unique_insights"),
        ("Blind Spots", "blind_spots"),
        ("Mechanism Check", "mechanism_check"),
        ("Consensus Risks", "consensus_risks"),
        ("Minority Report", "minority_report"),
        ("Judge-Inferred Blind Spots", "judge_inferred_blind_spots"),
        ("Unsupported Or Risky Claims", "unsupported_or_risky_claims"),
        ("Model Quality", "model_quality"),
        ("Top Improvements", "top_improvements"),
        ("Top Strengths", "top_strengths"),
        ("Consensus Vs Disputes", "consensus_vs_disputes"),
        ("Synthesis Strategy", "synthesis_strategy"),
        ("Action Delta", "action_delta"),
        ("Escalation Recommendation", "escalation_recommendation"),
        ("Cost Quality Notes", "cost_quality_notes"),
        ("Schema Warnings", "schema_warnings"),
    ]
    for title, key in cards:
        rendered = render_analysis_value(judge_json.get(key))
        if rendered:
            append_report_card(lines, title, rendered, count_items(judge_json.get(key)))

    attempts = judge_json.get("judge_attempts")
    rendered_attempts = render_judge_attempts(attempts)
    if rendered_attempts:
        append_report_card(lines, "Judge Attempts", rendered_attempts, count_items(attempts))

    scalar_lines = []
    for label, key in (
        ("Task class", "task_class"),
        ("Answer sufficiency", "answer_sufficiency"),
        ("Disagreement score", "disagreement_score"),
        ("Confidence", "confidence"),
    ):
        value = judge_json.get(key)
        if value not in (None, "", [], {}):
            scalar_lines.append(f"- {label}: `{value}`")
    if scalar_lines:
        append_report_card(lines, "Run Verdict", scalar_lines, len(scalar_lines))
    return lines


def render_judge_attempts(attempts: Any) -> list[str]:
    if not isinstance(attempts, list):
        return []
    lines = []
    for attempt in attempts:
        if not isinstance(attempt, dict):
            continue
        judge = str(attempt.get("judge") or "unknown")
        status = str(attempt.get("status") or "unknown")
        parsed = attempt.get("parsed_json")
        elapsed = attempt.get("elapsed_seconds")
        model = attempt.get("model")
        error = str(attempt.get("error") or "").strip()
        item = f"- `{judge}` status={status}"
        if model:
            item += f" model=`{model}`"
        if elapsed not in (None, ""):
            item += f" elapsed={elapsed}s"
        if parsed is not None:
            item += f" parsed_json={parsed}"
        if error:
            item += f"\n  error: {truncate_text(error, 500)}"
        lines.append(item)
    return lines


def render_report_result(judge_json: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
    final_answer = str(judge_json.get("final_answer") or "").strip()
    judge_label = render_judge_label(judge_json, metadata)
    lines = ["## STEP 3/3 RESULT", ""]
    if judge_label:
        lines.extend([f"### {judge_label}", ""])
    lines.extend([final_answer or "No final answer was returned.", ""])
    action_delta = render_points(judge_json.get("action_delta"))
    if action_delta:
        lines.extend(["", "### Action Delta", ""])
        lines.extend(action_delta)
        lines.append("")
    return lines


def render_analysis_value(value: Any) -> list[str]:
    if isinstance(value, dict):
        return render_mapping(value)
    return render_points(value)


def append_report_card(lines: list[str], title: str, rendered: list[str], count: int) -> None:
    suffix = f" ({count})" if count else ""
    preview = first_preview(rendered)
    summary = f"{title}{suffix}"
    if preview:
        summary = f"{summary}: {preview}"
    lines.extend(["<details>", f"<summary>{summary}</summary>", ""])
    lines.extend(rendered)
    lines.extend(["", "</details>", ""])


def first_preview(rendered: list[str]) -> str:
    for line in rendered:
        stripped = line.strip()
        if not stripped:
            continue
        stripped = stripped.removeprefix("- ").strip()
        return truncate_text(stripped, 220).replace("\n", " ")
    return ""


def count_items(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        return len([item for item in value.values() if item not in (None, "", [], {})])
    return 1 if value not in (None, "", [], {}) else 0


def truncate_text(text: str, limit: int) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[: max(0, limit - 15)].rstrip() + "\n\n[truncated]"


def render_status(status: str) -> str:
    if status == "ok":
        return "Complete"
    if status == "skipped":
        return "Skipped"
    if status == "error":
        return "Error"
    return status


def format_cost(value: Any) -> str:
    number = numeric_value(value)
    if number is None:
        return "-"
    return f"${number:.6f}"


def render_judge_label(judge_json: dict[str, Any], metadata: dict[str, Any]) -> str:
    judge_used = str(judge_json.get("judge_used") or metadata.get("judge_used") or "").strip()
    attempts = metadata.get("judge_attempts") or judge_json.get("judge_attempts") or []
    model = None
    if isinstance(attempts, list):
        for attempt in attempts:
            if not isinstance(attempt, dict):
                continue
            if attempt.get("judge") == judge_used and attempt.get("status") == "ok":
                model = attempt.get("model")
                break
    if judge_used and model:
        return f"{judge_used} ({model}) - Fused"
    if judge_used:
        return f"{judge_used} - Fused"
    return "Fusion Lite - Fused"


def render_analysis_markdown(judge_json: dict[str, Any]) -> str:
    lines = ["# Fusion Lite Analysis", ""]
    task_class = judge_json.get("task_class")
    if task_class:
        lines.extend(["## Task Class", "", str(task_class), ""])
    append_section(lines, "Agreement", render_points(judge_json.get("agreement")))
    append_section(lines, "Key Differences", render_points(judge_json.get("key_differences")))
    append_section(lines, "Partial Coverage", render_points(judge_json.get("partial_coverage")))
    append_section(lines, "Unique Insights", render_points(judge_json.get("unique_insights")))
    append_section(lines, "Blind Spots", render_points(judge_json.get("blind_spots")))
    append_section(lines, "Mechanism Check", render_points(judge_json.get("mechanism_check")))
    append_section(lines, "Consensus Risks", render_points(judge_json.get("consensus_risks")))
    append_section(lines, "Minority Report", render_points(judge_json.get("minority_report")))
    append_section(lines, "Judge-Inferred Blind Spots", render_points(judge_json.get("judge_inferred_blind_spots")))
    append_section(lines, "Unsupported Or Risky Claims", render_points(judge_json.get("unsupported_or_risky_claims")))
    append_section(lines, "Conversion Verdict", render_mapping(judge_json.get("conversion_verdict")))
    append_section(lines, "Strongest Objection", render_mapping(judge_json.get("strongest_objection")))
    append_section(lines, "Top Strengths", render_points(judge_json.get("top_strengths")))
    append_section(lines, "Top Improvements", render_points(judge_json.get("top_improvements")))
    append_section(lines, "Consensus Vs Disputes", render_mapping(judge_json.get("consensus_vs_disputes")))
    append_section(lines, "Model Quality", render_points(judge_json.get("model_quality")))
    append_section(lines, "Synthesis Strategy", render_mapping(judge_json.get("synthesis_strategy")))
    append_section(lines, "Action Delta", render_points(judge_json.get("action_delta")))
    answer_sufficiency = judge_json.get("answer_sufficiency")
    if answer_sufficiency:
        lines.extend(["## Answer Sufficiency", "", str(answer_sufficiency), ""])
    disagreement_score = judge_json.get("disagreement_score")
    if disagreement_score is not None:
        lines.extend(["## Disagreement Score", "", str(disagreement_score), ""])
    append_section(lines, "Escalation Recommendation", render_mapping(judge_json.get("escalation_recommendation")))
    append_section(lines, "Cost Quality Notes", render_points(judge_json.get("cost_quality_notes")))
    append_section(lines, "Schema Warnings", render_points(judge_json.get("schema_warnings")))
    confidence = judge_json.get("confidence")
    if confidence:
        lines.extend(["## Confidence", "", str(confidence), ""])
    final_answer = str(judge_json.get("final_answer") or "").strip()
    if final_answer:
        lines.extend(["## Final Answer", "", final_answer, ""])
    return "\n".join(lines).rstrip()


def append_section(lines: list[str], title: str, rendered: list[str]) -> None:
    if not rendered:
        return
    lines.extend([f"## {title}", ""])
    lines.extend(rendered)
    lines.append("")


def render_points(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        lines: list[str] = []
        for item in value:
            if isinstance(item, dict):
                primary = (
                    item.get("point")
                    or item.get("topic")
                    or item.get("insight")
                    or item.get("blind_spot")
                    or item.get("claim")
                    or item.get("consensus")
                    or item.get("minority_view")
                    or item.get("issue")
                    or item.get("action")
                    or item.get("model")
                    or json.dumps(item, ensure_ascii=False)
                )
                lines.append(f"- {primary}")
                details = []
                for key, detail in item.items():
                    if detail in (None, "", [], {}) or key in {
                        "point",
                        "topic",
                        "insight",
                        "blind_spot",
                        "claim",
                        "consensus",
                        "minority_view",
                        "issue",
                        "action",
                        "model",
                    }:
                        continue
                    details.append(f"{key}: {format_detail(detail)}")
                if details:
                    lines.append(f"  {'; '.join(details)}")
            else:
                lines.append(f"- {item}")
        return lines
    if isinstance(value, dict):
        return render_mapping(value)
    return [str(value)]


def render_mapping(value: Any) -> list[str]:
    if not isinstance(value, dict) or not value:
        return []
    return [f"- {key}: {format_detail(detail)}" for key, detail in value.items() if detail not in (None, "", [], {})]


def format_detail(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(format_detail(item) for item in value)
    if isinstance(value, dict):
        return "; ".join(f"{key}: {format_detail(detail)}" for key, detail in value.items() if detail not in (None, "", [], {}))
    return str(value)


def emit_live_step(args: argparse.Namespace, step: str, message: str) -> None:
    if getattr(args, "quiet", False):
        return
    print(f"[fusion-lite] {step}: {message}", file=sys.stderr, flush=True)


def cleanup_run_dir(args: argparse.Namespace, run_dir: Path) -> None:
    if not getattr(args, "no_save", False):
        return
    shutil.rmtree(run_dir, ignore_errors=True)
    if not getattr(args, "quiet", False):
        print(f"[fusion-lite] discarded run artifacts: {run_dir}", file=sys.stderr, flush=True)


def print_panel(panel_config: dict[str, Any], args: argparse.Namespace) -> None:
    judges = choose_judges(args.judge, panel_config, no_fallback=args.no_judge_fallback)
    judge_model = choose_judge_model(args.judge_model, panel_config)
    print(f"Panel: {panel_config['name']}")
    judge_labels = list(judges)
    if judge_model and judge_labels:
        judge_labels[0] = f"{judge_labels[0]} ({judge_model})"
    judge_label = " -> ".join(judge_labels)
    print(f"Judge: {judge_label}")
    for member in panel_config.get("members", []):
        timeout = int(member.get("timeout_seconds") or args.timeout)
        rendered = render_command(member, timeout)
        optional = " optional" if member.get("optional") else ""
        print(f"- {member.get('id') or member['adapter']} ({member['adapter']}{optional}): {shell_join(rendered)}")


def list_panels() -> None:
    panels: dict[str, str] = {}
    for path in panel_search_paths():
        if not path.exists():
            continue
        for panel_path in sorted(path.glob("*.json")):
            try:
                data = json.loads(panel_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            panels[panel_path.stem] = str(data.get("description", ""))
    try:
        panel_dir = resources.files("fusion_lite").joinpath(PACKAGE_PANELS_DIR)
        for panel_file in sorted(item for item in panel_dir.iterdir() if item.name.endswith(".json")):
            data = json.loads(panel_file.read_text(encoding="utf-8"))
            panels.setdefault(panel_file.name.removesuffix(".json"), str(data.get("description", "")))
    except (FileNotFoundError, ModuleNotFoundError, json.JSONDecodeError):
        pass
    for name in sorted(panels):
        print(f"{name}\t{panels[name]}")


def panel_search_paths() -> list[Path]:
    paths = [Path.cwd() / "panels"]
    if SOURCE_PANELS_DIR.exists():
        paths.append(SOURCE_PANELS_DIR)
    return paths


def resolve_runs_dir(value: str | None) -> Path:
    configured = value or os.getenv("FUSION_LITE_RUNS_DIR")
    return Path(configured).expanduser() if configured else Path.cwd() / DEFAULT_RUNS_DIR


def make_run_dir(panel_name: str, runs_root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = runs_root / f"{stamp}_{safe_name(panel_name)}"
    counter = 2
    while path.exists():
        path = runs_root / f"{stamp}_{safe_name(panel_name)}_{counter}"
        counter += 1
    path.mkdir(parents=True)
    return path


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value.strip())
    return cleaned.strip("_") or "run"


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_dotenv_candidates() -> None:
    seen: set[Path] = set()
    for path in (Path.cwd() / ".env", SOURCE_ROOT / ".env"):
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        load_dotenv(path)


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key in DOTENV_ALLOWED_KEYS and key not in os.environ:
            os.environ[key] = value


def print_doctor() -> None:
    print(f"fusion-lite {__version__}")
    print(f"runs_dir\t{resolve_runs_dir(None)}")
    print(f"openrouter_key\t{'set' if os.getenv('OPENROUTER_API_KEY') else 'missing'}")
    print(f"deepseek_key\t{'set' if os.getenv('DEEPSEEK_API_KEY') else 'missing'}")
    for binary in ("codex", "claude", "gemini", "kimi", "grok"):
        found = shutil.which(binary)
        print(f"{binary}\t{found or 'missing'}")
