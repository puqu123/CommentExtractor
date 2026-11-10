"""Optional read-only Word automation, using only a private temporary copy."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import re
from difflib import SequenceMatcher


def read_layout(source, convert=False, include_comments=False, copy_input=True):
    script = Path(__file__).with_name("assets") / "word_layout.ps1"
    with tempfile.TemporaryDirectory(prefix="CommentExtractor-word-") as folder:
        folder = Path(folder)
        copy = folder / ("input" + Path(source).suffix)
        input_path = copy if copy_input else Path(source).resolve()
        if copy_input:
            shutil.copyfile(source, copy)
        result = folder / "layout.json"
        converted = folder / "converted.docx"
        environment = os.environ.copy()
        environment.update(CE_WORD_INPUT=str(input_path), CE_WORD_OUTPUT=str(result), CE_WORD_CONVERT=str(converted) if convert else "")
        environment["CE_WORD_COMMENTS"] = "1" if include_comments else "0"
        command = "& {\n" + script.read_text(encoding="utf-8") + "\n} -InputFile $env:CE_WORD_INPUT -OutputFile $env:CE_WORD_OUTPUT -ConvertedFile $env:CE_WORD_CONVERT -IncludeComments:($env:CE_WORD_COMMENTS -eq '1')"
        shell = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        try:
            subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-Command", command], env=environment,
                           capture_output=True, timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=True)
        except (OSError, subprocess.SubprocessError) as exc:
            detail = "请确认本机 Microsoft Word 可正常打开该文件。"
            if isinstance(exc, subprocess.TimeoutExpired):
                detail = "Word 操作超时，请检查是否有隐藏的 Word 提示窗口。"
            elif isinstance(exc, subprocess.CalledProcessError):
                error = (exc.stderr or b"").decode("utf-8", errors="ignore") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
                open_message = ("Word 无法打开原始文件（只读）；请确认文件可在 Word 中打开。"
                                if not copy_input else "Word 无法打开文件副本，请检查文件是否加密、受保护或损坏。")
                for marker, message in [("WORD_START", "无法启动 Microsoft Word，请检查是否安装且可正常打开。"),
                                        ("OPEN", open_message),
                                        ("CONVERT", "Word 打开了文件，但另存为 .docx 未完成。"),
                                        ("LAYOUT", "Word 打开了文件，但读取排版页码未完成。")]:
                    if "CE_WORD_STAGE=" + marker in error:
                        detail = message
                        break
            raise RuntimeError("Microsoft Word 转换或页码读取未完成。" + detail) from exc
        try:
            payload = json.loads(result.read_text(encoding="utf-8-sig"))
            if isinstance(payload, dict):
                paragraphs = payload.get("paragraphs", [])
                comments = payload.get("comments", [])
            else:  # Older script output, retained for compatibility with cached environments.
                paragraphs, comments = payload, []
            if not isinstance(paragraphs, list):
                raise ValueError("排版结果格式无效")
        except (OSError, ValueError, UnicodeError) as exc:
            # A page lookup is optional. If a legacy file was already converted,
            # keep that converted copy so comment extraction can continue.
            if convert and converted.is_file():
                return ([], converted.read_bytes(), []) if include_comments else ([], converted.read_bytes())
            raise RuntimeError("Microsoft Word 未返回有效的页码结果；已保留批注提取。") from exc
        result = (paragraphs, converted.read_bytes() if convert else None)
        return result + (comments if isinstance(comments, list) else [],) if include_comments else result


def add_pages(location, context, paragraphs):
    # Never infer pages by counting XML paragraphs or page breaks.
    from .developer_word import normalized
    needles = [normalized(line) for line in context.splitlines() if len(normalized(line)) >= 8]
    lines = []
    for line in location.splitlines():
        if re.search(r"第\s*\d+\s*页", line):
            lines.append(line)
            continue
        if "位置未确定" in line or "位置未记录" in line:
            lines.append(line)
            continue
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


def apply_word_comment_positions(comments, word_comments):
    """Use Word's actual comment scope/page when it can be paired unambiguously."""
    from .developer_word import normalized

    available = list(word_comments)
    for comment in comments:
        body = normalized(comment.text)
        author = normalized(comment.author)
        scope = normalized(comment.context)
        # The selected text is the strongest stable key across OOXML and Word.
        # Comment bodies/authors can be rewritten by WPS or differ for replies.
        candidates = [item for item in available if scope and normalized(item.get("scope", "")) == scope]
        if len(candidates) > 1:
            same_body = [item for item in candidates if body and normalized(item.get("text", "")) == body]
            if same_body:
                candidates = same_body
        if len(candidates) > 1 and author:
            same_author = [item for item in candidates if normalized(item.get("author", "")) == author]
            if same_author:
                candidates = same_author
        if len(candidates) != 1:
            candidates = [item for item in available
                          if body and normalized(item.get("text", "")) == body and
                          (not author or not item.get("author") or normalized(item.get("author", "")) == author)]
        if len(candidates) != 1 and body and scope:
            candidates = [item for item in available
                          if normalized(item.get("text", "")) == body and normalized(item.get("scope", "")) == scope]
        if len(candidates) != 1:
            continue
        item = candidates[0]
        available.remove(item)
        scope_text = item.get("scope", "").strip()
        heading = (item.get("heading", "") or "").strip()
        parts = [comment.location.split(" · ", 1)[0] if comment.location else "正文"]
        if heading and heading not in parts:
            parts.append(heading)
        excerpt = re.search(r'搜索“([^”]+)”', comment.location)
        if scope_text:
            quote = re.sub(r"\s+", " ", scope_text).strip()[:48]
            if len(re.sub(r"\s+", " ", scope_text).strip()) > 48:
                quote += "…"
        else:
            quote = excerpt.group(1) if excerpt else ""
        if quote:
            parts.append(f'搜索“{quote}”')
        start_page, end_page = item.get("start_page"), item.get("end_page")
        try:
            start_page, end_page = int(start_page), int(end_page)
        except (TypeError, ValueError):
            start_page = end_page = 0
        if start_page > 0:
            page = f"第 {start_page} 页" if end_page <= start_page else f"第 {start_page}–{end_page} 页"
            comment.location = " · ".join(parts) + f"（{page}）"
        else:
            comment.location = " · ".join(parts)
    return comments


