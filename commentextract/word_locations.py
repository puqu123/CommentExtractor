"""Find searchable Word anchors without pretending to paginate a DOCX."""
import re

from .ooxml import attr, elements, local, text


def excerpt(value, length=48):
    value = re.sub(r"\s+", " ", value).strip()
    return value[:length] + ("…" if len(value) > length else "")


def is_toc_paragraph(paragraph):
    """Exclude Word-generated directory entries, not ordinary cross-references."""
    styles = elements(paragraph, "pStyle")
    style = attr(styles[0], "val") if styles else ""
    if re.fullmatch(r"(?:toc|目录)\s*[1-9]", style, re.I):
        return True
    return False


def paragraph_records(package, document, warnings=None):
    styles = {}
    if "word/styles.xml" in package.names:
        try:
            styles = {attr(s, "styleId"): s for s in elements(package.xml("word/styles.xml"), "style")}
        except Exception as exc:
            if warnings is not None:
                warnings.append(f"样式信息无法读取：{type(exc).__name__}：{exc}；批注保留，标题定位可能缺失。")

    def style_level(style_id, seen=None):
        seen = set() if seen is None else seen
        if style_id in seen or style_id not in styles:
            return None
        seen.add(style_id)
        node = styles[style_id]
        outlines = elements(node, "outlineLvl")
        if outlines and attr(outlines[0], "val").isdigit():
            return int(attr(outlines[0], "val"))
        names = elements(node, "name")
        name = attr(names[0], "val") if names else style_id
        match = re.fullmatch(r"(?:heading|标题)\s*([1-9])", name, re.I)
        if match:
            return int(match[1]) - 1
        if name.lower() in {"title", "标题"}:
            return 0
        based = elements(node, "basedOn")
        return style_level(attr(based[0], "val"), seen) if based else None

    headings = []
    records = []
    for paragraph in elements(document, "p"):
        value = text(paragraph)
        props = next((p for p in paragraph if local(p.tag) == "pPr"), None)
        level = None
        if props is not None:
            outline = elements(props, "outlineLvl")
            style = elements(props, "pStyle")
            if outline and attr(outline[0], "val").isdigit():
                level = int(attr(outline[0], "val"))
            elif style:
                level = style_level(attr(style[0], "val"))
        if level is not None and level < 9 and value:
            headings = [(n, title) for n, title in headings if n < level]
            headings.append((level, value))
        title = " / ".join(title for _, title in headings)
        records.append((paragraph, value, title, level))
    return records


def word_location(title, paragraph, selected="", label="正文"):
    search_value = next((line for line in (selected or paragraph).splitlines() if line.strip()), "")
    anchor = excerpt(search_value).rstrip("…")
    parts = [label]
    if title:
        parts.append(title)
    if anchor and anchor != excerpt(title):
        parts.append(f'搜索“{anchor}”')
    return " · ".join(parts) if len(parts) > 1 else label + " · 位置未确定"
