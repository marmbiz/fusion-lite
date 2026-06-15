from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AdapterResult:
    id: str
    adapter: str
    model: str | None
    status: str
    content: str
    elapsed_seconds: float
    command: list[str] = field(default_factory=list)
    error: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    raw_json: dict[str, Any] | None = None


def run_adapter(spec: dict[str, Any], prompt: str, work_dir: Path, timeout: int) -> AdapterResult:
    adapter = str(spec["adapter"])
    if adapter == "gemini_cli":
        return _run_gemini_cli(spec, prompt, work_dir, timeout)
    if adapter == "kimi_cli":
        return _run_kimi_cli(spec, prompt, work_dir, timeout)
    if adapter == "grok_cli":
        return _run_grok_cli(spec, prompt, work_dir, timeout)
    if adapter == "claude_cli":
        return _run_claude_cli(spec, prompt, work_dir, timeout)
    if adapter == "codex_cli":
        return _run_codex_cli(spec, prompt, work_dir, timeout)
    if adapter == "deepseek_api":
        return _run_deepseek_api(spec, prompt, work_dir, timeout)
    if adapter == "openrouter_chat":
        return _run_openrouter_chat(spec, prompt, work_dir, timeout)
    return AdapterResult(
        id=str(spec.get("id") or adapter),
        adapter=adapter,
        model=spec.get("model"),
        status="error",
        content="",
        elapsed_seconds=0.0,
        error=f"unknown adapter: {adapter}",
    )


def render_command(spec: dict[str, Any], timeout: int) -> list[str]:
    adapter = str(spec["adapter"])
    prompt_placeholder = "<prompt>"
    if adapter == "gemini_cli":
        cmd = ["gemini", "-p", prompt_placeholder, "--output-format", "json", "--approval-mode", "plan"]
        if spec.get("model"):
            cmd.extend(["--model", str(spec["model"])])
        return cmd
    if adapter == "kimi_cli":
        cmd = [
            "kimi",
            "--print",
            "--output-format",
            "text",
            "--final-message-only",
            "--work-dir",
            "<work_dir>",
            "--max-steps-per-turn",
            str(spec.get("max_steps_per_turn") or 1),
            "--prompt",
            prompt_placeholder,
        ]
        if spec.get("thinking") is False:
            cmd.insert(1, "--no-thinking")
        elif spec.get("thinking") is True:
            cmd.insert(1, "--thinking")
        if spec.get("max_ralph_iterations") is not None:
            cmd.extend(["--max-ralph-iterations", str(spec["max_ralph_iterations"])])
        if spec.get("max_retries_per_step") is not None:
            cmd.extend(["--max-retries-per-step", str(spec["max_retries_per_step"])])
        if spec.get("agent"):
            cmd.extend(["--agent", str(spec["agent"])])
        if spec.get("model"):
            cmd.extend(["--model", str(spec["model"])])
        return cmd
    if adapter == "grok_cli":
        cmd = [
            "grok",
            "-p",
            prompt_placeholder,
            "--output-format",
            "json",
            "--permission-mode",
            "plan",
            "--sandbox",
            "read-only",
            "--max-turns",
            "1",
            "--disable-web-search",
        ]
        if spec.get("model"):
            cmd.extend(["--model", str(spec["model"])])
        return cmd
    if adapter == "claude_cli":
        cmd = [
            "claude",
            "-p",
            "--output-format",
            "json",
            "--tools",
            "",
            "--max-turns",
            str(spec.get("max_turns") or 10),
            "--no-session-persistence",
            prompt_placeholder,
        ]
        if spec.get("model"):
            cmd[1:1] = ["--model", str(spec["model"])]
        if spec.get("effort"):
            cmd[1:1] = ["--effort", str(spec["effort"])]
        return cmd
    if adapter == "codex_cli":
        cmd = [
            "codex",
            "exec",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ephemeral",
            "--output-last-message",
            "<output_file>",
            prompt_placeholder,
        ]
        if spec.get("model"):
            cmd[2:2] = ["--model", str(spec["model"])]
        return cmd
    if adapter == "deepseek_api":
        return ["POST", str(spec.get("api_url") or "https://api.deepseek.com/chat/completions")]
    if adapter == "openrouter_chat":
        return ["POST", "https://openrouter.ai/api/v1/chat/completions", str(spec.get("model") or "<model>")]
    return [adapter]


