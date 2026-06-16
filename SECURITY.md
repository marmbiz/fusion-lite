# Security

Fusion Lite stores prompt text, raw model responses, judge prompts, and metadata on disk for auditability.

Do not run confidential prompts unless you are comfortable with:

- the selected OpenRouter models seeing panel prompts;
- the selected direct API adapters sending prompts to their fixed official API endpoints;
- OpenAI data-sharing/free-daily-token panels sharing inputs and outputs with OpenAI when enabled for that project;
- the selected local judge CLI seeing panel outputs;
- run artifacts being written under `.fusion-lite/runs` or your configured `FUSION_LITE_RUNS_DIR`.

## Secrets

Use environment variables or a local `.env` file:

```bash
OPENROUTER_API_KEY=...
OPENAI_API_KEY=...
```

Never commit `.env`, run artifacts, or private prompt files. The repository `.gitignore` excludes these by default.

Fusion Lite automatically loads `.env` from the current working directory and from the source checkout when present, but only for known Fusion/provider keys. It ignores arbitrary process variables such as `PATH`, `PYTHONPATH`, and shell/tool options.

Panel JSON cannot override OpenRouter or DeepSeek API endpoints. This prevents downloaded panels from redirecting bearer tokens to untrusted hosts.

## Local CLI Trust

Local adapters execute `codex`, `claude`, `gemini`, `kimi`, and `grok` from `PATH`.
Only run Fusion Lite in environments where those binaries are trusted. A malicious shim earlier in `PATH` can see prompts and local run directories.

## Reporting

Please open a private GitHub security advisory if the repository enables advisories. If advisories are unavailable, contact the maintainer through the public GitHub profile or project website and ask for a private security channel. Do not include secrets, private prompts, or exploit payloads in public issues.
