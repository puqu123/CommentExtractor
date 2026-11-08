"""Collect inputs with an explanation for every skipped file."""
from pathlib import Path

from .extract import SUPPORTED
from .models import HEADERS
from .ooxml import Package, elements, text


def is_export(path):
    if path.suffix.lower() != ".xlsx" or "_评审意见" not in path.stem:
        return False
    try:
        with Package(path) as package:
            workbook = package.xml("xl/workbook.xml")
            sheets = elements(workbook, "sheet")
            if [s.get("name") for s in sheets] != ["评审汇总", "提取报告"]:
                return False
            # Verify actual headers as well as names; never skip by filename alone.
            from .ooxml import attr
            part = package.rels("xl/workbook.xml")[attr(sheets[0], "id")][1]
            shared = [text(n) for n in elements(package.xml("xl/sharedStrings.xml"), "si")] if "xl/sharedStrings.xml" in package.names else []
            row = elements(package.xml(part), "row")[0]
            headers = []
            for cell in elements(row, "c"):
                if cell.get("t") == "s":
                    headers.append(shared[int(elements(cell, "v")[0].text)])
                else:
                    headers.append(text(cell))
            legacy = [h for h in HEADERS if h != "上下文截图"] + ["上下文截图"]
            return headers in (HEADERS, [h for h in HEADERS if h != "文件名"],
                               legacy, [h for h in legacy if h != "文件名"])
    except Exception:
        return False  # Let extraction surface corrupt inputs as failures.


def collect_files(paths, existing=(), output=None):
    files, skipped = [], []
    seen = {Path(p).resolve() for p in existing}
    for value in paths:
        path = Path(value).resolve()
        directory = path.is_dir()
        try:
            candidates = sorted(p for p in path.rglob("*") if p.is_file()) if directory else [path]
        except OSError as exc:
            skipped.append((path, f"无法读取目录：{exc}"))
            continue
        for candidate in candidates:
            candidate = candidate.resolve()
            if directory and candidate.suffix.lower() not in SUPPORTED:
                continue
            reason = ""
            if not candidate.is_file():
                reason = "文件不存在或不可读取"
            elif candidate.suffix.lower() not in SUPPORTED:
                reason = "不支持的格式；仅支持 .docx、.xlsx、.pptx"
            elif candidate.name.startswith("~$"):
                reason = "Office 临时文件"
            elif candidate in seen:
                reason = "已在列表中或本次重复选择"
            elif output and Path(output).resolve() in candidate.parents:
                reason = "位于输出目录内"
            elif is_export(candidate):
                reason = "本工具生成的导出表"
            if reason:
                skipped.append((candidate, reason))
            else:
                files.append(candidate)
                seen.add(candidate)
    return files, skipped