def _run_gemini_cli(spec: dict[str, Any], prompt: str, work_dir: Path, timeout: int) -> AdapterResult:
    cmd = ["gemini", "-p", prompt, "--output-format", "json", "--approval-mode", "plan"]
    if spec.get("model"):
        cmd.extend(["--model", str(spec["model"])])
    return _run_process_json_text(spec, cmd, work_dir, timeout, extract_text=_extract_gemini_text)


def _run_kimi_cli(spec: dict[str, Any], prompt: str, work_dir: Path, timeout: int) -> AdapterResult:
    resolved_model = str(spec.get("model") or _resolve_kimi_default_model() or "kimi_cli_default")
    cmd = [
        "kimi",
        "--print",
        "--output-format",
        "text",
        "--final-message-only",
        "--work-dir",
        str(work_dir.resolve()),
        "--max-steps-per-turn",
        str(spec.get("max_steps_per_turn") or 1),
        "--prompt",
        prompt,
    ]
    if spec.get("thinking") is False:
        cmd.insert(1, "--no-thinking")
    elif spec.get("thinking") is True:
        cmd.insert(1, "--thinking")
    if spec.get("max_ralph_iterations") is not None:
        cmd.extend(["--max-ralph-iterations", str(spec["max_ralph_iterations"])])
    if spec.get("max_retries_per_step") is not None:
        cmd.extend(["--max-retries-per-step", str(spec["max_retries_per_step"])])
    if spec.get("agent"):
        cmd.extend(["--agent", str(spec["agent"])])
    if spec.get("model"):
        cmd.extend(["--model", str(spec["model"])])
    result = _run_process_text(spec, cmd, work_dir, timeout)
    result.model = resolved_model
    result.content = _strip_kimi_resume_hint(result.content)
    if result.error:
        result.error = _strip_kimi_resume_hint(result.error)
    return result


def _run_grok_cli(spec: dict[str, Any], prompt: str, work_dir: Path, timeout: int) -> AdapterResult:
    cmd = [
        "grok",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--permission-mode",
        "plan",
        "--sandbox",
        "read-only",
        "--max-turns",
        "1",
        "--disable-web-search",
    ]
    if spec.get("model"):
        cmd.extend(["--model", str(spec["model"])])
    return _run_process_json_text(spec, cmd, work_dir, timeout, extract_text=_extract_grok_text)


def _run_claude_cli(spec: dict[str, Any], prompt: str, work_dir: Path, timeout: int) -> AdapterResult:
    cmd = [
        "claude",
        "-p",
        "--output-format",
        "json",
        "--tools",
        "",
        "--max-turns",
        str(spec.get("max_turns") or 10),
        "--no-session-persistence",
        prompt,
    ]
    if spec.get("model"):
        cmd[1:1] = ["--model", str(spec["model"])]
    if spec.get("effort"):
        cmd[1:1] = ["--effort", str(spec["effort"])]
    return _run_process_json_text(spec, cmd, work_dir, timeout, extract_text=_extract_claude_text)


def _run_codex_cli(spec: dict[str, Any], prompt: str, work_dir: Path, timeout: int) -> AdapterResult:
    output_file = work_dir / "codex-last-message.txt"
    cmd = [
        "codex",
        "exec",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--ephemeral",
        "--output-last-message",
        str(output_file),
        prompt,
    ]
    if spec.get("model"):
        cmd[2:2] = ["--model", str(spec["model"])]
    started = time.monotonic()
    proc = _run_subprocess(cmd, work_dir, timeout, spec)
    elapsed = time.monotonic() - started
    content = output_file.read_text(encoding="utf-8") if output_file.exists() else proc.stdout.strip()
    if proc.returncode != 0:
        return _error_result(spec, cmd, elapsed, proc)
    return AdapterResult(
        id=str(spec.get("id") or spec["adapter"]),
        adapter=str(spec["adapter"]),
        model=spec.get("model"),
        status="ok",
        content=content.strip(),
        elapsed_seconds=elapsed,
        command=_redact_command(cmd),
    )


