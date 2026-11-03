from pathlib import Path

from .models import Extraction, group_comments

SUPPORTED = {".docx", ".xlsx", ".pptx"}


def extract_file(path) -> Extraction:
    source = Path(path).resolve()
    result = Extraction(source)
    try:
        suffix = source.suffix.lower()
        if suffix not in SUPPORTED:
            raise ValueError("支持 .docx、.xlsx、.pptx；旧版 Office 文件请先另存为新格式。PDF 已移出需求范围。")
        if suffix == ".docx":
            from .word import read_word
            comments = read_word(source, result.warnings)
        elif suffix == ".xlsx":
            from .excel import read_excel
            comments = read_excel(source, result.warnings)
        else:
            from .powerpoint import read_powerpoint
            comments = read_powerpoint(source, result.warnings)
        result.issues = group_comments(comments, result.warnings)
        for issue in result.issues:
            issue.source = source
        result.warnings = list(dict.fromkeys(result.warnings))
    except Exception as exc:
        result.error = f"{type(exc).__name__}：{exc}"
    return result
