---
name: knowledge-vault
description: Obsidian 知识库入库与检索工作流。用于当用户说“入库/收录/存到知识库”并提供 URL / x.com 推文链接 / PDF 文件路径时：自动抓取、落盘到 Obsidian vault 的 knowledge/ 目录结构（knowledge/Inbox, knowledge/Sources/{Web,PDF,YouTube,X}, knowledge/Notes, knowledge/Attachments），并写入带 YAML frontmatter 的 Markdown（含 direction/方向字段）。也用于当用户说“读取/汇总 知识库里某方向/某主题”时：在 vault/knowledge/Notes 与 vault/knowledge/Sources 内按 direction 与关键词检索并汇总。
---

# Knowledge Vault (Obsidian)

## Fixed locations (important)

- **Vault root**: `/path/to/your/obsidian-vault` (example)
- **All knowledge content lives under**: `vault/knowledge/`
  - `knowledge/Inbox/`
  - `knowledge/Sources/Web/`
  - `knowledge/Sources/PDF/`
  - `knowledge/Sources/YouTube/` (link-card only unless user explicitly wants transcription)
  - `knowledge/Sources/X/` (optional raw area; canonical notes should be under `knowledge/Notes/<direction>/X/`)
  - `knowledge/Notes/` (**direction-first; final notes live here**)
  - `knowledge/Attachments/`

Never write new notes into the vault root.

## User-facing commands (how to interpret)

### A) Ingest / 入库

Hard requirement: **one-pass final note**
- Do not leave placeholders like "(Jarvis: 待生成)".
- Every ingest must finish with: TL;DR + Key points + tags (<=5) written into the same note.

When the user says any of:
- “入库 …”, “收录 …”, “存到知识库 …”, “保存 … 到知识库”

Do:
1) **Detect item type**
   - `x.com/.../status/<id>` → X thread
   - local path ending with `.pdf` → PDF
   - other `http(s)` → Web article
   - YouTube → **default link-card only** (no audio download/transcription) unless user explicitly asks for transcript
2) **Ask for `direction/方向` only if missing**
   - If user did not provide a direction, default `direction: auto` (auto-route into the right folder).
   - **Final notes always go to** `knowledge/Notes/<direction>/` (direction-first).
3) **Write Markdown note** into `knowledge/Notes/<direction>/` with YAML frontmatter:
   - `source`, `saved_at`, `type`, `direction`, `tags`, and a pointer to raw attachment path if any.
4) **Store raw attachments** under `knowledge/Attachments/<Type>/<id>/...`.

Implementation shortcuts (prefer deterministic scripts):
- X: **use the skill-bundled ingester** `skills/knowledge-vault/scripts/ingest_x.py` (default `--direction auto`)
  - Default behavior: capture tweet/article screenshots into `knowledge/Attachments/X/<conversation_id>/`.
  - If the user explicitly says **不要截图/不需要截图/skip screenshot**, then ingest **without** screenshots (pass a `--no-screenshot` flag once implemented, or temporarily skip calling the screenshot step).
  - It already implements: `bird thread --json` → save `thread.json` → **headless Chrome screenshot** (best-effort) → optional crop → write a one-pass note (TL;DR + Key points + tags).
  - Screenshot mechanism (no Playwright): calls `/usr/bin/google-chrome-stable --headless=new --screenshot=...` with a virtual-time budget to reduce X lazy-load blank pages; then crops to `*.article.png`.
  - Output paths:
    - Note: `knowledge/Notes/<direction>/X/`
    - Attachments: `knowledge/Attachments/X/<conversation_id>/` (including `tweet-<id>.png` and `tweet-<id>.article.png` when available)
  - **Do not** rely on OpenClaw `browser` tool for X Article screenshots by default; it may fail due to loopback SSRF restrictions (127.0.0.1/CDP).
  - Edge case: **filename too long**. If re-ingesting would create an overlong note path, keep the existing note and only generate screenshot + update the note’s `article_screenshot:` and embed.
- PDF: run bundled `skills/knowledge-vault/scripts/ingest_pdf.py`
- Web: use `web_fetch` tool to get readable markdown, save `raw.html` under `knowledge/Attachments/Web/<bundle>/raw.html`, then write the final note under `knowledge/Notes/<direction>/Web/`.
  - Auto-generate **detailed** TL;DR + Key points + tags (<=5).
  - Save extracted markdown to `knowledge/Attachments/Web/<bundle>/extracted.md` for traceability.
  - Use bundled `scripts/ingest_web.py` to write the final note once you have: title, tldr, keypoints, tags, extracted markdown.

### B) Read / summarize by direction

When the user says:
- “读取知识库里 <方向> …” / “把 <方向> 相关内容汇总一下”

Do:
1) Search in this order (direction-first):
   - `knowledge/Notes/<方向>/` (if exists)
   - then `knowledge/Sources/**` filtering by frontmatter `direction: <方向>`
2) Use fast local search tools:
   - `rg -n "^direction: <方向>$" vault/knowledge -S`
   - `obsidian-cli search-content "direction: <方向>"` (if available)
3) Return:
   - 5–15 bullet summary
   - list of relevant note paths (so the user can open them)

## Output conventions

- **Math (Obsidian/KaTeX):** when writing math, wrap inline math with `$...$` and block math with `$$...$$` so it renders correctly.
- **Tags:** keep `tags:` <= 5 items (user preference).

- Keep note title: `YYYY-MM-DD - <short title>`
- Always include frontmatter `direction:`.
- Default: every ingest produces a final note under `knowledge/Notes/<direction>/...`.
- Optionally keep a raw/Source note too if helpful, but the user-facing canonical note lives in Notes.
