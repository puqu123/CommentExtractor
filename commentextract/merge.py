"""Explicitly group review returns; never infer duplicate opinions."""
import re
from copy import deepcopy
from pathlib import Path

from .models import Extraction


def suggest_group_name(results):
    stem = results[0].source.stem
    # This is only an editable dialog default, never an automatic grouping rule.
    return re.split(r"[_-]rev(?:iew)?(?:\b|[_ -])", stem, maxsplit=1, flags=re.IGNORECASE)[0] or stem


def merge_results(results, name):
    if len(results) < 2:
        raise ValueError("请至少选择两个评审返回文件。")
    if any(result.error for result in results):
        raise ValueError("提取失败的文件不能合并，请先检查对应错误。")
    name = name.strip().rstrip(". ")
    if not name or re.search(r'[<>:"/\\|?*\x00-\x1f]', name):
        raise ValueError("请填写有效的文档名称，不要包含路径或文件名特殊字符。")
    if Path(name).suffix.lower() in {".docx", ".xlsx", ".pdf", ".pptx"}:
        name = Path(name).stem
    sources = list(dict.fromkeys(source for result in results
                                 for source in (result.sources or [result.source])))
    # This path names the export group only. Each issue keeps its real source.
    merged = Extraction(results[0].source.parent / (name + ".review"), sources=sources)
    for result in results:
        merged.warnings.extend(f"{result.source.name}：{warning}" for warning in result.warnings)
        for issue in result.issues:
            copied = deepcopy(issue)
            copied.id = f"R{len(merged.issues) + 1:04d}"
            copied.source = issue.source or result.source
            # Comment IDs are only unique within an individual source package.
            prefix = str(copied.source) + "#"
            for comment in [copied.root] + copied.replies:
                comment.id = prefix + comment.id
                if comment.parent_id:
                    comment.parent_id = prefix + comment.parent_id
            merged.issues.append(copied)
    return merged