def developer_pages(anchors, paragraphs):
    """Attach actual layout pages and the nearest usable heading to anchors."""
    from .developer_word import normalized, anchor_title, CAPTION
    locations = {}
    visible_pages = {}
    for anchor in anchors:
        paragraph = anchor["paragraph"]
        title = anchor["title"].split(" / ")[-1] if anchor["title"] else ""
        target = normalized(paragraph)
        exact = [p for p in paragraphs if normalized(p.get("text", "")) == target]
        candidates = exact
        if not candidates and len(target) >= 32:
            # Word's COM text can differ slightly from the OOXML paragraph
            # (field markers, cell endings, or line breaks). Allow only a
            # close, substantial match; never choose a weak nearest paragraph.
            scored = []
            for item in paragraphs:
                value = normalized(item.get("text", ""))
                if len(value) < 32:
                    continue
                shorter, longer = sorted((len(target), len(value)))
                if shorter / longer < 0.65:
                    continue
                ratio = SequenceMatcher(None, target, value, autojunk=False).ratio()
                if ratio >= 0.84:
                    scored.append((ratio, item))
            if scored:
                best = max(score for score, _ in scored)
                candidates = [item for score, item in scored if score >= max(0.84, best - 0.015)]
        scoped = []
        if title:
            scoped = [p for p in candidates if p.get("heading") and
                      normalized(title) in normalized(p["heading"])]
            # A unique exact paragraph can be located even when Word's heading
            # style is unavailable; ambiguous matches must not be guessed.
            candidates = scoped or (candidates if len(candidates) == 1 else [])
        # Prefer the heading reported by Word itself. OOXML styles are often
        # missing on real manuals even when numbered section headings are clear.
        layout_headings = list(dict.fromkeys(p.get("heading", "") for p in candidates if p.get("heading")))
        if scoped and title and not CAPTION.fullmatch(paragraph.strip()):
            labels = [scoped[0].get("heading") or anchor_title(paragraph, anchor["title"])]
        elif layout_headings and not CAPTION.fullmatch(paragraph.strip()):
            labels = layout_headings
        else:
            labels = [anchor_title(paragraph, anchor["title"])]
        if anchor.get("approximate"):
            labels = [label + "（待核对）" for label in labels]
        for label in labels:
            pages = locations.setdefault(label, set())
            if anchor.get("visible_page"):
                visible_pages.setdefault(label, set()).add(anchor["visible_page"])
            for p in candidates:
                if len(labels) > 1 and p.get("heading") != label.removesuffix("（待核对）"):
                    continue
                pages.update(range(int(p.get("page", 0)), int(p.get("end_page", p.get("page", 0))) + 1))
    rendered = []
    for label, pages in locations.items():
        if label in visible_pages:
            visible = sorted(visible_pages[label], key=lambda value: int(re.search(r"\d+", value).group()))
            rendered.append("、".join(visible) + " · " + label)
        elif any(page > 0 for page in pages):
            rendered.append(label + "（第 " + "、".join(map(str, sorted(page for page in pages if page > 0))) + " 页）")
        else:
            rendered.append(label)
    return "\n".join(rendered)
