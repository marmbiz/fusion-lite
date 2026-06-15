from __future__ import annotations

import filecmp
import json
import os
import py_compile
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fusion_lite.adapters import _redact_command
from fusion_lite.cli import load_dotenv, normalize_judge_json, render_fusion_report, summarize_panel_results, summarize_usage, validate_panel_config


def main() -> int:
    checks = [
        compile_python,
        validate_json_panels,
        validate_panel_copies_match,
        validate_panel_schema_rejects_api_url,
        validate_release_version,
        validate_no_tracked_secrets,
        validate_command_redaction,
        validate_ci_actions_pinned,
        validate_dotenv_allowlist,
        validate_metric_summaries,
        validate_judge_normalization,
        validate_fusion_report,
        run_list_panels,
        run_default_dry_run,
        run_doctor,
    ]
    for check in checks:
        print(f"== {check.__name__}")
        check()
    print("OK")
    return 0


def compile_python() -> None:
    for path in sorted((ROOT / "fusion_lite").glob("*.py")):
        py_compile.compile(str(path), doraise=True)


def validate_json_panels() -> None:
    panel_paths = list((ROOT / "panels").glob("*.json")) + list((ROOT / "fusion_lite" / "panels").glob("*.json"))
    if not panel_paths:
        raise AssertionError("no panel JSON files found")
    for path in sorted(panel_paths):
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not data.get("name"):
            raise AssertionError(f"{path} missing name")
        if not isinstance(data.get("members"), list) or not data["members"]:
            raise AssertionError(f"{path} missing members")
        validate_panel_config(data, str(path.relative_to(ROOT)))


def validate_panel_copies_match() -> None:
    source_panels = ROOT / "panels"
    package_panels = ROOT / "fusion_lite" / "panels"
    for source_path in sorted(source_panels.glob("*.json")):
        package_path = package_panels / source_path.name
        if not package_path.exists():
            raise AssertionError(f"packaged panel missing: {package_path.relative_to(ROOT)}")
        if not filecmp.cmp(source_path, package_path, shallow=False):
            raise AssertionError(f"panel drift: {source_path.relative_to(ROOT)} != {package_path.relative_to(ROOT)}")
    for package_path in sorted(package_panels.glob("*.json")):
        source_path = source_panels / package_path.name
        if not source_path.exists():
            raise AssertionError(f"source panel missing: {source_path.relative_to(ROOT)}")


def validate_panel_schema_rejects_api_url() -> None:
    bad_panel = {
        "name": "bad",
        "members": [
            {
                "id": "exfil",
                "adapter": "openrouter_chat",
                "model": "example/model",
                "api_url": "https://attacker.example/api",
            }
        ],
    }
    try:
        validate_panel_config(bad_panel, "bad panel")
    except SystemExit as exc:
        if "api_url" not in str(exc):
            raise AssertionError(f"panel schema rejected wrong reason: {exc}") from exc
        return
    raise AssertionError("panel schema accepted api_url override")


def validate_release_version() -> None:
    result = run_script("scripts/release_version.py", "--check", "--tag")
    version = run_script("scripts/release_version.py").stdout.strip()
    if result.stdout.strip() != f"v{version}":
        raise AssertionError(f"release tag output is wrong: {result.stdout!r}")


def validate_no_tracked_secrets() -> None:
    tracked = run_git("ls-files").stdout.splitlines()
    key_like = re.compile(r"(?i)\b(sk-[A-Za-z0-9_-]{12,}|or-[A-Za-z0-9_-]{12,})\b")
    assignment = re.compile(r"(?i)(api[_-]?key|token|secret)[ \t]*[:=][ \t]*['\"]?(?!\.\.\.|<|$)([A-Za-z0-9_./+=-]{20,})")
    for relative in tracked:
        path = ROOT / relative
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if key_like.search(text) or assignment.search(text):
            raise AssertionError(f"possible tracked secret in {relative}")


def validate_command_redaction() -> None:
    prompt = "SECRET_PROMPT_MARKER"
    redacted = _redact_command(["codex", "exec", "--output-last-message", "out.txt", prompt])
    if prompt in redacted:
        raise AssertionError("codex prompt was not redacted")


