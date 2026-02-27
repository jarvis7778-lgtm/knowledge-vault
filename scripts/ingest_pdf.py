#!/usr/bin/env python3
"""Ingest a local PDF file into an Obsidian vault.

- Copies the PDF into: knowledge/Attachments/PDF/<slug>/original.pdf
- Extracts text with `pdftotext` into: knowledge/Attachments/PDF/<slug>/extracted.txt
- Writes a Markdown note into: knowledge/Sources/PDF/

Usage:
  python3 ingest_pdf.py /path/to/file.pdf --vault <vault_path> [--direction <name>]
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import subprocess
import re
from pathlib import Path


def slugify(name: str, max_len: int = 80) -> str:
    name = re.sub(r"[\\/:*?\"<>|]", "-", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:max_len].rstrip(" .-")


def run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{p.stderr.strip()}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--vault", required=True)
    ap.add_argument("--direction", default="Inbox")
    ap.add_argument("--max-chars", type=int, default=20000)
    args = ap.parse_args()

    vault = Path(args.vault)
    base = vault / "knowledge"

    src_pdf = Path(args.pdf).expanduser().resolve()
    if not src_pdf.exists():
        raise FileNotFoundError(str(src_pdf))
    if src_pdf.suffix.lower() != ".pdf":
        raise ValueError("input must be a .pdf")

    attach_base = base / "Attachments" / "PDF"

    direction_path = Path(*[p for p in args.direction.split("/") if p])
    notes_dir = base / "Notes" / direction_path / "PDF"

    attach_base.mkdir(parents=True, exist_ok=True)
    notes_dir.mkdir(parents=True, exist_ok=True)

    now = dt.datetime.now()
    today = now.strftime("%Y-%m-%d")

    stem = slugify(src_pdf.stem)
    bundle_dir = attach_base / f"{today}-{stem}"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    copied_pdf = bundle_dir / "original.pdf"
    shutil.copy2(src_pdf, copied_pdf)

    extracted_txt = bundle_dir / "extracted.txt"
    run(["pdftotext", "-layout", str(copied_pdf), str(extracted_txt)])

    text = extracted_txt.read_text(encoding="utf-8", errors="ignore")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > args.max_chars:
        text = text[: args.max_chars] + "\n\n...(truncated)"

    title = src_pdf.stem
    note_title = f"{today} - {slugify(title, 120)}"
    note_path = notes_dir / f"{note_title}.md"
    if note_path.exists():
        note_path = notes_dir / f"{note_title} ({bundle_dir.name}).md"

    md: list[str] = []
    md.append("---")
    md.append(f"source: file://{src_pdf.name}")
    md.append(f"saved_at: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    md.append("type: pdf")
    md.append(f"direction: {args.direction}")
    md.append("tags: [pdf]")
    md.append(f"pdf_file: {copied_pdf.relative_to(vault)}")
    md.append(f"text_file: {extracted_txt.relative_to(vault)}")
    md.append("---\n")

    md.append(f"# {title}\n")
    md.append("## TL;DR\n\n(Jarvis: 待生成)\n")
    md.append("## Key points\n\n- (Jarvis: 待生成)\n")
    md.append("## Extracted text (best-effort)\n")
    md.append(text + "\n")

    note_path.write_text("\n".join(md), encoding="utf-8")
    print(str(note_path))


if __name__ == "__main__":
    main()
