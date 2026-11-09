from pathlib import Path
from contextlib import ExitStack
import tempfile

from .models import Extraction, group_comments
from .support import Collector, exception_details

SUPPORTED = {".doc", ".docx", ".xlsx", ".pptx"}


def extract_file(path, *, developer=False, reviewer="", reference=None, ocr=True, progress=None, word_pages=False, ocr_backend="windows", ai=False) -> Extraction:
    source = Path(path).resolve()
    result = Extraction(source)
    diagnostic = Collector(source, "developer_word" if developer else "standard")
    from .progress import callback, stage
    token = callback.set(progress)
    temporary = ExitStack()
    try:
        stage(5, "打开文件")
        suffix = source.suffix.lower()
        read_path = source
        layout = []
        if suffix == ".doc":
            from .word_layout import read_layout
            stage(10, "通过 Microsoft Word 转换旧格式副本")
            layout, converted = read_layout(source, convert=True)
            folder = Path(temporary.enter_context(tempfile.TemporaryDirectory(prefix="CommentExtractor-doc-")))
            read_path = folder / "converted.docx"
            read_path.write_bytes(converted)
            diagnostic.source = read_path.resolve()  # The converted package is still the source, not a reference manual.
            suffix = ".docx"
        if suffix not in SUPPORTED:
            raise ValueError("支持 .doc、.docx、.xlsx、.pptx；.doc 依赖 Microsoft Word，.xls/.ppt 请先另存为新格式。PDF 已移出需求范围。")
        if developer and suffix != ".docx":
            raise ValueError("开发评审正文模式仅支持 .docx 文件。")
        if suffix == ".docx":
            if developer:
                from .developer_word import read_developer_word
                reference_read = reference
                if reference and Path(reference).suffix.lower() == ".doc":
                    from .word_layout import read_layout
                    stage(20, "通过 Microsoft Word 转换原手册副本")
                    try:
                        _, converted_reference = read_layout(reference, convert=True)
                        folder = Path(temporary.enter_context(tempfile.TemporaryDirectory(prefix="CommentExtractor-manual-")))
                        reference_read = folder / "manual.docx"
                        reference_read.write_bytes(converted_reference)
                    except RuntimeError as exc:
                        result.warnings.append("原手册未能读取：" + str(exc) + " 已保留评审意见及截图。")
                        reference_read = None
                comments = read_developer_word(read_path, result.warnings, reviewer, reference_read, ocr, ocr_backend, ai)
            else:
                from .word import read_word
                comments = read_word(read_path, result.warnings)
        elif suffix == ".xlsx":
            from .excel import read_excel
            comments = read_excel(source, result.warnings)
        else:
            from .powerpoint import read_powerpoint
            comments = read_powerpoint(source, result.warnings)
        stage(87, "整理意见与回复")
        result.issues = group_comments(comments, result.warnings)
        for issue in result.issues:
            issue.source = source
        if word_pages and result.issues and developer and not reference:
            result.warnings.append("未提供原手册，未读取排版页码；不会把评审文件的页码当成原手册页码。")
        elif word_pages and result.issues and suffix == ".docx":
            from .word_layout import read_layout, add_pages, developer_pages
            stage(90, "通过 Microsoft Word 读取排版页码")
            try:
                if not layout or (developer and reference):
                    if developer:
                        layout, _ = read_layout(reference if reference else source)
                        word_comments = []
                    else:
                        layout, _, word_comments = read_layout(source, include_comments=True)
                else:
                    word_comments = []
                if not developer and word_comments:
                    from .word_layout import apply_word_comment_positions
                    ordinary_comments = [comment for issue in result.issues
                                         for comment in [issue.root] + issue.replies]
                    apply_word_comment_positions(ordinary_comments, word_comments)
                for issue in result.issues:
                    if developer and issue.root.location_anchors:
                        issue.root.location = developer_pages(issue.root.location_anchors, layout)
                    elif not developer:
                        issue.root.location = add_pages(issue.root.location, issue.root.context, layout)
            except (RuntimeError, OSError) as exc:
                result.warnings.append(str(exc) + " 已保留提取内容及标题定位。")
                if developer:
                    for issue in result.issues:
                        if issue.root.location_anchors:
                            issue.root.location = developer_pages(issue.root.location_anchors, [])
        result.warnings = list(dict.fromkeys(result.warnings))
    except Exception as exc:
        diagnostic.error = exception_details(exc)
        result.error = f"[{diagnostic.error['code']}] {type(exc).__name__}：{exc}"
    finally:
        result.diagnostics = diagnostic.finish(result)
        stage(100, "处理完成" if not result.error else "处理结束，有异常")
        callback.reset(token)
        temporary.close()
    return result
