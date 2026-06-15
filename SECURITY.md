# Security

Fusion Lite stores prompt text, raw model responses, judge prompts, and metadata on disk for auditability.

Do not run confidential prompts unless you are comfortable with:

- the selected OpenRouter models seeing panel prompts;
- the selected local judge CLI seeing panel outputs;
- run artifacts being written under `.fusion-lite/runs` or your configured `FUSION_LITE_RUNS_DIR`.

## Secrets

Use environment variables or a local `.env` file:

```bash
OPENROUTER_API_KEY=...
```

Never commit `.env`, run artifacts, or private prompt files. The repository `.gitignore` excludes these by default.

## Reporting

Please open a private GitHub security advisory if the repository enables advisories. Otherwise, open an issue that describes the risk without including secrets or private prompts.
