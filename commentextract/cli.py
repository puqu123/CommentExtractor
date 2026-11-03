import argparse
from pathlib import Path

from .extract import extract_file, SUPPORTED
from .export import export_result
from .inputs import collect_files


def main():
    parser = argparse.ArgumentParser(description="离线提取 Office 评审意见，每个源文件生成一个 Excel。")
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("-o", "--output", required=True, type=Path)
    args = parser.parse_args()
    failed = False
    output = args.output.resolve()
    files, skipped = collect_files(args.files, output=output)
    for path, reason in skipped:
        print(f"跳过：{path} — {reason}")
        if not path.is_file() or path.suffix.lower() not in SUPPORTED:
            failed = True
    for path in files:
        result = extract_file(path)
        if result.error:
            print(f"失败：{path.name} — {result.error}")
            failed = True
            continue
        try:
            destination = export_result(result, args.output)
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