def _run_deepseek_api(spec: dict[str, Any], prompt: str, work_dir: Path, timeout: int) -> AdapterResult:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    started = time.monotonic()
    if not api_key:
        return AdapterResult(
            id=str(spec.get("id") or spec["adapter"]),
            adapter=str(spec["adapter"]),
            model=spec.get("model"),
            status="skipped",
            content="",
            elapsed_seconds=0.0,
            error="DEEPSEEK_API_KEY is not set",
        )

    api_url = str(spec.get("api_url") or os.getenv("DEEPSEEK_API_URL") or "https://api.deepseek.com/chat/completions")
    model = str(spec.get("model") or "deepseek-chat")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Answer directly. Do not use tools. Do not modify files."},
            {"role": "user", "content": prompt},
        ],
        "temperature": float(spec.get("temperature", 0.2)),
        "max_tokens": int(spec.get("max_tokens", 2500)),
    }
    req = urllib.request.Request(
        api_url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")[:2000]
        return AdapterResult(
            id=str(spec.get("id") or spec["adapter"]),
            adapter=str(spec["adapter"]),
            model=model,
            status="error",
            content="",
            elapsed_seconds=time.monotonic() - started,
            command=["POST", api_url],
            error=f"HTTP {exc.code}: {error_body}",
        )
    except Exception as exc:  # noqa: BLE001 - adapter boundary should not crash the run
        return AdapterResult(
            id=str(spec.get("id") or spec["adapter"]),
            adapter=str(spec["adapter"]),
            model=model,
            status="error",
            content="",
            elapsed_seconds=time.monotonic() - started,
            command=["POST", api_url],
            error=str(exc),
        )

    choices = payload.get("choices") or []
    message = choices[0].get("message", {}) if choices else {}
    content = str(message.get("content") or "").strip()
    return AdapterResult(
        id=str(spec.get("id") or spec["adapter"]),
        adapter=str(spec["adapter"]),
        model=model,
        status="ok" if content else "error",
        content=content,
        elapsed_seconds=time.monotonic() - started,
        command=["POST", api_url],
        error=None if content else "empty DeepSeek response",
        usage=payload.get("usage") or {},
        raw_json=payload,
    )


def _run_openrouter_chat(spec: dict[str, Any], prompt: str, work_dir: Path, timeout: int) -> AdapterResult:
    api_key = os.getenv("OPENROUTER_API_KEY")
    started = time.monotonic()
    if not api_key:
        return AdapterResult(
            id=str(spec.get("id") or spec["adapter"]),
            adapter=str(spec["adapter"]),
            model=spec.get("model"),
            status="skipped" if spec.get("optional") else "error",
            content="",
            elapsed_seconds=0.0,
            error="OPENROUTER_API_KEY is not set",
        )

    api_url = str(spec.get("api_url") or "https://openrouter.ai/api/v1/chat/completions")
    model = str(spec["model"])
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Answer independently. Do not mention other models. Do not use tools."},
            {"role": "user", "content": prompt},
        ],
        "temperature": float(spec.get("temperature", 0.2)),
        "max_tokens": int(spec.get("max_tokens", 2500)),
    }
    if spec.get("reasoning") is not None:
        body["reasoning"] = spec["reasoning"]
    provider_sort = spec.get("provider_sort", "price")
    if provider_sort:
        body["provider"] = {"sort": provider_sort}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    http_referer = os.getenv("OPENROUTER_HTTP_REFERER") or os.getenv("OPENROUTER_SITE_URL")
    title = os.getenv("OPENROUTER_TITLE")
    if http_referer:
        headers["HTTP-Referer"] = http_referer
    if title:
        headers["X-OpenRouter-Title"] = title

    req = urllib.request.Request(
        api_url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")[:2000]
        return AdapterResult(
            id=str(spec.get("id") or spec["adapter"]),
            adapter=str(spec["adapter"]),
            model=model,
            status="error",
            content="",
            elapsed_seconds=time.monotonic() - started,
            command=["POST", api_url, model],
            error=f"HTTP {exc.code}: {error_body}",
        )
    except Exception as exc:  # noqa: BLE001 - adapter boundary should not crash the run
        return AdapterResult(
            id=str(spec.get("id") or spec["adapter"]),
            adapter=str(spec["adapter"]),
            model=model,
            status="error",
            content="",
            elapsed_seconds=time.monotonic() - started,
            command=["POST", api_url, model],
            error=str(exc),
        )

    choices = payload.get("choices") or []
    message = choices[0].get("message", {}) if choices else {}
    content = extract_openai_style_text(message.get("content"))
    served_model = str(payload.get("model") or model)
    return AdapterResult(
        id=str(spec.get("id") or spec["adapter"]),
        adapter=str(spec["adapter"]),
        model=served_model,
        status="ok" if content else "error",
        content=content,
        elapsed_seconds=time.monotonic() - started,
        command=["POST", api_url, model],
        error=None if content else "empty OpenRouter response",
        usage=payload.get("usage") or {},
        raw_json=payload,
    )


def _run_process_text(spec: dict[str, Any], cmd: list[str], work_dir: Path, timeout: int) -> AdapterResult:
    started = time.monotonic()
    if not shutil.which(cmd[0]):
        return _missing_binary_result(spec, cmd[0])
    proc = _run_subprocess(cmd, work_dir, timeout, spec)
    elapsed = time.monotonic() - started
    if proc.returncode != 0:
        return _error_result(spec, cmd, elapsed, proc)
    return AdapterResult(
        id=str(spec.get("id") or spec["adapter"]),
        adapter=str(spec["adapter"]),
        model=spec.get("model"),
        status="ok",
        content=proc.stdout.strip(),
        elapsed_seconds=elapsed,
        command=_redact_command(cmd),
    )


def _run_process_json_text(
    spec: dict[str, Any],
    cmd: list[str],
    work_dir: Path,
    timeout: int,
    extract_text,
) -> AdapterResult:
    started = time.monotonic()
    if not shutil.which(cmd[0]):
        return _missing_binary_result(spec, cmd[0])
    proc = _run_subprocess(cmd, work_dir, timeout, spec)
    elapsed = time.monotonic() - started
    if proc.returncode != 0:
        return _error_result(spec, cmd, elapsed, proc)
    raw_json = _extract_json_object(proc.stdout)
    content = extract_text(raw_json, proc.stdout)
    if not content.strip():
        return AdapterResult(
            id=str(spec.get("id") or spec["adapter"]),
            adapter=str(spec["adapter"]),
            model=spec.get("model"),
            status="error",
            content="",
            elapsed_seconds=elapsed,
            command=_redact_command(cmd),
            error="empty response",
            raw_json=raw_json,
        )
    usage = _extract_usage(raw_json)
    return AdapterResult(
        id=str(spec.get("id") or spec["adapter"]),
        adapter=str(spec["adapter"]),
        model=spec.get("model"),
        status="ok",
        content=content.strip(),
        elapsed_seconds=elapsed,
        command=_redact_command(cmd),
        usage=usage,
        raw_json=raw_json,
    )


def _run_subprocess(cmd: list[str], work_dir: Path, timeout: int, spec: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    progress_interval = int(spec.get("progress_interval_seconds") or 0)
    progress_label = _progress_label(spec)
    if progress_interval > 0:
        return _run_subprocess_with_progress(cmd, work_dir, timeout, progress_interval, progress_label)
    try:
        proc = subprocess.run(
            cmd,
            cwd=work_dir,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        _write_process_diagnostics(work_dir, cmd, proc)
        return proc
    except subprocess.TimeoutExpired as exc:
        proc = subprocess.CompletedProcess(
            args=cmd,
            returncode=124,
            stdout=exc.stdout if isinstance(exc.stdout, str) else "",
            stderr=f"timeout after {timeout}s\n{exc.stderr or ''}",
        )
        _write_process_diagnostics(work_dir, cmd, proc)
        return proc


def _run_subprocess_with_progress(
    cmd: list[str],
    work_dir: Path,
    timeout: int,
    progress_interval: int,
    label: str,
) -> subprocess.CompletedProcess[str]:
    started = time.monotonic()
    deadline = started + timeout
    next_progress = started + progress_interval
    proc = subprocess.Popen(
        cmd,
        cwd=work_dir,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _progress(f"{label} started (timeout {timeout}s)")
    while True:
        now = time.monotonic()
        remaining = deadline - now
        if remaining <= 0:
            proc.kill()
            stdout, stderr = proc.communicate()
            elapsed = int(time.monotonic() - started)
            _progress(f"{label} timed out after {elapsed}s")
            completed = subprocess.CompletedProcess(
                args=cmd,
                returncode=124,
                stdout=stdout or "",
                stderr=f"timeout after {timeout}s\n{stderr or ''}",
            )
            _write_process_diagnostics(work_dir, cmd, completed)
            return completed

        wait_for = max(0.1, min(remaining, max(0.1, next_progress - now)))
        try:
            stdout, stderr = proc.communicate(timeout=wait_for)
            elapsed = int(time.monotonic() - started)
            if proc.returncode == 0:
                _progress(f"{label} finished in {elapsed}s")
            else:
                _progress(f"{label} exited {proc.returncode} after {elapsed}s")
            completed = subprocess.CompletedProcess(
                args=cmd,
                returncode=proc.returncode,
                stdout=stdout or "",
                stderr=stderr or "",
            )
            _write_process_diagnostics(work_dir, cmd, completed)
            return completed
        except subprocess.TimeoutExpired:
            now = time.monotonic()
            if now >= next_progress:
                elapsed = int(now - started)
                _progress(f"{label} still running ({elapsed}s elapsed, timeout {timeout}s)")
                next_progress = now + progress_interval


def _progress(message: str) -> None:
    print(f"[fusion-lite] {message}", file=sys.stderr, flush=True)


def _progress_label(spec: dict[str, Any]) -> str:
    label = str(spec.get("id") or spec.get("adapter") or "adapter")
    model = spec.get("model")
    return f"{label} ({model})" if model else label


def _error_result(spec: dict[str, Any], cmd: list[str], elapsed: float, proc: subprocess.CompletedProcess[str]) -> AdapterResult:
    raw_json = _extract_json_object(proc.stdout)
    details = _format_process_error(proc, raw_json)
    content = "" if raw_json and raw_json.get("is_error") is True else proc.stdout.strip()
    return AdapterResult(
        id=str(spec.get("id") or spec["adapter"]),
        adapter=str(spec["adapter"]),
        model=spec.get("model"),
        status="error",
        content=content,
        elapsed_seconds=elapsed,
        command=_redact_command(cmd),
        error=f"exit {proc.returncode}: {details[:2000]}",
        usage=_extract_usage(raw_json),
        raw_json=raw_json,
    )


def _format_process_error(proc: subprocess.CompletedProcess[str], raw_json: dict[str, Any] | None = None) -> str:
    parts = []
    json_error = _extract_cli_json_error(raw_json)
    if json_error:
        parts.append(json_error)
    stderr = (proc.stderr or "").strip()
    stdout = (proc.stdout or "").strip()
    if stderr:
        parts.append(f"stderr:\n{stderr}")
    if stdout and not json_error:
        parts.append(f"stdout:\n{stdout}")
    return "\n\n".join(parts).strip()


def _extract_cli_json_error(raw_json: dict[str, Any] | None) -> str:
    if not raw_json:
        return ""
    if raw_json.get("is_error") is not True and not raw_json.get("api_error_status"):
        return ""
    status = raw_json.get("api_error_status")
    result = str(raw_json.get("result") or raw_json.get("error") or raw_json.get("message") or "").strip()
    subtype = str(raw_json.get("subtype") or "").strip()
    prefix = "CLI JSON error"
    if status:
        prefix = f"API error {status}"
    elif subtype:
        prefix = f"CLI error ({subtype})"
    return f"{prefix}: {result}" if result else prefix


def _write_process_diagnostics(work_dir: Path, cmd: list[str], proc: subprocess.CompletedProcess[str]) -> None:
    try:
        work_dir.mkdir(parents=True, exist_ok=True)
        (work_dir / "command.txt").write_text(shell_join(_redact_command(cmd)) + "\n", encoding="utf-8")
        (work_dir / "stdout.txt").write_text(proc.stdout or "", encoding="utf-8")
        (work_dir / "stderr.txt").write_text(proc.stderr or "", encoding="utf-8")
    except OSError:
        return


def _strip_kimi_resume_hint(text: str | None) -> str:
    if not text:
        return ""
    lines = []
    for line in text.splitlines():
        if line.strip().startswith("To resume this session: kimi -r "):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _resolve_kimi_default_model() -> str | None:
    env_model = os.getenv("KIMI_MODEL")
    if env_model:
        return env_model
    config_path = Path(os.getenv("KIMI_CONFIG_FILE") or Path.home() / ".kimi" / "config.toml")
    try:
        config_text = config_path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r'(?m)^\s*default_model\s*=\s*["\']([^"\']+)["\']\s*$', config_text)
    return match.group(1) if match else None


def _missing_binary_result(spec: dict[str, Any], binary: str) -> AdapterResult:
    status = "skipped" if spec.get("optional") else "error"
    return AdapterResult(
        id=str(spec.get("id") or spec["adapter"]),
        adapter=str(spec["adapter"]),
        model=spec.get("model"),
        status=status,
        content="",
        elapsed_seconds=0.0,
        command=[binary],
        error=f"binary not found on PATH: {binary}",
    )


def _extract_gemini_text(raw_json: dict[str, Any] | None, stdout: str) -> str:
    if raw_json:
        return str(raw_json.get("response") or raw_json.get("text") or raw_json.get("result") or "")
    return stdout


def _extract_grok_text(raw_json: dict[str, Any] | None, stdout: str) -> str:
    if raw_json:
        for key in ("response", "result", "text", "content", "message"):
            if key in raw_json and raw_json[key]:
                return str(raw_json[key])
    return stdout


def _extract_claude_text(raw_json: dict[str, Any] | None, stdout: str) -> str:
    if raw_json:
        for key in ("result", "response", "text", "content"):
            if key in raw_json and raw_json[key]:
                return str(raw_json[key])
    return stdout


def _extract_usage(raw_json: dict[str, Any] | None) -> dict[str, Any]:
    if not raw_json:
        return {}
    for key in ("usage", "stats"):
        if isinstance(raw_json.get(key), dict):
            return raw_json[key]
    return {}


def extract_openai_style_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
                elif "text" in item:
                    parts.append(str(item.get("text") or ""))
        return "".join(parts).strip()
    return str(content or "").strip()


def _extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    for index, char in enumerate(stripped):
        if char != "{":
            continue
        try:
            parsed = json.loads(stripped[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _redact_command(cmd: list[str]) -> list[str]:
    redacted: list[str] = []
    skip_next = False
    binary = cmd[0] if cmd else ""
    for index, part in enumerate(cmd):
        if skip_next:
            redacted.append("<redacted>")
            skip_next = False
            continue
        redacted.append(part)
        if part == "--prompt":
            skip_next = True
        elif part == "-p" and binary in {"gemini", "grok"}:
            skip_next = True
        elif binary == "claude" and index == len(cmd) - 2:
            skip_next = True
    return redacted


def shell_join(cmd: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)
