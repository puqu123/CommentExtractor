"""Optional read-only Word automation, using only a private temporary copy."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import re


def read_layout(source, convert=False):
    script = Path(__file__).with_name("assets") / "word_layout.ps1"
    with tempfile.TemporaryDirectory(prefix="CommentExtractor-word-") as folder:
        folder = Path(folder)
        copy = folder / ("input" + Path(source).suffix)
        shutil.copyfile(source, copy)
        result = folder / "layout.json"
        converted = folder / "converted.docx"
        environment = os.environ.copy()
        environment.update(CE_WORD_INPUT=str(copy), CE_WORD_OUTPUT=str(result), CE_WORD_CONVERT=str(converted) if convert else "")
        command = "& {\n" + script.read_text(encoding="utf-8") + "\n} -InputFile $env:CE_WORD_INPUT -OutputFile $env:CE_WORD_OUTPUT -ConvertedFile $env:CE_WORD_CONVERT"
        shell = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        try:
            subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-Command", command], env=environment,
                           capture_output=True, timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=True)
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError("需要本机已安装且可正常使用的 Microsoft Word；转换或页码读取未完成。") from exc
        return json.loads(result.read_text(encoding="utf-8-sig")), converted.read_bytes() if convert else None


def add_pages(location, context, paragraphs):
    # Never infer pages by counting XML paragraphs or page breaks.
    from .developer_word import normalized
    needles = [normalized(line) for line in context.splitlines() if len(normalized(line)) >= 8]
    lines = []
    for line in location.splitlines():
        if "截图 OCR" in line and "页" in line:
            lines.append(line)
            continue
        quote = re.search('搜索“([^”]+)”', line)
        terms = [normalized(quote.group(1))] if quote else needles
        candidates = [p for p in paragraphs if normalized(p["text"]) and any(
            n and (n in normalized(p["text"]) or normalized(p["text"]) in n) for n in terms)]
        if not candidates:
            candidates = [p for p in paragraphs if normalized(p["text"]) and normalized(p["text"]) in normalized(line)
                          and p.get("heading") == p["text"]]
        same_heading = [p for p in candidates if p.get("heading") and normalized(p["heading"]) in normalized(line)]
        pages = sorted({page for p in (same_heading or candidates)
                        for page in range(int(p["page"]), int(p.get("end_page", p["page"])) + 1) if page > 0})
        lines.append(line + ("（第 " + "、".join(map(str, pages)) + " 页）" if pages else "（页码未获取）"))
    return "\n".join(lines)


def developer_pages(anchors, paragraphs):
    """Attach actual layout pages to the same matched paragraph and section."""
    from .developer_word import normalized, anchor_title, CAPTION
    locations = {}
    visible_pages = {}
    for anchor in anchors:
        paragraph = anchor["paragraph"]
        title = anchor["title"].split(" / ")[-1] if anchor["title"] else ""
        candidates = [p for p in paragraphs if normalized(p["text"]) == normalized(paragraph)]
        if title:
            candidates = [p for p in candidates if p.get("heading") and
                          normalized(title) in normalized(p["heading"])]
        label = anchor_title(paragraph, anchor["title"])
        if candidates and title and not CAPTION.fullmatch(paragraph.strip()):
            label = candidates[0].get("heading") or label
        if anchor.get("approximate"):
            label += "（相似匹配，待核对）"
        pages = locations.setdefault(label, set())
        if anchor.get("visible_page"):
            visible_pages.setdefault(label, set()).add(anchor["visible_page"])
        for p in candidates:
            pages.update(range(int(p["page"]), int(p.get("end_page", p["page"])) + 1))
    return "\n".join(label + ("（第 " + "、".join(map(str, sorted(p for p in pages if p > 0))) + " 页）"
                               if any(p > 0 for p in pages) else
                               ("（截图识别：" + "、".join(sorted(visible_pages[label])) + "，待核对）"
                                if label in visible_pages else "（页码未获取）"))
                     for label, pages in locations.items())
