"""Read OOXML packages without launching Office or changing source files."""
from __future__ import annotations

import posixpath
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from urllib.parse import unquote

from defusedxml import ElementTree as ET
from .support import note_package, note_xml

MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
SUPPORTED_MC_NAMESPACES = {
    "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "http://schemas.openxmlformats.org/presentationml/2006/main",
    "http://schemas.openxmlformats.org/drawingml/2006/main",
    "http://purl.oclc.org/ooxml/wordprocessingml/main",
    "http://purl.oclc.org/ooxml/spreadsheetml/main",
    "http://purl.oclc.org/ooxml/presentationml/main",
    "http://purl.oclc.org/ooxml/drawingml/main",
    "http://schemas.microsoft.com/office/word/2010/wordml",
    "http://schemas.microsoft.com/office/word/2012/wordml",
    "http://schemas.microsoft.com/office/powerpoint/2018/8/main",
    "http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments",
    "urn:schemas-microsoft-com:vml",
}


def compatible_xml(data, warnings=None):
    root = ET.fromstring(data)
    if not any(node.tag == "{" + MC + "}AlternateContent" for node in root.iter()):
        return root
    # Requires contains PREFIXES whose scope can change on every element.
    # Keep scoped declarations; a global prefix map can choose the wrong branch.
    namespaces, stack, pending = {}, [], []
    parser = ET.iterparse(BytesIO(data), events=("start-ns", "start", "end"))
    for event, value in parser:
        if event == "start-ns":
            pending.append(value)
        elif event == "start":
            scope = dict(stack[-1]) if stack else {}
            scope.update(pending)
            pending = []
            namespaces[id(value)] = scope
            stack.append(scope)
        else:
            stack.pop()
    root = parser.root

    def select(node):
        for index in range(len(node) - 1, -1, -1):
            child = node[index]
            if child.tag != "{" + MC + "}AlternateContent":
                select(child)
                continue
            chosen = None
            for branch in child:
                if branch.tag == "{" + MC + "}Choice":
                    requires = branch.get("Requires", "").split()
                    scope = namespaces[id(branch)]
                    if requires and all(scope.get(prefix) in SUPPORTED_MC_NAMESPACES for prefix in requires):
                        chosen = branch
                        break
                elif branch.tag == "{" + MC + "}Fallback":
                    chosen = branch
                    if warnings is not None:
                        warnings.append("部分内容使用兼容回退分支，当前未支持较新的扩展；请对照 Office/WPS 核对文字及截图。")
                    break
            if chosen is None:
                raise ValueError("包含尚不支持的兼容内容，且没有可用的回退分支；不能确认批注完整性。")
            select(chosen)
            node.remove(child)
            for offset, item in enumerate(list(chosen)):
                node.insert(index + offset, item)
    select(root)
    return root


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def attr(node, name: str, default: str = "") -> str:
    return next((value for key, value in node.attrib.items() if local(key) == name), default)


def elements(node, name: str):
    return [item for item in node.iter() if local(item.tag) == name]


def text(node) -> str:
    """Collect rich text with paragraph/line separation; never stringify XML markup."""
    def walk(item):
        tag = local(item.tag)
        if tag in {"t", "delText"}:
            return item.text or ""
        if tag == "text":  # classic PowerPoint plain text
            return "".join(item.itertext())
        if tag in {"br", "cr"}:
            return "\n"
        if tag == "tab":
            return "\t"
        value = "".join(walk(child) for child in item)
        return value + ("\n" if tag == "p" else "")
    return walk(node).strip()


class Package:
    def __init__(self, path: Path, warnings=None):
        self.zip = ZipFile(path)
        self.warnings = warnings
        self.names = set(self.zip.namelist())
        note_package(self, path)
        # A corrupt/hostile package must not exhaust memory before displaying an error.
        if any(i.file_size > 128 * 1024 * 1024 for i in self.zip.infolist()):
            self.zip.close()
            raise ValueError("文件包含超过 128 MB 的单个部件，当前版本不支持。")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.zip.close()

    def xml(self, part: str):
        try:
            root = compatible_xml(self.zip.read(part), self.warnings)
        except Exception:
            note_xml(self, part, failed=True)
            raise
        note_xml(self, part, root)
        return root

    def rels(self, part: str):
        directory, filename = posixpath.split(part)
        relpart = posixpath.join(directory, "_rels", filename + ".rels")
        if relpart not in self.names:
            return {}
        result = {}
        for rel in self.xml(relpart):
            if rel.get("TargetMode") == "External":
                continue
            target = unquote(rel.get("Target", ""))
            resolved = posixpath.normpath(target.lstrip("/") if target.startswith("/")
                                          else posixpath.join(directory, target))
            if resolved.startswith("../"):
                raise ValueError("文件关系路径无效。")
            result[rel.get("Id")] = (rel.get("Type", "").rsplit("/", 1)[-1], resolved)
        return result
