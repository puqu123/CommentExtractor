from __future__ import annotations

from .models import Comment, Screenshot, IMAGE_EXTENSIONS
from .ooxml import Package, attr, elements, local, text
from .word_locations import paragraph_records, word_location


def read_word(path, warnings):
    comments = []
    with Package(path, warnings) as package:
        parts = [n for n in package.names if n.startswith("word/") and n.endswith(".xml")
                 and "/" not in n[len("word/"):]
                 and (n == "word/document.xml" or n.rsplit("/", 1)[-1].startswith(
                     ("header", "footer", "footnotes", "endnotes")))]
        parts.sort(key=lambda p: (p != "word/document.xml", p))
        comment_parts = {}
        for part in parts:
            for kind, target in package.rels(part).values():
                if kind == "comments":
                    comment_parts.setdefault(target, []).append(part)
        if not comment_parts and "word/comments.xml" in package.names:
            comment_parts["word/comments.xml"] = parts
        for comment_part, documents in comment_parts.items():
            prefix = comment_part + "#"
            nodes = elements(package.xml(comment_part), "comment")
            image_relationships = package.rels(comment_part)
            para_to_id = {}
            for node in nodes:
                # Word identifies a comment via the paraId of its last paragraph.
                for paragraph in elements(node, "p"):
                    if attr(paragraph, "paraId"):
                        para_to_id[attr(paragraph, "paraId")] = attr(node, "id")
            parents = {}
            extended = comment_part.rsplit("/", 1)[0] + "/commentsExtended.xml"
            for kind, target in package.rels("word/document.xml").values():
                if kind == "commentsExtended":
                    extended = target
            if extended in package.names:
                try:
                    for node in elements(package.xml(extended), "commentEx"):
                        child = para_to_id.get(attr(node, "paraId"))
                        parent = para_to_id.get(attr(node, "paraIdParent"))
                        if child is not None and parent is not None:
                            parents[child] = parent
                except Exception as exc:
                    warnings.append(f"回复关系信息无法读取：{type(exc).__name__}：{exc}；全部批注文字按独立意见保留，请核对回复归属。")
            anchors = {}
            for part in documents:
                try:
                    document = package.xml(part)
                except Exception as exc:
                    warnings.append(f"原文定位信息无法读取 {part}：{type(exc).__name__}：{exc}；批注文字继续保留，位置待核对。")
                    continue
                active = {}
                locations = {}
                paragraph_text, heading = "", ""
                records = {id(p): (value, title) for p, value, title, _ in paragraph_records(package, document, warnings)}
                label = "正文" if part == "word/document.xml" else part.rsplit("/", 1)[-1]
                for node in document.iter():
                    tag = local(node.tag)
                    if tag == "p":
                        paragraph_text, heading = records.get(id(node), ("", ""))
                        for value in active.values():
                            value.append("\n")
                    if tag == "commentRangeStart":
                        cid = attr(node, "id")
                        active[cid] = []
                        locations[cid] = (heading, paragraph_text)
                    elif tag == "commentRangeEnd":
                        cid = attr(node, "id")
                        if cid in active:
                            context = "".join(active.pop(cid)).strip()
                            title, paragraph_value = locations[cid]
                            anchors[cid] = (word_location(title, paragraph_value, context, label), context)
                    elif tag == "commentReference":
                        anchors.setdefault(attr(node, "id"), (word_location(heading, paragraph_text, label=label), ""))
                    elif tag in {"t", "tab", "br", "cr"}:
                        value = (node.text or "") if tag == "t" else ("\t" if tag == "tab" else "\n")
                        for buffer in active.values():
                            buffer.append(value)
            for node in nodes:
                cid = attr(node, "id")
                location, context = anchors.get(cid, ("位置未记录", ""))
                pictures = []
                for image in node.iter():
                    if local(image.tag) not in {"blip", "imagedata"}:
                        continue
                    relation = image_relationships.get(attr(image, "embed") or attr(image, "id"))
                    if relation and relation[0] == "image":
                        from pathlib import Path
                        extension = Path(relation[1]).suffix.lower()
                        try:
                            pictures.append(Screenshot(f"批注截图_{len(pictures) + 1}" + (extension if extension in IMAGE_EXTENSIONS else ".bin"), package.zip.read(relation[1])))
                        except Exception:
                            warnings.append("批注图片无法读取，已保留可读文字。")
                    else:
                        warnings.append("批注图片引用无法解析，已保留可读文字，请核对原图。")
                comments.append(Comment(prefix + cid, attr(node, "author"), text(node),
                                        prefix + parents[cid] if cid in parents else None,
                                        location, context, pictures))
    return comments