def validate_ci_actions_pinned() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    mutable_actions = re.findall(r"uses:\s*actions/[^@\s]+@v\d+(?:\s|$)", workflow)
    if mutable_actions:
        raise AssertionError(f"workflow uses mutable action tags: {', '.join(mutable_actions)}")
    if "actions/checkout@" in workflow and "persist-credentials: false" not in workflow:
        raise AssertionError("actions/checkout must set persist-credentials: false")


def validate_dotenv_allowlist() -> None:
    watched = ("OPENROUTER_API_KEY", "PATH", "PYTHONPATH", "KIMI_CONFIG_FILE")
    original = {key: os.environ.get(key) for key in watched}
    try:
        for key in watched:
            os.environ.pop(key, None)
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "OPENROUTER_API_KEY=ok",
                        "PATH=/tmp/malicious",
                        "PYTHONPATH=/tmp/malicious",
                        "KIMI_CONFIG_FILE=/tmp/malicious",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            load_dotenv(env_path)
        if os.environ.get("OPENROUTER_API_KEY") != "ok":
            raise AssertionError(".env allowlist did not load OPENROUTER_API_KEY")
        for blocked in ("PATH", "PYTHONPATH", "KIMI_CONFIG_FILE"):
            if os.environ.get(blocked) == "/tmp/malicious":
                raise AssertionError(f".env loaded blocked key: {blocked}")
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def validate_metric_summaries() -> None:
    fake_results = [
        {
            "id": "a",
            "status": "ok",
            "content": "alpha",
            "elapsed_seconds": 1.25,
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": 0.0003},
        },
        {
            "id": "b",
            "status": "error",
            "content": "",
            "elapsed_seconds": 2.5,
            "usage": {},
        },
    ]
    panel_summary = summarize_panel_results(fake_results)
    if panel_summary["ok"] != 1 or panel_summary["error"] != 1:
        raise AssertionError("panel status summary is wrong")
    if panel_summary["wall_seconds_estimate"] != 2.5:
        raise AssertionError("panel wall-time estimate is wrong")
    usage_summary = summarize_usage(fake_results)
    if usage_summary["total_tokens"] != 15:
        raise AssertionError("usage token summary is wrong")
    if usage_summary["known_cost_usd"] != 0.0003:
        raise AssertionError("usage cost summary is wrong")


def validate_judge_normalization() -> None:
    normalized = normalize_judge_json(
        {
            "final_answer": "ok",
            "blind_spots": [{"blind_spot": "panel spot"}],
            "judge_inferred_blind_spots": [{"blind_spot": "judge spot"}],
        }
    )
    if not isinstance(normalized.get("agreement"), list):
        raise AssertionError("normalizer did not default missing list fields")
    if not isinstance(normalized.get("synthesis_strategy"), dict):
        raise AssertionError("normalizer did not default missing object fields")
    if normalized["blind_spots"][0].get("source") != "panel":
        raise AssertionError("normalizer did not mark panel blind spot provenance")
    if normalized["judge_inferred_blind_spots"][0].get("source") != "judge_inferred":
        raise AssertionError("normalizer did not mark judge-inferred blind spot provenance")
    if not normalized.get("schema_warnings"):
        raise AssertionError("normalizer did not report schema warnings")


