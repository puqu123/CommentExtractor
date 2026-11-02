import argparse
from pathlib import Path

from .extract import extract_file, SUPPORTED
from .export import export_result


def main():
    parser = argparse.ArgumentParser(description="离线提取 Office/PDF 评审意见，每个源文件生成一个 Excel。")
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("-o", "--output", required=True, type=Path)
    parser.add_argument("--no-screenshots", action="store_true")
    args = parser.parse_args()
    failed = False
    files = []
    output = args.output.resolve()
    for path in args.files:
        if path.is_dir():
            files.extend(p for p in sorted(path.rglob("*")) if p.suffix.lower() in SUPPORTED
                         and not p.name.startswith("~$") and "_评审意见" not in p.stem
                         and output not in p.resolve().parents)
        else:
            files.append(path)
    for path in dict.fromkeys(p.resolve() for p in files):
        result = extract_file(path)
        if result.error:
            print(f"失败：{path.name} — {result.error}")
            failed = True
            continue
        try:
            destination = export_result(result, args.output, not args.no_screenshots)
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
