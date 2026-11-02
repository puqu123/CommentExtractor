from __future__ import annotations

from .models import Comment
from .ooxml import Package, attr, elements, local, text


def read_word(path, warnings):
    comments = []
    with Package(path) as package:
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
                for node in elements(package.xml(extended), "commentEx"):
                    child = para_to_id.get(attr(node, "paraId"))
                    parent = para_to_id.get(attr(node, "paraIdParent"))
                    if child is not None and parent is not None:
                        parents[child] = parent
            anchors = {}
            for part in documents:
                document = package.xml(part)
                active = {}
                locations = {}
                paragraph = 0
                label = "正文" if part == "word/document.xml" else part.rsplit("/", 1)[-1]
                for node in document.iter():
                    tag = local(node.tag)
                    if tag == "p":
                        paragraph += 1
                        for value in active.values():
                            value.append("\n")
                    if tag == "commentRangeStart":
                        cid = attr(node, "id")
                        active[cid] = []
                        locations[cid] = f"{label} · 第 {paragraph} 段"
                    elif tag == "commentRangeEnd":
                        cid = attr(node, "id")
                        if cid in active:
                            anchors[cid] = (locations[cid], "".join(active.pop(cid)).strip())
                    elif tag == "commentReference":
                        anchors.setdefault(attr(node, "id"), (f"{label} · 第 {paragraph} 段", ""))
                    elif tag in {"t", "tab", "br", "cr"}:
                        value = (node.text or "") if tag == "t" else ("\t" if tag == "tab" else "\n")
                        for buffer in active.values():
                            buffer.append(value)
            for node in nodes:
                cid = attr(node, "id")
                location, context = anchors.get(cid, ("位置未记录", ""))
                comments.append(Comment(prefix + cid, attr(node, "author"), text(node),
                                        prefix + parents[cid] if cid in parents else None,
                                        location, context))
    return comments
