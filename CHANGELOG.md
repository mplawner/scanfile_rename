# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog (https://keepachangelog.com/en/1.1.0/),
and this project adheres to Semantic Versioning (https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-02-13
### Added
- Text-first extraction using Poppler `pdftotext`.
- Vision fallback: render pages with Poppler `pdftoppm` and call an OpenAI-compatible endpoint.
- Copy (default) or move into an output directory; filenames sanitized and de-duplicated.
- Optional best-effort repair for some broken PDFs (qpdf/ghostscript).
- Best-effort PDF metadata enrichment (classic DocumentInfo; skipped for encrypted/signed PDFs).
- Debugging/controls: `--print-json`, `--dry-run`, `--no-progress`, retry/timeout flags.
