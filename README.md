# knowledge-vault（OpenClaw Skill）

> 面向 Obsidian 的“知识入库 + 按方向检索汇总”工作流。支持 Web / X / PDF 入库，产出结构化 Markdown 笔记与附件归档。

## 这个 skill 是干嘛的

`knowledge-vault` 用来把外部信息（网页、X 推文线程、本地 PDF）统一沉淀到 Obsidian vault 的 `knowledge/` 目录下，并强制写出可复用的结构化笔记（含 YAML frontmatter、TL;DR、Key points、tags、direction）。

核心能力：
- 入库：Web / X / PDF
- 归档：原始数据放 `knowledge/Attachments/...`
- 产出：规范笔记放 `knowledge/Notes/<direction>/...`
- 检索：可按 `direction` 做聚合读取与总结

---

## 安装 / 前置条件

### 1) OpenClaw
- 建议：OpenClaw 新版本（支持 skills 与 tool 调用）
- 将本仓库放到你的 skills 目录（或按你的 OpenClaw 配置加载）

### 2) 运行环境
- Python 3.10+
- `curl`
- 可选（按场景）：
  - `bird`（X 线程抓取）
  - `google-chrome-stable`（X 页面截图）
  - `pdftotext`（PDF 文本提取，通常来自 `poppler-utils`）

### 3) Python 依赖
```bash
pip install -r requirements.txt
```

---

## 配置（务必用环境变量，不要把 key 写进仓库）

### 必填参数（CLI）
- `--vault "/path/to/your/obsidian-vault"`

> 这里请使用你自己的 Obsidian vault 路径占位符，不要提交任何个人绝对路径到仓库。

### 可选环境变量
- `CHROME_PATH`：Chrome 可执行路径（默认 `google-chrome-stable`）

示例：
```bash
export CHROME_PATH="/usr/bin/google-chrome-stable"
```

### 安全建议
- 不要在仓库内写入：API Key、Token、Cookie、CT0、邮箱、账号、个人目录绝对路径。
- 如果你需要私有配置，请放在本地 `.env` 或 shell profile，并确保 `.gitignore` 忽略。

---

## 使用示例

## 1) 入库 Web
```bash
python3 scripts/ingest_web.py "https://example.com/article" \
  --vault "/path/to/your/obsidian-vault" \
  --direction auto \
  --title "示例文章" \
  --tags "web,reading" \
  --tldr "一句话总结" \
  --keypoints-file /tmp/keypoints.txt \
  --extracted-md-file /tmp/extracted.md
```

## 2) 入库 X（推文线程）
```bash
python3 scripts/ingest_x.py "https://x.com/<user>/status/<id>" \
  --vault "/path/to/your/obsidian-vault" \
  --direction auto
```

跳过截图：
```bash
python3 scripts/ingest_x.py "https://x.com/<user>/status/<id>" \
  --vault "/path/to/your/obsidian-vault" \
  --direction auto \
  --no-screenshot
```

## 3) 入库 PDF
```bash
python3 scripts/ingest_pdf.py "/path/to/doc.pdf" \
  --vault "/path/to/your/obsidian-vault" \
  --direction Inbox
```

---

## 输出目录结构

在你的 vault 下会生成：
- `knowledge/Notes/<direction>/{Web|X|PDF}/...`（规范笔记）
- `knowledge/Attachments/{Web|X|PDF}/...`（原始附件）

---

## 常见问题 / 排错

1. **X 入库报错：`bird` not found**  
   - 说明未安装或不在 PATH。安装并确保命令行可直接执行 `bird`。

2. **X 截图失败**  
   - 检查 `google-chrome-stable` 是否可用。必要时设置 `CHROME_PATH`。
   - 某些页面会懒加载，已内置重试；仍失败可先 `--no-screenshot`。

3. **PDF 入库失败：`pdftotext` not found**  
   - 安装 `poppler-utils` 后重试。

4. **笔记里出现占位符“待生成”**  
   - 说明未传入完整摘要参数（常见于 Web/PDF 流程）；请补充 `--tldr` 和 `--keypoints-file`。

5. **方向分流不符合预期**  
   - `--direction auto` 是启发式规则。可直接显式传 `--direction "你的方向"` 覆盖。

---

## License

本仓库使用 **MIT License**（已包含 `LICENSE` 文件）。
