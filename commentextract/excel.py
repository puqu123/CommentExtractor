from __future__ import annotations

from .models import Comment
from .ooxml import Package, attr, elements, local, text


def read_excel(path, warnings):
    result = []
    with Package(path) as package:
        workbook = package.xml("xl/workbook.xml")
        rels = package.rels("xl/workbook.xml")
        shared = []
        if "xl/sharedStrings.xml" in package.names:
            shared = [text(node) for node in elements(package.xml("xl/sharedStrings.xml"), "si")]
        people = {}
        for part in sorted(package.names):
            if part.startswith("xl/persons/") and part.endswith(".xml"):
                for person in elements(package.xml(part), "person"):
                    people[attr(person, "id")] = attr(person, "displayName")
        for sheet in elements(workbook, "sheet"):
            rid = attr(sheet, "id")
            if rid not in rels:
                continue
            part = rels[rid][1]
            cells = {}
            for cell in elements(package.xml(part), "c"):
                values = elements(cell, "v")
                raw = values[0].text or "" if values else ""
                if cell.get("t") == "s":
                    raw = shared[int(raw)] if raw else ""
                elif cell.get("t") == "inlineStr":
                    raw = text(cell)
                elif not raw:
                    formulas = elements(cell, "f")
                    if formulas:
                        raw = "=" + (formulas[0].text or "")
                cells[cell.get("r")] = raw
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
                    result.append(Comment(target + "#" + attr(node, "id"),
                                          people.get(attr(node, "personId"), ""), text(node),
                                          target + "#" + parent if parent else None,
                                          f"{attr(sheet, 'name')}!{ref}", cells.get(ref, "")))
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
                    author_id = int(attr(node, "authorId", "0"))
                    author = authors[author_id] if author_id < len(authors) else ""
                    result.append(Comment(target + "#" + str(index), author, content,
                                          location=f"{attr(sheet, 'name')}!{ref}", context=cells.get(ref, "")))
    return result
