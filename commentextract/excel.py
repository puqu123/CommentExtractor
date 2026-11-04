from __future__ import annotations

from .models import Comment
from .ooxml import Package, attr, elements, text
from openpyxl.utils.cell import range_boundaries, get_column_letter


def cell_range(ref):
    """Canonical A1 address, including reverse-order range endpoints."""
    left, top, right, bottom = range_boundaries(ref.replace("$", "").upper())
    if None in (left, top, right, bottom) or min(left, top, right, bottom) < 1:
        raise ValueError("批注单元格地址无效：" + ref)
    left, right = sorted((left, right))
    top, bottom = sorted((top, bottom))
    start, end = f"{get_column_letter(left)}{top}", f"{get_column_letter(right)}{bottom}"
    return (start if start == end else start + ":" + end), (left, top, right, bottom)


def read_excel(path, warnings):
    result = []
    with Package(path, warnings) as package:
        workbook = package.xml("xl/workbook.xml")
        rels = package.rels("xl/workbook.xml")
        shared = []
        shared_parts = [target for kind, target in rels.values() if kind.lower() == "sharedstrings"]
        if not shared_parts and "xl/sharedStrings.xml" in package.names:
            shared_parts = ["xl/sharedStrings.xml"]
        if shared_parts:
            try:
                shared = [text(node) for node in elements(package.xml(shared_parts[0]), "si")]
            except Exception as exc:
                warnings.append(f"共享字符串表无法读取：{type(exc).__name__}：{exc}；继续提取批注，对应单元格内容可能缺失。")
        people = {}
        person_parts = {target for kind, target in rels.values() if kind.lower() in {"person", "persons"}}
        person_parts.update(part for part in package.names if part.startswith("xl/persons/") and part.endswith(".xml"))
        for part in sorted(person_parts):
            try:
                for person in elements(package.xml(part), "person"):
                    people[attr(person, "id")] = attr(person, "displayName")
            except Exception as exc:
                warnings.append(f"作者表无法读取 {part}：{type(exc).__name__}：{exc}；无法识别的姓名留空。")
        for sheet in elements(workbook, "sheet"):
            rid = attr(sheet, "id")
            if rid not in rels:
                continue
            part = rels[rid][1]
            cells = {}
            try:
                sheet_xml = package.xml(part)
            except Exception as exc:
                warnings.append(f"工作表内容无法读取 {part}：{type(exc).__name__}：{exc}；批注仍保留，对应内容留空。")
                from xml.etree.ElementTree import Element
                sheet_xml = Element("worksheet")
            merged = [cell_range(attr(node, "ref")) for node in elements(sheet_xml, "mergeCell")]
            for cell in elements(sheet_xml, "c"):
                values = elements(cell, "v")
                raw = values[0].text or "" if values else ""
                if cell.get("t") == "s":
                    try:
                        index = int(raw)
                        if not 0 <= index < len(shared):
                            raise IndexError(index)
                        raw = shared[index]
                    except (ValueError, IndexError):
                        raw = ""
                        warnings.append(f"{attr(sheet, 'name')} · {cell.get('r', '')}：共享字符串索引无效，单元格内容留空，批注仍保留。")
                elif cell.get("t") == "inlineStr":
                    raw = text(cell)
                elif not raw:
                    formulas = elements(cell, "f")
                    if formulas:
                        raw = "=" + (formulas[0].text or "")
                cells[cell.get("r")] = raw

            def anchor(ref):
                if not ref:
                    warnings.append(f"{attr(sheet, 'name')}：有批注未记录单元格地址。")
                    return f"{attr(sheet, 'name')} · 位置未记录", ""
                try:
                    address, bounds = cell_range(ref)
                except (ValueError, TypeError):
                    warnings.append(f"{attr(sheet, 'name')}：批注单元格地址无效（{ref}），保留意见，位置待核对。")
                    return f"{attr(sheet, 'name')} · 位置未确定（{ref}）", ""
                left, top, right, bottom = bounds
                if left == right and top == bottom:
                    for merged_ref, merged_bounds in merged:
                        ml, mt, mr, mb = merged_bounds
                        if ml <= left <= mr and mt <= top <= mb:
                            address, bounds = merged_ref, merged_bounds
                            break
                left, top, right, bottom = bounds
                if left == right and top == bottom:
                    content = cells.get(address, "")
                else:
                    values = []
                    for coordinate, value in cells.items():
                        if not value:
                            continue
                        _, (col, row, _, _) = cell_range(coordinate)
                        if left <= col <= right and top <= row <= bottom:
                            values.append((row, col, coordinate, value))
                    values.sort()
                    content = values[0][3] if len(values) == 1 else "\n".join(f"{c}：{v}" for _, _, c, v in values)
                return f"{attr(sheet, 'name')} · {address}", content
            links = package.rels(part)
            threaded_cells = set()
            for kind, target in links.values():
                if kind.lower() != "threadedcomment":
                    continue
                nodes = elements(package.xml(target), "threadedComment")
                nodes_by_id = {attr(node, "id"): node for node in nodes}
                for node in nodes:
                    ref = attr(node, "ref")
                    ancestor = node
                    seen = set()
                    while not ref and attr(ancestor, "parentId") in nodes_by_id:
                        parent_id = attr(ancestor, "parentId")
                        if parent_id in seen:
                            break
                        seen.add(parent_id)
                        ancestor = nodes_by_id[parent_id]
                        ref = attr(ancestor, "ref")
                    threaded_cells.add(ref)
                    parent = attr(node, "parentId")
                    location, context = anchor(ref)
                    result.append(Comment(target + "#" + attr(node, "id"),
                                          people.get(attr(node, "personId"), ""), text(node),
                                          target + "#" + parent if parent else None,
                                          location, context))
            for kind, target in links.values():
                if kind != "comments":
                    continue
                root = package.xml(target)
                authors = ["".join(n.itertext()) for n in elements(root, "author")]
                for index, node in enumerate(elements(root, "comment")):
                    ref = attr(node, "ref")
                    content = text(node)
                    # Modern Excel embeds compatibility placeholders in legacy comments.
                    if ref in threaded_cells and "[Threaded comment]" in content:
                        continue
                    try:
                        author_id = int(attr(node, "authorId", ""))
                        if not 0 <= author_id < len(authors):
                            raise IndexError(author_id)
                        author = authors[author_id]
                    except (ValueError, IndexError):
                        author = ""
                        warnings.append(f"{attr(sheet, 'name')} · {ref}：批注作者编号无效或缺少作者表，姓名留空，意见保留。")
                    location, context = anchor(ref)
                    result.append(Comment(target + "#" + str(index), author, content,
                                          location=location, context=context))
    return result
