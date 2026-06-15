# Release Checklist

- [ ] Run `python3 scripts/validate_release.py`.
- [ ] Run `fusion-lite --doctor` and confirm no secrets are printed.
- [ ] Confirm `.env`, `.fusion-lite/`, `runs/`, and private `prompts/` are not tracked.
- [ ] Confirm generated artifacts (`build/`, `dist/`, `*.egg-info/`, `__pycache__/`) are not tracked.
- [ ] Review `fusion_lite/panels/*.json` for current model IDs and pricing notes.
- [ ] Test a dry run after install: `fusion-lite --dry-run "release check"`.
- [ ] Optionally test a live thrift run: `fusion-lite --panel openrouter-thrift --judge codex "one sentence test"`.
- [ ] Confirm the release tag: `python3 scripts/release_version.py --check --tag`.
- [ ] Tag the release from the checked version: `git tag "$(python3 scripts/release_version.py --check --tag)"`.
