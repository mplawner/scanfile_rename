# macOS Finder Quick Action (Automator)

This folder contains a template Automator Quick Action script for running `scanfile_rename.py` on one or more selected PDFs in Finder.

The template script is:

- `quick_action/scanfile_rename_quick_action.zsh`

It expects the selected files as arguments, uses a lockdir under `/tmp` to prevent concurrent runs, and logs to:

- `~/Library/Logs/scanfile_rename/quick_action.log`

## Prereqs

- You have this repo on disk (any location).
- You created a venv at `REPO_DIR/.venv` and installed requirements:

```bash
cd "/path/to/scanfile_rename"
python3 -m venv .venv
"./.venv/bin/python3" -m pip install -r requirements.txt
```

- You installed Poppler (`pdftotext`, `pdftoppm`). On macOS with Homebrew:

```bash
brew install poppler
```

## Create the Quick Action in Automator

1) Open `Automator`.

2) Choose `Quick Action` (sometimes shown as `Service`).

3) At the top of the workflow, set:

- Workflow receives: `PDF files`
- In: `Finder`

4) Add an action: `Run Shell Script`.

5) Configure the action:

- Shell: `/bin/zsh`
- Pass input: `as arguments`

6) Paste the contents of `quick_action/scanfile_rename_quick_action.zsh` into the Run Shell Script box.

7) Edit the pasted script and set `REPO_DIR`:

```zsh
REPO_DIR="/absolute/path/to/scanfile_rename"
```

Notes:

- `REPO_DIR` must be the directory containing `scanfile_rename.py`.
- The script expects the Python interpreter at `REPO_DIR/.venv/bin/python3`.

8) Save the Quick Action (e.g. name it `Rename Scanned PDFs`).

## Use it

1) In Finder, select one or more PDF files.

2) Right-click -> `Quick Actions` -> choose your saved action.

The script will process each selected PDF and place the renamed file next to the original input (it runs `scanfile_rename.py ... --outdir <input_dir>`).

## Logs

The Quick Action writes logs to:

- `~/Library/Logs/scanfile_rename/quick_action.log`

If something fails, check this file first.

## Recommended first run (--dry-run)

For a safe first run, temporarily add `--dry-run` to the `python3 scanfile_rename.py ...` line inside the pasted script.

In the template, the call looks like this:

```zsh
"${PY}" "${SCRIPT}" "${f_abs}" --outdir "${outdir}"
```

Temporarily change it to:

```zsh
"${PY}" "${SCRIPT}" "${f_abs}" --outdir "${outdir}" --dry-run
```

When you are happy with the proposed names, remove `--dry-run`.

## Concurrency / lockdir

The Quick Action prevents concurrent runs using a lock directory:

- `/tmp/scanfile_rename_quick_action.${UID}.lock`

If Automator says another run is already in progress but you know it is stuck (for example, Automator was force-quit), you can clear the lock with:

```bash
rm -rf "/tmp/scanfile_rename_quick_action.$UID.lock"
```

After clearing the lockdir, run the Quick Action again and check the log file for the last failure.
