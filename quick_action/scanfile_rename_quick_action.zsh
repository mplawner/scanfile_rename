#!/bin/zsh

# Automator Quick Action template for scanfile_rename
# - Expects selected files as argv
# - Uses a lockdir under /tmp to prevent concurrent runs
# - Logs to ~/Library/Logs/scanfile_rename/quick_action.log

# --- Configuration (edit these) ---
REPO_DIR=""  # Set to the directory containing scanfile_rename.py (e.g. "/path/to/scanfile_rename")
LOCKDIR="/tmp/scanfile_rename_quick_action.${UID}.lock"
LOG="$HOME/Library/Logs/scanfile_rename/quick_action.log"

set -euo pipefail 2>/dev/null || {
  set -euo
  set -o pipefail
}

_show_dialog() {
  local title="$1"
  local msg="$2"

  /usr/bin/osascript - "$title" "$msg" <<'APPLESCRIPT'
on run argv
  set theTitle to item 1 of argv
  set theMsg to item 2 of argv
  display dialog theMsg with title theTitle buttons {"OK"} default button "OK"
end run
APPLESCRIPT
}

_die() {
  local msg="$1"
  print -r -- "ERROR: ${msg}" >&2
  _show_dialog "scanfile_rename (Quick Action)" "$msg"
  exit 1
}

_require_repo_dir() {
  if [[ -z "${REPO_DIR}" ]]; then
    _die "REPO_DIR is not set. Edit this script and set REPO_DIR to your scanfile_rename repo directory."
  fi
  if [[ ! -d "${REPO_DIR}" ]]; then
    _die "REPO_DIR is not a directory: ${REPO_DIR}"
  fi
}

_setup_lock() {
  if ! /bin/mkdir "${LOCKDIR}" 2>/dev/null; then
    _die "Another scanfile_rename Quick Action run is already in progress. (lock: ${LOCKDIR})"
  fi

  trap '_cleanup_lock' EXIT INT TERM HUP
}

_cleanup_lock() {
  [[ -d "${LOCKDIR}" ]] && /bin/rm -rf "${LOCKDIR}" || true
}

_setup_logging() {
  if [[ -z "${HOME:-}" ]]; then
    _die "HOME is not set; cannot determine log path."
  fi

  /bin/mkdir -p "${LOG:h}"
  {
    print -r -- ""
    print -r -- "---- $(/bin/date '+%Y-%m-%d %H:%M:%S') scanfile_rename Quick Action ----"
    print -r -- "REPO_DIR=${REPO_DIR}"
    print -r -- "LOCKDIR=${LOCKDIR}"
    print -r -- "ARGS_COUNT=$#"
  } >>"${LOG}"

  exec >>"${LOG}" 2>&1
}

_is_pdf_path() {
  local f="$1"
  [[ "${f:l}" == *.pdf ]]
}

main() {
  _setup_logging
  _setup_lock

  _require_repo_dir

  local PY="${REPO_DIR}/.venv/bin/python3"
  local SCRIPT="${REPO_DIR}/scanfile_rename.py"

  if [[ ! -x "${PY}" ]]; then
    _die "Python not found or not executable: ${PY} (did you create the venv at ${REPO_DIR}/.venv?)"
  fi
  if [[ ! -f "${SCRIPT}" ]]; then
    _die "Script not found: ${SCRIPT}"
  fi

  if [[ "$#" -eq 0 ]]; then
    _die "No files provided. (This Quick Action expects selected PDF files as input.)"
  fi

  local processed=0
  local skipped=0
  local failed=0

  local f
  for f in "$@"; do
    if [[ ! -e "${f}" ]]; then
      print -r -- "Skipping missing path: ${f}"
      skipped=$((skipped + 1))
      continue
    fi

    if [[ -d "${f}" ]]; then
      print -r -- "Skipping directory: ${f}"
      skipped=$((skipped + 1))
      continue
    fi

    if ! _is_pdf_path "${f}"; then
      print -r -- "Skipping non-PDF: ${f}"
      skipped=$((skipped + 1))
      continue
    fi

    local f_abs="${f:A}"
    local outdir="${f_abs:h}"

    print -r -- "Processing: ${f_abs}"
    if ! "${PY}" "${SCRIPT}" "${f_abs}" --outdir "${outdir}"; then
      failed=$((failed + 1))
      _die "scanfile_rename failed for: ${f_abs} (see log: ${LOG})"
    fi

    processed=$((processed + 1))
  done

  local nl=$'\n'
  local msg="Done. Processed ${processed} PDF(s); skipped ${skipped}; failures ${failed}.${nl}${nl}Log: ${LOG}"
  _show_dialog "scanfile_rename (Quick Action)" "${msg}"
}

main "$@"
