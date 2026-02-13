# Contributing

Thanks for taking the time to contribute.

This repo is intentionally small: the main entrypoint is `scanfile_rename.py`.

## Dev setup

Create a virtualenv and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

System tools are required for normal operation (Poppler `pdftotext`/`pdftoppm`); see `README.md` for install notes.

## Run checks

Syntax check (required for any code change):

```bash
python3 -m py_compile scanfile_rename.py
```

Tests:

```bash
python3 -m unittest discover -s tests
```

## Contribution expectations

- Keep diffs small and focused; prefer one logical change per PR.
- For user-visible changes, update `CHANGELOG.md` in the same PR.
- Keep stdout stable; consider `--no-progress` and `--print-json` behavior before changing output.
- Do not add new dependencies unless there is a strong reason.
- `_versions/` is local-only, gitignored, and should not be committed.
