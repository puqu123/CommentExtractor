"""Explicit opt-in extraction of numbered review prose and its screenshots."""
from pathlib import Path
import re
import unicodedata
from difflib import SequenceMatcher

from .models import Comment, Screenshot, IMAGE_EXTENSIONS
from .ooxml import Package, attr, elements, local, text
from .word_locations import excerpt, paragraph_records, word_location, is_toc_paragraph

NUMBER = re.compile(r"^\s*(?:\d{1,3}[、．.](?!\d)|[（(]\d{1,3}[）)]|\d{1,3}[）)])\s*(.*)", re.S)
PAGE = re.compile(r"(?:第\s*(\d(?:[ \t]*\d){0,4})\s*页|\b(?:page|p\.)[ \t]*[:：]?[ \t]*(\d(?:[ \t]*\d){0,4})(?!\d)|(?:页码|页号)[ \t]*[:：]?[ \t]*(\d(?:[ \t]*\d){0,4})(?!\d))", re.I)
CAPTION = re.compile(r"^(?:图|表|figure|table)\s*\d+(?:[-.－]\d+)*(?:\s|[:：、]|[^\d\W]).*", re.I)
HEADING = re.compile(r"^(?:第[一二三四五六七八九十百\d]+[章节]|\d+(?:\.\d+){1,5}\s*)[^。；;]{1,120}$")


def normalize_ocr_line(value):
    value = unicodedata.normalize("NFKC", value).strip()
    value = re.sub(r"(?<=\d)\s*\.\s*(?=\d)", ".", value)
    value = re.sub(r"(?<=\d)\s*[一－–—-]\s*(?=\d)", "-", value)
    return re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", value)


def normalized(value):
    return re.sub(r"[\W_]+", "", normalize_ocr_line(value).casefold())


def explicit_location(value):
    lines = [unicodedata.normalize("NFKC", line).strip() for line in value.splitlines() if line.strip()]
    pages = list(dict.fromkeys(re.sub(r"\s", "", next(g for g in match.groups() if g))
                               for match in PAGE.finditer("\n".join(lines))))
    if pages:
        return "、".join("第 " + page + " 页" for page in pages)
    # OCR often inserts spaces between Chinese characters. Keep original content
    # elsewhere, only normalize candidate anchors for recognition.
    for pattern in (HEADING, CAPTION):
        found = [normalize_ocr_line(line) for line in lines if pattern.fullmatch(normalize_ocr_line(line))]
        if found:
            return "\n".join(line + "（待核对）" for line in dict.fromkeys(found))
    return ""


def reference_matches(value, reference):
    """Keep all substantial matches; resolve each image independently."""
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    needles = [normalized(line) for line in lines
               if len(normalized(line)) >= 8 and not PAGE.fullmatch(line.strip())]
    matches = []
    for paragraph, title, level in reference:
        candidate = normalized(paragraph)
        if len(candidate) >= 8 and any(n in candidate or candidate in n for n in needles):
            matches.append((paragraph, title, level))
    if matches:
        # A screenshot can contain both a section heading and its body. Keep
        # the body anchor so a heading's page does not masquerade as its page.
        matches = [record for record in matches if record[2] is None or not any(
            other[1] == record[1] and other[2] is None for other in matches)]
        return matches, False
    scored = []
    for record in reference:
        candidate = normalized(record[0])
        scores = [SequenceMatcher(None, needle, candidate, autojunk=False).ratio()
                  for needle in needles if min(len(needle), len(candidate)) >= 12
                  and min(len(needle), len(candidate)) / max(len(needle), len(candidate)) >= 0.6]
        if scores:
            scored.append((max(scores), record))
    scored.sort(key=lambda item: item[0], reverse=True)
    if scored and scored[0][0] >= 0.88:
        return [record for score, record in scored if score >= max(0.88, scored[0][0] - 0.03)], True
    return [], False


def reference_title_matches(value, reference):
    """Prioritize screenshot headings and figure/table captions over body text."""
    lines = [normalized(line) for line in value.splitlines() if len(normalized(line)) >= 6]
    titled = [record for record in reference if record[2] is not None or
              CAPTION.fullmatch(record[0].strip()) or HEADING.fullmatch(normalize_ocr_line(record[0]))]
    exact = []
    for record in titled:
        paragraph, title, _ = record
        candidates = [normalized(paragraph), normalized(title)]
        if any(candidate and any(line in candidate or candidate in line for line in lines)
               for candidate in candidates):
            exact.append(record)
    if exact:
        return list(dict.fromkeys(exact)), False
    scored = []
    for record in titled:
        paragraph, title, _ = record
        anchors = [normalized(paragraph), normalized(title)]
        for line in lines:
            for anchor in anchors:
                if len(anchor) < 6 or min(len(line), len(anchor)) / max(len(line), len(anchor)) < 0.55:
                    continue
                score = SequenceMatcher(None, line, anchor, autojunk=False).ratio()
                if score >= 0.78:
                    scored.append((score, record))
    if not scored:
        return [], False
    best = max(score for score, _ in scored)
    matches = list(dict.fromkeys(record for score, record in scored if score >= max(0.78, best - 0.025)))
    return matches, True


