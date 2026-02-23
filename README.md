# knowledge-vault (OpenClaw skill)

An Obsidian knowledge-vault ingestion workflow for OpenClaw.

## What it does

- Ingests content into an Obsidian vault under `knowledge/`.
- For X/Twitter status URLs: fetches the full thread via `bird`, saves raw JSON, generates a one-pass note (TL;DR + key points + tags), and (optionally) captures screenshots with headless Chrome.

## Folder layout

Inside your vault, this skill writes into:

- `knowledge/Notes/<direction>/...` (canonical notes)
- `knowledge/Attachments/<type>/...` (raw JSON, screenshots, PDFs, etc.)

## Prerequisites

- `python3`
- `bird` (for X thread fetching)
- `google-chrome-stable` (for screenshots)
- Python package: `Pillow` (for cropping + screenshot quality checks)

## X ingestion

Script: `scripts/ingest_x.py`

Examples:

```bash
python3 scripts/ingest_x.py "https://x.com/<user>/status/<id>" --vault "/path/to/your/obsidian-vault" --direction auto
```

Skip screenshots:

```bash
python3 scripts/ingest_x.py "https://x.com/<user>/status/<id>" --vault "/path/to/your/obsidian-vault" --direction auto --no-screenshot
```

## Notes

- X is JS-heavy and may lazy-load long articles/images; screenshots can be blank. The ingester includes a non-white pixel ratio check and retries with a larger `--virtual-time-budget` when needed.
- Very long tweet titles can exceed filesystem filename limits; the ingester falls back to short deterministic filenames based on `conversation_id`.

## License

MIT