def validate_fusion_report() -> None:
    panel_results = [
        {
            "id": "source_a",
            "adapter": "openrouter_chat",
            "model": "example/a",
            "status": "ok",
            "content": "alpha answer",
            "elapsed_seconds": 1.2,
            "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14, "cost": 0.001},
        }
    ]
    judge_json = {
        "task_class": "analysis",
        "agreement": [{"point": "same verdict", "models": ["source_a"], "why_it_matters": "coverage"}],
        "mechanism_check": [
            {"claim": "mechanism claim", "models": ["source_a"], "verdict": "sound", "reason": "grounded"}
        ],
        "consensus_risks": [{"consensus": "consensus can be wrong", "risk": "false agreement", "judge_verdict": "check it"}],
        "minority_report": [{"model": "source_a", "minority_view": "useful dissent", "promote": True, "why": "better mechanism"}],
        "judge_inferred_blind_spots": [
            {"blind_spot": "missing external validity", "risk": "overfit", "suggested_check": "sample test"}
        ],
        "synthesis_strategy": {
            "dominant_answer": "dominant",
            "promoted_minority_views": ["useful dissent"],
            "demoted_claims": ["weak claim"],
            "early_caveat": "important caveat",
        },
        "action_delta": [{"priority": 1, "action": "next action", "why": "highest leverage"}],
        "schema_warnings": ["test warning"],
        "answer_sufficiency": "sufficient",
        "confidence": "high",
        "final_answer": "final answer",
        "judge_used": "claude",
    }
    metadata = {
        "panel": "test",
        "judge_used": "claude",
        "judge_model_requested": "opus",
        "panel_summary": summarize_panel_results(panel_results),
        "usage_summary": summarize_usage(panel_results),
        "judge_attempts": [{"judge": "claude", "status": "ok", "model": "opus"}],
    }
    report = render_fusion_report("prompt", panel_results, judge_json, metadata)
    for marker in (
        "STEP 1/3 SOURCES",
        "STEP 2/3 ANALYSIS",
        "Mechanism Check",
        "Consensus Risks",
        "Minority Report",
        "Judge-Inferred Blind Spots",
        "Synthesis Strategy",
        "Action Delta",
        "Schema Warnings",
        "STEP 3/3 RESULT",
        "final answer",
    ):
        if marker not in report:
            raise AssertionError(f"fusion report missing {marker}")


def run_list_panels() -> None:
    result = run_python_module("--list-panels")
    if "openrouter-budget" not in result.stdout:
        raise AssertionError("openrouter-budget missing from --list-panels")
    if "fable" not in result.stdout:
        raise AssertionError("fable missing from --list-panels")


def run_default_dry_run() -> None:
    result = run_python_module("--dry-run", "release check")
    if "Panel: openrouter-budget" not in result.stdout:
        raise AssertionError("default panel is not openrouter-budget")
    if "z-ai/glm-5.1" not in result.stdout:
        raise AssertionError("GLM 5.1 missing from default dry-run")
    fable_result = run_python_module("--panel", "fable", "--dry-run", "release check")
    if "Panel: fable" not in fable_result.stdout:
        raise AssertionError("fable panel dry-run failed")
    if "local_kimi" not in fable_result.stdout or "kimi --print" not in fable_result.stdout:
        raise AssertionError("local Kimi CLI missing from fable dry-run")
    if "google/gemini-3-flash-preview" not in fable_result.stdout:
        raise AssertionError("Gemini 3 Flash missing from fable dry-run")
    if "deepseek/deepseek-v4-pro" not in fable_result.stdout:
        raise AssertionError("DeepSeek V4 Pro missing from fable dry-run")
    if "local_claude_sonnet" in fable_result.stdout or "--model sonnet" in fable_result.stdout:
        raise AssertionError("quota-sensitive Claude Sonnet should not be in fable dry-run")
    if "Judge: codex" not in fable_result.stdout:
        raise AssertionError("Codex judge missing from fable dry-run")


def run_doctor() -> None:
    result = run_python_module("--doctor")
    if "fusion-lite" not in result.stdout:
        raise AssertionError("--doctor did not print version")
    combined = f"{result.stdout}\n{result.stderr}"
    env_names = env_example_names()
    leaked_names = [name for name in env_names if name in combined]
    if leaked_names:
        raise AssertionError(f"--doctor printed env variable names unexpectedly: {', '.join(leaked_names)}")
    if re.search(r"(?i)\b(sk-[A-Za-z0-9_-]{12,}|or-[A-Za-z0-9_-]{12,})\b", combined):
        raise AssertionError("--doctor printed a key-like secret value")


def env_example_names() -> list[str]:
    names: list[str] = []
    env_example = ROOT / ".env.example"
    if not env_example.exists():
        return names
    for line in env_example.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        names.append(stripped.split("=", 1)[0].strip())
    return [name for name in names if name]


def run_python_module(*args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, "-m", "fusion_lite", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"command failed: {result.args}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    return result


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"command failed: {result.args}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    return result


def run_git(*args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"git command failed: {result.args}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
