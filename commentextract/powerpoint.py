from __future__ import annotations

from .models import Comment
from .ooxml import Package, attr, elements, local, text


def read_powerpoint(path, warnings):
    result = []
    with Package(path) as package:
        authors = {}
        for part in sorted(package.names):
            if part.startswith("ppt/") and part.endswith(".xml") and "author" in part.lower():
                for node in package.xml(part).iter():
                    if local(node.tag) in {"cmAuthor", "author"}:
                        authors[attr(node, "id")] = attr(node, "name")
        presentation = package.xml("ppt/presentation.xml")
        links = package.rels("ppt/presentation.xml")
        for number, slide in enumerate(elements(presentation, "sldId"), 1):
            rid = next((value for key, value in slide.attrib.items()
                        if key.startswith("{") and local(key) == "id"), "")
            if rid not in links:
                continue
            part = links[rid][1]
            for kind, target in package.rels(part).values():
                if kind.lower() not in {"comments", "comment"}:
                    continue
                root = package.xml(target)
                def collect(container, parent=None):
                    for node in container:
                        tag = local(node.tag)
                        if tag in {"cm", "reply"}:
                            cid = target + "#" + attr(node, "id", attr(node, "idx"))
                            body = next((n for n in node if local(n.tag) in {"text", "txBody"}), None)
                            content = text(body) if body is not None else ""
                            result.append(Comment(cid, authors.get(attr(node, "authorId"), ""), content,
                                                  parent, f"第 {number} 张幻灯片"))
                            for child in node:
                                if local(child.tag) == "replyLst":
                                    collect(child, cid)
                        elif tag in {"replyLst", "cmLst"}:
                            collect(node, parent)
                collect(root)
        if result:
            warnings.append("PPT 当前提供幻灯片编号；对象原文定位及幻灯片截图尚未支持。")
    return result
