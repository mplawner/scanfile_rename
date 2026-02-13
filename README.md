# scanfile_rename

Rename scanned PDFs into human-readable filenames by extracting key fields (date, provider, document type, title). Text extraction runs first; if the PDF has little or no text, the tool can fall back to a vision pass via an OpenAI-compatible LLM endpoint (LM Studio and Ollama examples below).

## Key features

- Text-first extraction using Poppler `pdftotext`
- Vision fallback: render pages with Poppler `pdftoppm` and call an OpenAI-compatible LLM endpoint
- Copy (default) or move into an output directory; filenames are sanitized and de-duplicated
- Optional best-effort repair for some broken PDFs (qpdf/ghostscript)
- Best-effort PDF metadata enrichment via `pypdf` (classic DocumentInfo, not XMP)
- `--print-json` for debugging extracted fields

## Requirements

- Python 3.12 recommended
- System tools:
  - Required: Poppler (`pdftotext`, `pdftoppm`)
  - Optional (PDF repair helpers): `ghostscript` (`gs`), `qpdf`

macOS/Homebrew:

```bash
brew install poppler
brew install ghostscript qpdf
```

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

## Usage

Basic run (copies into `processed/` next to the input PDF by default):

```bash
python3 scanfile_rename.py "path/to/input.pdf"
```

More examples:

```bash
# Dry run (no file written)
python3 scanfile_rename.py "scan.pdf" --dry-run

# Copy into a specific directory
python3 scanfile_rename.py "scan.pdf" --outdir "./renamed"

# Move (destructive)
python3 scanfile_rename.py "scan.pdf" --move

# Debug: show extracted fields as JSON
python3 scanfile_rename.py "scan.pdf" --print-json
```

## Options

All flags below match `scanfile_rename.py`'s `argparse` setup:

- `--outdir DIR`: destination directory (default: `<input_dir>/processed`)
- `--move`: move instead of copy
- `--dry-run`: print the proposed filename, do not write a file
- `--print-json`: print extracted JSON (useful for debugging)
- `--no-progress`: disable progress output
- `--no-repair`: disable qpdf/ghostscript repair attempts
- `--keywords-count N`: number of keywords to include (default: 5)
- `--lm-timeout SEC`: LLM request timeout in seconds
- `--lm-retries N`: LLM max retries on network/server errors
- `--version`: print version and exit

## Configuration

Environment variables (defaults shown):

- `LLM_ENDPOINT` = `http://localhost:1234/v1/chat/completions` (OpenAI-compatible Chat Completions)
- `LLM_MODEL` = `qwen3-vl-8b-instruct`
- `LLM_TIMEOUT` = `120`
- `LLM_MAX_RETRIES` = `0`
- `PDFTOTEXT` = `/opt/homebrew/bin/pdftotext`
- `PDFTOPPM` = `/opt/homebrew/bin/pdftoppm`
- `GS` = `/opt/homebrew/bin/gs`
- `QPDF` = `/opt/homebrew/bin/qpdf`

Legacy aliases (still supported): `LM_STUDIO_ENDPOINT`, `LM_STUDIO_MODEL`, `LM_STUDIO_TIMEOUT`, `LM_STUDIO_MAX_RETRIES`

Tuning:

- `VISION_MAX_PAGES` (default: 3)
- `VISION_DPI` (default: 200)
- `MIN_TEXT_CHARS` (default: 200)

Notes:

- CLI flags override the LLM timeout/retry environment defaults.
- When `--print-json` is used and stdout is not a TTY (piping to a file), progress output is automatically disabled to keep JSON clean. Set `FORCE_PROGRESS=1` to force progress output while piping.

### LLM provider examples (OpenAI-compatible)

This tool uses the OpenAI-compatible `POST /v1/chat/completions` API. `LLM_ENDPOINT` can be the full chat-completions URL (default), or a base URL ending in `/v1` (or `/v1/`); it will be normalized to `/v1/chat/completions`.

LM Studio (OpenAI-compatible server):

```bash
# Base URL form (common in LM Studio docs)
export LLM_ENDPOINT="http://localhost:1234/v1"

# Model id (optional: list available models via GET /v1/models)
export LLM_MODEL="qwen3-vl-8b-instruct"
```

Ollama (OpenAI compatibility layer):

```bash
# OpenAI-compatible base URL (note the /v1/)
export LLM_ENDPOINT="http://localhost:11434/v1/"

# The request path used by this tool is POST /v1/chat/completions
export LLM_MODEL="llama3.2"
```

Vision note for Ollama OpenAI compatibility: images are supported via base64 content; image URL inputs are not supported in the OpenAI-compatible API.

## Metadata enrichment behavior

After the output file is written (post copy/move), the tool attempts to enrich classic PDF DocumentInfo metadata (Info dictionary, not XMP) using `pypdf`.

- Writes DocumentInfo keys like `/Title`, `/Author`, `/Subject`, `/Keywords`, `/CreationDate`, `/ModDate`
- Values are derived from extracted info plus local formatting helpers (for example, `/Title` is derived from the output filename)
- Skips metadata writing when the PDF appears encrypted or signed
- Best-effort: failures do not change the exit code

## Development and testing

```bash
python3 -m unittest discover -s tests
python3 -m unittest tests.test_core
```

## Troubleshooting

- Poppler tools not found: install Poppler and/or set `PDFTOTEXT` / `PDFTOPPM` to the correct executable paths.
- LLM connection errors: ensure your OpenAI-compatible LLM server is running and `LLM_ENDPOINT` is reachable (or the legacy `LM_STUDIO_ENDPOINT` alias); the default is `http://localhost:1234/v1/chat/completions`.
- Corrupt PDFs (Poppler syntax errors): install `qpdf` and/or `ghostscript` and avoid `--no-repair`.
- Encrypted or signed PDFs: the tool will still rename/copy/move the PDF, but metadata writing is skipped.
