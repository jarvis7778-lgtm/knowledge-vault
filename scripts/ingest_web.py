#!/usr/bin/env python3
"""Ingest a web URL into an Obsidian vault (knowledge-vault).

Design goal: deterministic file layout.
Content extraction is expected to be done by the agent via the `web_fetch` tool.
This script:
- Saves raw HTML via curl
- Saves extracted markdown (provided via --extracted-md-file or stdin)
- Writes a final note to knowledge/Notes/<direction>/Web/

Usage:
  python3 ingest_web.py <url> --vault <vault_path> [--direction <dir|auto>] \
    [--title "..."] [--tags "t1,t2"] [--tldr "..."] [--keypoints-file kp.txt] \
    [--extracted-md-file extracted.md | --extracted-md-stdin]

Notes:
- tags are capped externally by the agent (<=5). This script just writes what it's given.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import re
import subprocess
from pathlib import Path


def run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{p.stderr.strip()}")
    return p.stdout


def slugify(name: str, max_len: int = 80) -> str:
    name = re.sub(r"[\\/:*?\"<>|]", "-", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:max_len].rstrip(" .-")


def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()[:10]


def curl_save(url: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(
        ["curl", "-L", "--fail", "-sS", "-H", "User-Agent: Mozilla/5.0", "-o", str(out), url],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if p.returncode != 0:
        raise RuntimeError(f"curl failed: {url}\n{p.stderr.strip()}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--vault", required=True)
    ap.add_argument("--direction", default="auto")
    ap.add_argument("--title", default=None)
    ap.add_argument("--tags", default="")
    ap.add_argument("--tldr", default="")
    ap.add_argument("--keypoints-file", default=None)
    ap.add_argument("--extracted-md-file", default=None)
    ap.add_argument("--extracted-md-stdin", action="store_true")
    args = ap.parse_args()

    vault = Path(args.vault)
    base = vault / "knowledge"

    now = dt.datetime.now()
    today = now.strftime("%Y-%m-%d")

    # attachment bundle
    bundle = f"{today}-{sha1(args.url)}"
    attach_dir = base / "Attachments" / "Web" / bundle
    attach_dir.mkdir(parents=True, exist_ok=True)

    raw_html = attach_dir / "raw.html"
    curl_save(args.url, raw_html)

    extracted_md = attach_dir / "extracted.md"
    extracted_text = ""
    if args.extracted_md_file:
        extracted_text = Path(args.extracted_md_file).read_text(encoding="utf-8", errors="ignore")
    elif args.extracted_md_stdin:
        extracted_text = Path("/dev/stdin").read_text(encoding="utf-8", errors="ignore")
    if extracted_text:
        extracted_md.write_text(extracted_text, encoding="utf-8")

    # keypoints
    kps = ""
    if args.keypoints_file:
        kps = Path(args.keypoints_file).read_text(encoding="utf-8", errors="ignore").strip()

    def resolve_direction(direction: str, url: str, title: str, tags_csv: str) -> str:
        """Resolve direction.

        If direction == 'auto', pick a concrete folder based on simple heuristics.
        This is intentionally conservative (only a few stable buckets).
        """
        if direction != "auto":
            return direction

        hay = " ".join([url or "", title or "", tags_csv or ""]).lower()
        # Heuristics: code/engineering/devops/cloudflare/nextjs/etc -> code
        code_keywords = [
            "cloudflare",
            "worker",
            "workers",
            "next.js",
            "nextjs",
            "supabase",
            "postgres",
            "hyperdrive",
            "vercel",
            "devops",
            "kubernetes",
            "docker",
            "api",
            "typescript",
            "javascript",
        ]
        if any(k in hay for k in code_keywords):
            return "code"

        # default fallback
        return "Inbox"

    resolved_direction = resolve_direction(args.direction, args.url, (args.title or ""), args.tags)

    # direction path supports nested segments
    direction_path = Path(*[p for p in resolved_direction.split("/") if p])
    notes_dir = base / "Notes" / direction_path / "Web"
    notes_dir.mkdir(parents=True, exist_ok=True)

    title = args.title or args.url
    note_title = f"{today} - {slugify(title, 120)}"
    note_path = notes_dir / f"{note_title}.md"
    if note_path.exists():
        note_path = notes_dir / f"{note_title} ({bundle}).md"

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    md: list[str] = []
    md.append("---")
    md.append(f"source: {args.url}")
    md.append(f"saved_at: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    md.append("type: web")
    md.append(f"direction: {resolved_direction}")
    if tags:
        md.append(f"tags: [{', '.join(tags)}]")
    md.append(f"raw_html: {raw_html.relative_to(vault)}")
    if extracted_text:
        md.append(f"extracted_md: {extracted_md.relative_to(vault)}")
    md.append("---\n")

    md.append(f"# {title}\n")

    md.append("## TL;DR\n")
    md.append((args.tldr.strip() or "(Jarvis: 待生成)") + "\n")

    md.append("## Key points\n")
    if kps:
        # expect bullets already
        md.append(kps + "\n")
    else:
        md.append("- (Jarvis: 待生成)\n")

    md.append("## Extracted (markdown)\n")
    if extracted_text:
        md.append(extracted_text.strip() + "\n")
    else:
        md.append("(Jarvis: extracted markdown not provided)\n")

    note_path.write_text("\n".join(md), encoding="utf-8")
    print(str(note_path))


if __name__ == "__main__":
    main()