def anchor_title(paragraph, title):
    if CAPTION.fullmatch(paragraph.strip()):
        return paragraph.strip()
    if title:
        return title.split(" / ")[-1]
    return f'原文：“{excerpt(paragraph).rstrip("…")}”'


def match_reference(value, reference):
    matches, approximate = reference_matches(value, reference)
    if not matches:
        return "", ""
    lines = [anchor_title(paragraph, title) + ("（待核对）" if approximate else "")
             for paragraph, title, _ in matches]
    return "\n".join(dict.fromkeys(lines)), matches[0][0] if len(matches) == 1 else ""


def _numbered_paragraphs(package, document):
    """Identify top-level automatic decimal lists, including list styles."""
    styles = {}
    if "word/styles.xml" in package.names:
        styles = {attr(s, "styleId"): s for s in elements(package.xml("word/styles.xml"), "style")}
    numbering = package.xml("word/numbering.xml") if "word/numbering.xml" in package.names else None
    abstract = {attr(n, "abstractNumId"): n for n in elements(numbering, "abstractNum")} if numbering is not None else {}
    nums = {attr(n, "numId"): n for n in elements(numbering, "num")} if numbering is not None else {}

    def properties(paragraph):
        direct = elements(paragraph, "numPr")
        if direct:
            return direct[0]
        style = elements(paragraph, "pStyle")
        sid = attr(style[0], "val") if style else ""
        seen = set()
        while sid in styles and sid not in seen:
            seen.add(sid)
            direct = elements(styles[sid], "numPr")
            if direct:
                return direct[0]
            based = elements(styles[sid], "basedOn")
            sid = attr(based[0], "val") if based else ""
        return None

    result = set()
    for p in elements(document, "p"):
        props = properties(p)
        if props is None:
            continue
        ids, levels = elements(props, "numId"), elements(props, "ilvl")
        if not ids or (levels and attr(levels[0], "val") != "0"):
            continue
        num = nums.get(attr(ids[0], "val"))
        if num is None:
            continue
        aids = elements(num, "abstractNumId")
        definition = abstract.get(attr(aids[0], "val")) if aids else None
        if definition is None:
            continue
        level = next((n for n in elements(definition, "lvl") if attr(n, "ilvl") == "0"), None)
        formats = elements(level, "numFmt") if level is not None else []
        if formats and attr(formats[0], "val") != "bullet":
            result.add(id(p))
    return result


