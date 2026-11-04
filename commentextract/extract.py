from pathlib import Path

from .models import Extraction, group_comments
from .support import Collector, exception_details

SUPPORTED = {".docx", ".xlsx", ".pptx"}


def extract_file(path, *, developer=False, reviewer="", reference=None, ocr=True) -> Extraction:
    source = Path(path).resolve()
    result = Extraction(source)
    diagnostic = Collector(source, "developer_word" if developer else "standard")
    try:
        suffix = source.suffix.lower()
        if suffix not in SUPPORTED:
            raise ValueError("支持 .docx、.xlsx、.pptx；旧版 Office 文件请先另存为新格式。PDF 已移出需求范围。")
        if developer and suffix != ".docx":
            raise ValueError("开发评审正文模式仅支持 .docx 文件。")
        if suffix == ".docx":
            if developer:
                from .developer_word import read_developer_word
                comments = read_developer_word(source, result.warnings, reviewer, reference, ocr)
            else:
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
        diagnostic.error = exception_details(exc)
        result.error = f"[{diagnostic.error['code']}] {type(exc).__name__}：{exc}"
    finally:
        result.diagnostics = diagnostic.finish(result)
    return result
