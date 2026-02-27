#!/usr/bin/env python3
"""Ingest an X/Twitter tweet (and its conversation thread) into an Obsidian vault.

- Uses `bird thread --json` to fetch the conversation thread containing the tweet.
- Writes a Markdown note into: knowledge/Notes/<direction>/X/
- Stores raw JSON + screenshots under: knowledge/Attachments/X/<conversation_id>/

Usage:
  python3 ingest_x.py <tweet_url_or_id> --vault <vault_path> [--direction <name>]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path


def run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{p.stderr.strip()}")
    return p.stdout


def slugify(name: str, max_len: int = 120) -> str:
    name = re.sub(r"[\\/:*?\"<>|]", "-", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:max_len].rstrip(" .-")


def pick_main_tweet(thread: list[dict], target_id: str | None) -> dict | None:
    if not thread:
        return None
    if target_id:
        for t in thread:
            if str(t.get("id")) == str(target_id):
                return t
    return thread[0]


def extract_id(url_or_id: str) -> str | None:
    s = url_or_id.strip()
    if re.fullmatch(r"\d{8,22}", s):
        return s
    m = re.search(r"/status/(\d{8,22})", s)
    return m.group(1) if m else None


def _curl_text(url: str) -> str:
    p = subprocess.run(
        [
            "curl",
            "-L",
            "--fail",
            "-sS",
            "--max-time",
            "20",
            "-H",
            "User-Agent: Mozilla/5.0",
            url,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if p.returncode != 0:
        raise RuntimeError(f"curl fetch failed: {url}\n{p.stderr.strip()}")
    return p.stdout


def _download(url: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(
        [
            "curl",
            "-L",
            "--fail",
            "-sS",
            "--max-time",
            "60",
            "-H",
            "User-Agent: Mozilla/5.0",
            "-o",
            str(out_path),
            url,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if p.returncode != 0:
        raise RuntimeError(f"curl download failed: {url} -> {out_path}\n{p.stderr.strip()}")


def _resolve_url(url: str) -> str:
    """Follow redirects and return final URL."""
    p = subprocess.run(
        [
            "curl",
            "-Ls",
            "--max-time",
            "20",
            "-o",
            "/dev/null",
            "-w",
            "%{url_effective}",
            url,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if p.returncode != 0:
        return url
    out = (p.stdout or "").strip()
    return out or url


def _image_nonwhite_ratio(png_path: Path, *, thr: int = 250, sample: int = 4000) -> float:
    """Rudimentary blank-check.

    Returns fraction of sampled pixels that are "non-white".
    Used to detect X lazy-load blank screenshots.
    """

    try:
        from PIL import Image
    except Exception:
        return 1.0  # can't validate; assume ok

    try:
        img = Image.open(png_path).convert("RGB")
    except Exception:
        return 0.0

    w, h = img.size
    if w <= 0 or h <= 0:
        return 0.0

    import random

    pix = img.load()
    random.seed(0)
    non = 0
    for _ in range(max(500, sample)):
        x = random.randrange(w)
        y = random.randrange(h)
        r, g, b = pix[x, y]
        if r < thr or g < thr or b < thr:
            non += 1
    return non / max(500, sample)


def _screenshot_url(url: str, out_path: Path) -> None:
    """Best-effort headless screenshot with quality guard.

    Notes:
    - X pages are JS-heavy + lazy-load images; without waiting, screenshots can be blank.
    - We use virtual-time-budget + compositor flush to give the page time to render.
    - After screenshot, we validate non-white ratio; if too low, we retry with a bigger budget.
    """

    out_path.parent.mkdir(parents=True, exist_ok=True)

    chrome_bin = os.environ.get("CHROME_PATH", "google-chrome-stable")

    def run_once(virtual_budget_ms: int) -> None:
        cmd = [
            chrome_bin,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            f"--virtual-time-budget={virtual_budget_ms}",
            "--run-all-compositor-stages-before-draw",
            "--force-device-scale-factor=2",
            "--window-size=1400,12000",
            f"--screenshot={out_path}",
            url,
        ]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"chrome screenshot failed: {url}\n{p.stderr.strip()}")

    # 1st try
    run_once(25000)

    # quality check + retry
    ratio = _image_nonwhite_ratio(out_path)
    # Empirically: blank-ish screenshots often end up <0.5% nonwhite.
    if ratio < 0.01:
        run_once(60000)
        ratio2 = _image_nonwhite_ratio(out_path)
        if ratio2 < ratio:
            # keep the newer file anyway; caller can decide.
            pass


def _extract_media_urls_fallback(tweet_url: str) -> list[str]:
    """Fallback when bird JSON lacks media.

    We fetch a text-rendered version of the tweet HTML via r.jina.ai
    and regex out pbs.twimg.com/media URLs.
    """

    mirror = "https://r.jina.ai/" + tweet_url
    try:
        html = _curl_text(mirror)
    except Exception:
        return []

    urls = re.findall(r"https://pbs\.twimg\.com/media/[A-Za-z0-9_-]+\.(?:jpg|jpeg|png|webp)", html)
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def fmt_tweet(t: dict, *, vault: Path, media_dir: Path, allow_fallback: bool = False) -> str:
    tid = t.get("id")
    author = (t.get("author") or {}).get("username") or "unknown"
    created = t.get("createdAt") or ""
    text = (t.get("text") or "").strip()
    url = f"https://x.com/{author}/status/{tid}" if tid and author != "unknown" else ""

    header = f"- @{author} ({created})"
    if url:
        header += f" {url}"

    lines: list[str] = [header]

    if text:
        lines.extend(["  " + ln for ln in text.splitlines()])

    # Media (photos)
    media_urls: list[str] = []

    media = t.get("media") or []
    photos = [m for m in media if (m.get("type") == "photo" and m.get("url"))]
    for m in photos:
        media_urls.append(str(m.get("url")))

    # Fallback: bird sometimes omits media; try HTML mirror
    # IMPORTANT: only do this for the main tweet to avoid N× network calls.
    if allow_fallback and (not media_urls) and url:
        media_urls = _extract_media_urls_fallback(url)

    for i, murl in enumerate(media_urls, start=1):
        ext = Path(murl.split("?")[0]).suffix or ".jpg"
        fname = f"{tid or 'tweet'}-{i}{ext}"
        local = media_dir / fname
        try:
            if not local.exists():
                _download(murl, local)
            rel = local.relative_to(vault).as_posix()
            lines.append(f"  ![]({rel})")
        except Exception:
            lines.append(f"  - media: {murl}")

    return "\n".join(lines)


def auto_direction(text: str) -> str:
    t = text.lower()
    # ---- tony server direction taxonomy (channel-like) ----
    if "polymarket" in t or "kalshi" in t:
        return "co-in/Polymarket"
    if "wise" in t or "支付" in text or "银行卡" in text or "卡" in text or "出入金" in text:
        return "co-in/支付与出入金"
    if any(k in t for k in ["btc", "bitcoin", "usdc", "usdt", "eth", "sol"] ) or "比特" in text:
        return "co-in/加密"
    if "stock" in t or any(k in text for k in ["a股", "美股", "财报", "港股"]):
        return "stock"
    if "arxiv" in t or "paper" in t or "论文" in text:
        return "paper"
    if any(k in t for k in ["mcp", "openclaw", "python", "docker", "k8s", "kubernetes", "cloudflare", "tunnel", "cloudflared", "ssh", "nginx", "vps"]):
        return "code"
    if any(k in text for k in ["写作", "文案", "短文", "随笔"]):
        return "words"
    return "Inbox"


def _cap_tags(tags: list[str], limit: int = 5) -> list[str]:
    out: list[str] = []
    for t in tags:
        t = t.strip()
        if not t or t in out:
            continue
        out.append(t)
        if len(out) >= limit:
            break
    return out


def summarize_text(main_text: str) -> tuple[str, str, list[str]]:
    """Return (tldr, keypoints_md, tags<=5). Rule-based, no LLM."""

    txt = main_text.strip()
    plain = re.sub(r"\s+", " ", txt)

    # TL;DR: 3-6 sentences
    sents = [s.strip() for s in re.split(r"(?<=[。！？.!?])\s+", plain) if s.strip()]
    tldr = " ".join(sents[:6]).strip() if sents else plain[:260].strip()

    # Key points: prefer explicit bullets/numbered lines
    kps: list[str] = []
    for line in txt.splitlines():
        s = line.strip()
        if re.match(r"^(\d+\)|\d+[、.]|[-*])\s+", s):
            s = re.sub(r"^(\d+\)|\d+[、.]|[-*])\s+", "", s).strip()
            if s and s not in kps:
                kps.append(s)

    if not kps:
        chunks = [c.strip() for c in re.split(r"[；;。]", plain) if c.strip()]
        kps = chunks[:12]

    keypoints_md = "\n".join([f"- {x}" for x in kps[:15]]) if kps else "- (Jarvis: 待生成)"

    # Tags: keep <=5 total
    low = plain.lower()
    tags = ["x"]
    tag_map = [
        ("openclaw", "openclaw"),
        ("clawdbot", "clawdbot"),
        ("polymarket", "polymarket"),
        ("kalshi", "kalshi"),
        ("arbitrage", "arbitrage"),
        ("套利", "arbitrage"),
        ("量化", "quant"),
        ("网格", "grid"),
        ("python", "python"),
        ("mcp", "mcp"),
        ("cloudflare", "cloudflare"),
        ("tunnel", "tunnel"),
        ("wise", "wise"),
        ("btc", "btc"),
        ("bitcoin", "btc"),
    ]
    for key, tag in tag_map:
        if key in low or key in plain:
            if tag not in tags:
                tags.append(tag)
        if len(tags) >= 5:
            break

    tags = _cap_tags(tags, 5)

    return tldr, keypoints_md, tags


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tweet")
    ap.add_argument("--vault", required=True)
    ap.add_argument("--direction", default="auto")  # default auto for new ingests
    ap.add_argument("--no-screenshot", action="store_true", help="Skip chrome screenshots (for X articles/tweets)")
    args = ap.parse_args()

    vault = Path(args.vault)
    base = vault / "knowledge"

    # Decide direction
    # If --direction=auto, classify from the main tweet text (best-effort)
    direction = args.direction

    # direction can be nested like "网络/内网穿透"; create nested folders.
    # (direction is finalized after fetching the thread)

    # placeholders; will be created after direction is finalized
    attach_dir = base / "Attachments" / "X"
    attach_dir.mkdir(parents=True, exist_ok=True)

    target_id = extract_id(args.tweet)

    raw = run(["bird", "thread", "--json", args.tweet])
    data = json.loads(raw)
    thread = data if isinstance(data, list) else data.get("thread") or []
    if not thread:
        raise RuntimeError("bird returned empty thread")

    main_tweet = pick_main_tweet(thread, target_id)

    # finalize direction
    if direction == "auto":
        direction = auto_direction((main_tweet or {}).get("text") or "")

    direction_path = Path(*[p for p in direction.split("/") if p])
    notes_dir = base / "Notes" / direction_path / "X"
    notes_dir.mkdir(parents=True, exist_ok=True)

    conv_id = str((main_tweet or {}).get("conversationId") or (main_tweet or {}).get("id") or (target_id or "unknown"))

    conv_dir = attach_dir / conv_id
    conv_dir.mkdir(parents=True, exist_ok=True)
    media_dir = conv_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    # Expanded links + article screenshot (best-effort)
    expanded_links: list[str] = []
    article_screenshot_rel: str | None = None
    main_text = (main_tweet or {}).get("text") or ""
    for u in re.findall(r"https?://t\.co/[A-Za-z0-9]+", main_text):
        final = _resolve_url(u)
        expanded_links.append(final)
        if args.no_screenshot:
            continue
        m = re.search(r"https://x\.com/i/article/(\d+)", final)
        if m and article_screenshot_rel is None:
            article_id = m.group(1)
            shot = conv_dir / f"article-{article_id}.png"
            try:
                _screenshot_url(final, shot)
                article_screenshot_rel = shot.relative_to(vault).as_posix()
            except Exception:
                article_screenshot_rel = None

    # If this is an X Article, bird may not expose embedded images reliably.
    # Fallback: screenshot the main tweet page (usually includes all inline images).
    def _crop_if_possible(p: Path) -> Path:
        """Crop screenshot to content area (remove sidebar/whitespace).

        Uses crop_screenshot.py-like heuristic; if PIL isn't available, returns original.
        """
        try:
            from PIL import Image

            Image.MAX_IMAGE_PIXELS = None
            img = Image.open(p).convert("RGB")
            w, h = img.size
            pix = img.load()

            step = 10
            thr_ratio = 0.02

            def nonwhite(px):
                r, g, b = px
                return r < 245 or g < 245 or b < 245

            def col_ratio(x: int) -> float:
                non = 0
                total = 0
                for y in range(0, h, step):
                    total += 1
                    if nonwhite(pix[x, y]):
                        non += 1
                return non / total

            def row_ratio(y: int) -> float:
                non = 0
                total = 0
                for x in range(0, w, step):
                    total += 1
                    if nonwhite(pix[x, y]):
                        non += 1
                return non / total

            left = 0
            for x in range(0, w, step):
                if col_ratio(x) > thr_ratio:
                    left = x
                    break
            right = w - 1
            for x in range(w - 1, 0, -step):
                if col_ratio(x) > thr_ratio:
                    right = x
                    break
            top = 0
            for y in range(0, h, step):
                if row_ratio(y) > thr_ratio:
                    top = y
                    break
            bottom = h - 1
            for y in range(h - 1, 0, -step):
                if row_ratio(y) > thr_ratio:
                    bottom = y
                    break

            # Guard: if we failed to find content (e.g. almost all-white), do not destroy the image.
            if (bottom - top) < 600:
                return p

            pad = 30
            left = max(0, left - pad)
            right = min(w - 1, right + pad)
            top = max(0, top - pad)
            bottom = min(h - 1, bottom + pad)

            cropped = img.crop((left, top, right + 1, bottom + 1))
            out = p.with_suffix("")
            out = out.parent / (out.name + ".article.png")
            cropped.save(out, optimize=True)
            return out
        except Exception:
            return p

    if (not args.no_screenshot) and (article_screenshot_rel is None) and (main_tweet or {}).get("article") and (main_tweet or {}).get("id"):
        # X Articles are the main place where images matter but API data may omit them.
        # To avoid missing important diagrams/screenshots, we ALWAYS capture a rendered screenshot.
        # (We already crop it to reduce whitespace.)
        tweet_url = f"https://x.com/{(main_tweet.get('author') or {}).get('username','')}/status/{main_tweet.get('id')}"

        shot = conv_dir / f"tweet-{main_tweet.get('id')}.png"
        try:
            _screenshot_url(tweet_url, shot)
            shot2 = _crop_if_possible(shot)
            article_screenshot_rel = shot2.relative_to(vault).as_posix()
        except Exception:
            article_screenshot_rel = None

    json_path = conv_dir / "thread.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    now = dt.datetime.now()
    today = now.strftime("%Y-%m-%d")

    title = (main_tweet or {}).get("text") or "X Thread"
    title_one_line = re.sub(r"\s+", " ", title).strip()[:80]

    # Idempotency: if we already ingested this conversation_id under this direction,
    # update that note instead of creating a new duplicate.
    existing = sorted(notes_dir.glob(f"*{conv_id}*.md"))
    if existing:
        note_path = existing[0]
    else:
        note_title = f"{today} - {slugify(title_one_line)}"
        note_path = notes_dir / f"{note_title}.md"

        # If the filename would be too long for ext4 (common max 255 bytes per segment),
        # fall back to a shorter, deterministic name.
        if len(note_path.name.encode("utf-8")) > 240:
            note_path = notes_dir / f"{today} - {conv_id}.md"

        if note_path.exists():
            alt = notes_dir / f"{note_title} ({conv_id}).md"
            if len(alt.name.encode("utf-8")) > 240:
                alt = notes_dir / f"{today} - {conv_id} ({target_id or 'tweet'}).md"
            note_path = alt

    md: list[str] = []
    md.append("---")
    md.append(f"source: {args.tweet}")
    md.append(f"saved_at: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    md.append("type: x")
    md.append(f"conversation_id: {conv_id}")
    if target_id:
        md.append(f"tweet_id: {target_id}")
    md.append(f"direction: {direction}")

    # One-pass summary generation (rule-based, no LLM)
    tldr, keypoints_md, tags = summarize_text((main_tweet or {}).get("text") or "")

    md.append(f"tags: [{', '.join(tags)}]")
    md.append(f"raw_json: {json_path.relative_to(vault)}")
    if expanded_links:
        md.append("expanded_links:")
        for u in expanded_links[:10]:
            md.append(f"  - {u}")
    if article_screenshot_rel:
        md.append(f"article_screenshot: {article_screenshot_rel}")
    md.append("---\n")

    md.append(f"# {title_one_line}\n")

    if article_screenshot_rel:
        md.append("## Article screenshot (best-effort)\n")
        md.append(f"![]({article_screenshot_rel})\n")

    md.append("## TL;DR\n")
    md.append(tldr + "\n")

    md.append("## Key points\n")
    md.append(keypoints_md + "\n")

    md.append("## Thread\n")
    main_id = str((main_tweet or {}).get("id") or "")
    for t in thread:
        allow_fb = str(t.get("id") or "") == main_id
        md.append(fmt_tweet(t, vault=vault, media_dir=media_dir, allow_fallback=allow_fb))
    md.append("\n")

    # If updating an existing note, merge in-place:
    # - keep existing content (e.g., manually edited TL;DR/key points)
    # - update frontmatter fields we own (raw_json, expanded_links, article_screenshot)
    # - ensure an embed for the article screenshot exists
    if note_path.exists():
        old = note_path.read_text(encoding="utf-8", errors="ignore")
        if old.lstrip().startswith("---"):
            # Split frontmatter
            parts = old.split("---", 2)
            if len(parts) >= 3:
                _pre, fm, body = parts[0], parts[1], parts[2]

                def parse_fm(text: str) -> list[str]:
                    return [ln.rstrip("\n") for ln in text.splitlines() if ln.strip() != ""]

                fm_lines = parse_fm(fm)

                def upsert_line(prefix: str, value_line: str) -> None:
                    for i, ln in enumerate(fm_lines):
                        if ln.startswith(prefix):
                            fm_lines[i] = value_line
                            return
                    fm_lines.append(value_line)

                upsert_line("source:", f"source: {args.tweet}")
                upsert_line("saved_at:", f"saved_at: {now.strftime('%Y-%m-%d %H:%M:%S')}")
                upsert_line("type:", "type: x")
                upsert_line("conversation_id:", f"conversation_id: {conv_id}")
                if target_id:
                    upsert_line("tweet_id:", f"tweet_id: {target_id}")
                upsert_line("direction:", f"direction: {direction}")
                upsert_line("tags:", f"tags: [{', '.join(tags)}]")
                upsert_line("raw_json:", f"raw_json: {json_path.relative_to(vault)}")
                # remove any existing expanded_links block; re-add below
                fm_lines = [ln for ln in fm_lines if not ln.startswith("expanded_links:") and not ln.startswith("  - ")]
                if expanded_links:
                    fm_lines.append("expanded_links:")
                    for u in expanded_links[:10]:
                        fm_lines.append(f"  - {u}")
                if article_screenshot_rel:
                    upsert_line("article_screenshot:", f"article_screenshot: {article_screenshot_rel}")

                new_fm = "\n".join(fm_lines)

                # Ensure screenshot embed exists (append if missing)
                if article_screenshot_rel and (article_screenshot_rel not in body):
                    body = body.rstrip() + "\n\n## Article screenshot (best-effort)\n\n![](" + article_screenshot_rel + ")\n"

                note_path.write_text("---\n" + new_fm + "\n---" + body, encoding="utf-8")
                print(str(note_path))
                return

    # Default: write full note
    note_path.write_text("\n".join(md), encoding="utf-8")
    print(str(note_path))


if __name__ == "__main__":
    main()
