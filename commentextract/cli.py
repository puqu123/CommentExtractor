import argparse
from pathlib import Path

from .extract import extract_file, SUPPORTED
from .export import export_result
from .inputs import collect_files
from .support import support_report


def main():
    parser = argparse.ArgumentParser(description="离线提取 Office 评审意见，每个源文件生成一个 Excel。")
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--diagnostics-only", action="store_true", help="只输出脱敏诊断，不导出 Excel；输出前仍应按公司规定审核")
    parser.add_argument("--developer-word", action="store_true", help="按编号抽取开发评审 Word 正文及截图")
    parser.add_argument("--reference", type=Path, help="开发评审对应的原始 Word（.docx），用于匹配定位")
    parser.add_argument("--reviewer", default="", help="开发评审的评审人，默认留空")
    parser.add_argument("--no-ocr", action="store_true", help="保留截图但不执行离线 OCR")
    parser.add_argument("--ocr-backend", choices=["windows", "rapidocr"], default="windows", help="离线截图识别引擎")
    parser.add_argument("--word-pages", action="store_true", help="使用本机 Microsoft Word 读取排版页码")
    parser.add_argument("--content-mode", choices=["both", "text", "images"], default="both", help="导出已识别文字与截图 / 仅文字 / 仅截图；不影响评审意见正文")
    args = parser.parse_args()
    if not args.diagnostics_only and args.output is None:
        parser.error("导出需要指定 -o / --output。")
    failed = False
    output = args.output.resolve() if args.output else None
    files, skipped = collect_files(args.files, output=output)
    if args.diagnostics_only:
        results = [extract_file(path, developer=args.developer_word, reference=args.reference,
                                reviewer=args.reviewer, ocr=not args.no_ocr, ocr_backend=args.ocr_backend,
                                word_pages=args.word_pages) for path in files]
        print(support_report(results))
        print(f"未处理输入条目：{len(skipped)}；未包含这些条目的名称或路径。")
        return 0 if results and not any(result.error for result in results) and not skipped else 1
    for path, reason in skipped:
        print(f"跳过：{path} — {reason}")
        if not path.is_file() or path.suffix.lower() not in SUPPORTED:
            failed = True
    for path in files:
        result = extract_file(path, developer=args.developer_word, reference=args.reference,
                              reviewer=args.reviewer, ocr=not args.no_ocr, ocr_backend=args.ocr_backend,
                              word_pages=args.word_pages)
        if result.error:
            print(f"失败：{path.name} — {result.error}")
            failed = True
            continue
        try:
            destination = export_result(result, args.output, content_mode=args.content_mode)
            print(f"{path.name}：{len(result.issues)} 条意见 → {destination}")
            for warning in result.warnings:
                print(f"  提示：{warning}")
        except Exception as exc:
            print(f"导出失败：{path.name} — {exc}")
            failed = True
    if not files:
        parser.error("没有找到支持的文件。")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
