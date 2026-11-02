"""Read OOXML packages without launching Office or changing source files."""
from __future__ import annotations

import posixpath
from pathlib import Path
from zipfile import ZipFile

from defusedxml import ElementTree as ET


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
    def __init__(self, path: Path):
        self.zip = ZipFile(path)
        self.names = set(self.zip.namelist())
        # A corrupt/hostile package must not exhaust memory before displaying an error.
        if any(i.file_size > 128 * 1024 * 1024 for i in self.zip.infolist()):
            self.zip.close()
            raise ValueError("文件包含超过 128 MB 的单个部件，当前版本不支持。")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.zip.close()

    def xml(self, part: str):
        return ET.fromstring(self.zip.read(part))

    def rels(self, part: str):
        directory, filename = posixpath.split(part)
        relpart = posixpath.join(directory, "_rels", filename + ".rels")
        if relpart not in self.names:
            return {}
        result = {}
        for rel in self.xml(relpart):
            if rel.get("TargetMode") == "External":
                continue
            target = rel.get("Target", "")
            resolved = posixpath.normpath(target.lstrip("/") if target.startswith("/")
                                          else posixpath.join(directory, target))
            if resolved.startswith("../"):
                raise ValueError("文件关系路径无效。")
            result[rel.get("Id")] = (rel.get("Type", "").rsplit("/", 1)[-1], resolved)
        return result
