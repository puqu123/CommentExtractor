from __future__ import annotations

from .models import Comment
from .ooxml import Package, attr, elements, local, text


def read_powerpoint(path, warnings):
    """Read independent parts separately; preserve recoverable comments verbatim."""
    result, failures = [], []
    with Package(path, warnings) as package:
        authors = {}
        try:
            presentation_links = package.rels("ppt/presentation.xml")
        except Exception:
            presentation_links = {}  # Detailed recovery warning is produced below.
        author_parts = {target for kind, target in presentation_links.values() if kind.lower() in {"authors", "commentauthors"}}
        author_parts.update(part for part in package.names if part.startswith("ppt/") and part.endswith(".xml") and "author" in part.lower())
        for part in sorted(author_parts):
            if part in package.names:
                try:
                    for node in package.xml(part).iter():
                        if local(node.tag) in {"cmAuthor", "author"}:
                            authors[attr(node, "id")] = attr(node, "name")
                except Exception as exc:
                    warnings.append(f"作者表无法读取 {part}：{type(exc).__name__}：{exc}；未识别的姓名留空。")
        mapped = {}
        try:
            presentation = package.xml("ppt/presentation.xml")
            links = package.rels("ppt/presentation.xml")
            for number, slide in enumerate(elements(presentation, "sldId"), 1):
                rid = next((value for key, value in slide.attrib.items()
                            if key.startswith("{") and local(key) == "id"), "")
                if rid not in links:
                    warnings.append(f"第 {number} 张幻灯片缺少关系，改为扫描批注部件。")
                    continue
                part = links[rid][1]
                try:
                    for kind, target in package.rels(part).values():
                        if kind.lower() in {"comments", "comment"}:
                            mapped.setdefault(target, f"第 {number} 张幻灯片")
                except Exception as exc:
                    failures.append(f"{part} 关系：{type(exc).__name__}：{exc}")
        except Exception as exc:
            failures.append(f"幻灯片顺序：{type(exc).__name__}：{exc}")
        for part in sorted(package.names):
            if part.startswith("ppt/comments/") and part.endswith(".xml") and part not in mapped:
                mapped[part] = "幻灯片位置未确定"
                warnings.append(f"发现未关联的批注部件 {part}，内容保留，幻灯片编号不推测。")
        for target, location in mapped.items():
            try:
                root = package.xml(target)
                if local(root.tag) != "cmLst":
                    raise ValueError("无法识别的批注列表结构")
                def collect(container, parent=None):
                    for node in container:
                        tag = local(node.tag)
                        if tag in {"cm", "reply"}:
                            # Classic idx is unique per author, not per slide.
                            key = attr(node, "id") or (attr(node, "authorId") + ":" + attr(node, "idx"))
                            cid = target + "#" + key
                            body = next((n for n in node if local(n.tag) in {"text", "txBody"}), None)
                            content = text(body) if body is not None else ""
                            if body is None:
                                warnings.append(f"{target} 批注 {key} 缺少文字，仍保留记录。")
                            result.append(Comment(cid, authors.get(attr(node, "authorId"), ""), content,
                                                  parent, location))
                            for child in node:
                                if local(child.tag) == "replyLst":
                                    collect(child, cid)
                        elif tag in {"replyLst", "cmLst"}:
                            collect(node, parent)
                collect(root)
            except Exception as exc:
                failures.append(f"{target}：{type(exc).__name__}：{exc}")
        if failures:
            if not result:
                raise ValueError("PPT 无法恢复可读取的批注；" + "；".join(failures))
            warnings.extend("部分提取：未能读取 " + failure for failure in failures)
        if result:
            warnings.append("PPT 当前提供幻灯片编号；对象原文定位及幻灯片截图尚未支持。")
    return result
