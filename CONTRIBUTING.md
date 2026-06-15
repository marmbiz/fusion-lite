# Contributing

Fusion Lite is intentionally small: no runtime dependencies, explicit panel JSON, and local audit trails.

## Local Setup

```bash
python3 -m pip install -e .
fusion-lite --doctor
fusion-lite --list-panels
fusion-lite --dry-run "check"
```

## Development Checks

```bash
python3 scripts/validate_release.py
```

Keep changes scoped:

- Put reusable panel presets in `fusion_lite/panels/`.
- Keep private prompts, `.env`, and run outputs out of commits.
- Do not print API keys or CLI auth material.
- Prefer pinned model IDs for default panels; use latest aliases only in explicit experimental panels.