def read_developer_word(path, warnings, reviewer="", reference=None, ocr=True, ocr_backend="windows", ai=False):
    comments = []
    reference_records = []
    if reference:
        try:
            with Package(reference, warnings) as original:
                reference_records = [(value, title, level) for paragraph, value, title, level in
                                     paragraph_records(original, original.xml("word/document.xml"), warnings)
                                     if value and not is_toc_paragraph(paragraph)]
        except Exception as exc:
            warnings.append(f"原始文档无法读取：{type(exc).__name__}：{exc}；继续保留意见和截图。")
    with Package(path, warnings) as package:
        document = package.xml("word/document.xml")
        auto = _numbered_paragraphs(package, document)
        relationships = package.rels("word/document.xml")
        current = None
        before = []
        image_number = 0
        for paragraph in elements(document, "p"):
            value = text(paragraph)
            marker = NUMBER.match(unicodedata.normalize("NFKC", value))
            # Nested automatic lists stay inside the current review item.
            if marker or id(paragraph) in auto:
                current = Comment("developer#" + str(len(comments) + 1), reviewer, "")
                comments.append(current)
            if current is None:
                if value:
                    before.append(value)
            elif value:
                current.text += ("\n" if current.text else "") + value
            for node in paragraph.iter():
                if local(node.tag) not in {"blip", "imagedata"}:
                    continue
                rid = attr(node, "embed") or attr(node, "id")
                relation = relationships.get(rid)
                if not relation or relation[0] != "image":
                    warnings.append("发现外部或无法解析的图片引用，未联网读取；请对照源评审文档核对。")
                    continue
                if current is None:
                    # An image before any numbered item must not be silently
                    # assigned to item 1. Export a clearly flagged separate row.
                    current = Comment("developer#preface", reviewer, "未编号内容（需核对）\n" + "\n".join(before))
                    before = []
                    comments.append(current)
                try:
                    target = relation[1]
                    image_number += 1
                    extension = Path(target).suffix.lower()
                    if extension not in IMAGE_EXTENSIONS:
                        extension = ".bin"
                        warnings.append(f"图片部件 {target} 格式不支持预览，按原始字节保存为 .bin 附件。")
                    image = Screenshot(f"截图_{image_number:03d}" + extension, package.zip.read(target))
                    current.screenshots.append(image)
                except Exception as exc:
                    warnings.append(f"图片无法读取 {relation[1]}：{type(exc).__name__}：{exc}；意见文字仍保留。")
        if before:
            warnings.append("首条编号前的说明（未计为意见）：\n" + "\n".join(before))
        if not comments:
            raise ValueError("未找到编号意见。请使用 1、/1./1）或 Word 顶层自动编号，每条意见从新段落开始。")
    images = [image for comment in comments for image in comment.screenshots]
    if ocr:
        from .ocr import recognize_images, recognize_images_rapid
        try:
            (recognize_images_rapid if ocr_backend == "rapidocr" else recognize_images)(images, warnings)
        except Exception as exc:
            warnings.append(f"截图识别失败：{type(exc).__name__}：{exc}；意见和原图仍保留。")
    ai_settings = {}
    if ai:
        from .model_settings import load_settings
        ai_settings = load_settings(include_key=True)
        if not ai_settings.get("key"):
            warnings.append("AI 辅助定位不可用：无法读取模型配置或密钥，已保留本地定位结果。")
        elif not reference_records:
            warnings.append("AI 辅助定位需要可读取的原手册；已保留意见和截图。")
    for index, comment in enumerate(comments, 1):
        matched_contexts = []
        seen_anchors = set()
        for image in comment.screenshots:
            # Evidence priority: explicit page printed in the screenshot,
            # then a visible heading/caption, then ordinary body-text matches.
            screenshot_page = explicit_location(image.ocr_text)
            title_matches, title_approximate = reference_title_matches(image.ocr_text, reference_records)
            matches, approximate = (title_matches, title_approximate) if title_matches else reference_matches(
                image.ocr_text, reference_records)
            if ai_settings.get("key") and reference_records:
                from .model_api import select_candidates, recognize_image
                from .progress import stage
                stage(75, "AI 辅助定位截图")
                try:
                    query = image.ocr_text
                    if not query and ai_settings.get("vision", True):
                        query = recognize_image(ai_settings, image)
                        image.ocr_text = query
                    selected = select_candidates(ai_settings, image, query or comment.text, reference_records)
                    if selected and not title_matches:
                        # Reused identical text can appear in other sections. Never
                        # silently discard those locations even if the model picks one.
                        selected_texts = {normalized(record[0]) for record in selected}
                        matches = [record for record in reference_records if normalized(record[0]) in selected_texts]
                        approximate = True
                    elif selected == []:
                        warnings.append("AI 未确认截图位置，保留本地匹配结果，请核对。")
                    else:
                        warnings.append("AI 定位没有足够的原文候选，保留本地匹配结果，请核对。")
                except Exception as exc:
                    reason = str(exc) if isinstance(exc, RuntimeError) else "模型服务调用失败"
                    warnings.append("AI 辅助定位失败：" + reason + "；已保留本地定位结果。")
            visible_page = screenshot_page or explicit_location(image.ocr_text)
            # A screenshot can contain a printed page number alongside several
            # matched paragraphs. Preserve that evidence for every anchor in it.
            visible_page = visible_page if visible_page.startswith("第 ") else ""
            for paragraph, title, _ in matches:
                key = (paragraph, title, approximate)
                if key not in seen_anchors:
                    comment.location_anchors.append({"paragraph": paragraph, "title": title,
                                                     "approximate": approximate, "visible_page": visible_page})
                    matched_contexts.append(paragraph)
                    seen_anchors.add(key)
                elif visible_page:
                    for anchor in comment.location_anchors:
                        if (anchor["paragraph"], anchor["title"], anchor["approximate"]) == key and not anchor.get("visible_page"):
                            anchor["visible_page"] = visible_page
        ocr_text = "\n".join(image.ocr_text for image in comment.screenshots if image.ocr_text)
        if comment.location_anchors:
            from .word_layout import developer_pages
            comment.location = developer_pages(comment.location_anchors, [])
        else:
            comment.location = explicit_location(ocr_text) or explicit_location(comment.text)
            if comment.location and ocr_text and "待核对" not in comment.location:
                comment.location += "（截图识别，待核对）"
            if not comment.location and ocr_text:
                comment.location = f'原文搜索“{excerpt(ocr_text).rstrip("…")}”（待核对）'
            if not comment.location:
                comment.location = "未定位" + ("（见截图）" if comment.screenshots else "")
        matched_context = "\n".join(dict.fromkeys(matched_contexts))
        sections = []
        if matched_context:
            sections.append("匹配到的原文：\n" + matched_context)
        if ocr_text:
            sections.append("截图文字识别（请核对原图）：\n" + ocr_text)
        comment.context = "\n\n".join(sections)
    warnings.append("开发评审按顶层编号归组，文字和截图均保留；未自动区分正文中的回复，请核对分条及位置。")
    if not reviewer:
        warnings.append("开发评审未指定评审人，姓名留空；不使用文档作者或最后修改人推断评审人。")
    return comments
