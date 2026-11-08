"""Run the actual ZIPs from a clean folder, before and after optional OCR overlay."""
import os
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commentextract import __version__
from scripts.package_windows import MAX_DOWNLOAD_BYTES, is_ocr_file
from scripts.make_developer_samples import make_developer_samples
from openpyxl import load_workbook


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-main", type=Path)
    parser.add_argument("--legacy-addon", type=Path)
    args = parser.parse_args()
    if bool(args.legacy_main) != bool(args.legacy_addon):
        parser.error("Provide both --legacy-main and --legacy-addon.")
    project = Path(__file__).resolve().parents[1]
    base = project / "dist" / f"CommentExtractor-v{__version__}-win64.zip"
    addon = project / "dist" / f"CommentExtractor-v{__version__}-ocr-addon-win64.zip"
    for archive in [base, addon]:
        assert archive.stat().st_size < MAX_DOWNLOAD_BYTES
    environment = dict(os.environ, HTTP_PROXY="http://127.0.0.1:9", HTTPS_PROXY="http://127.0.0.1:9")
    environment.pop("PYTHONPATH", None)
    with tempfile.TemporaryDirectory(prefix="commentextract-split-") as folder:
        root = Path(folder)
        destination = root / "离线程序 含空格"
        with ZipFile(base) as archive:
            assert archive.testzip() is None
            assert not any(is_ocr_file(Path(n).relative_to("CommentExtractor")) for n in archive.namelist())
            archive.extractall(destination)
        executable = destination / "CommentExtractor" / "CommentExtractor.exe"
        smoke = str(project / "scripts" / "smoke_bundle.py")
        subprocess.run([sys.executable, smoke, str(executable), "--without-enhanced"], check=True, env=environment, timeout=180)
        inputs, _ = make_developer_samples(root / "inputs")
        output = root / "missing-addon"
        # Explicitly selecting an unavailable addon must still preserve all opinions/images.
        subprocess.run([str(executable), "--cli", str(inputs / "02_开发评审_五条意见.docx"),
                        "--developer-word", "--ocr-backend", "rapidocr", "-o", str(output)],
                       check=True, env=environment, timeout=60, cwd=root)
        workbook = load_workbook(next(output.glob("*.xlsx")))
        assert workbook["评审汇总"].max_row == 6
        report = "\n".join(str(row[1].value or "") for row in workbook["提取报告"].iter_rows(min_row=2))
        assert "扩展包" in report
        assert len([p for p in output.glob("*_附件/*.png") if not p.name.endswith("_预览.png")]) == 5
        workbook.close()
        with ZipFile(addon) as archive:
            assert archive.testzip() is None
            assert "CommentExtractor/CommentExtractor.exe" not in archive.namelist()
            archive.extractall(destination)
        subprocess.run([sys.executable, smoke, str(executable)], check=True, env=environment, timeout=180)
        if args.legacy_main:
            # Simulate a real upgrade in the existing program directory.
            upgrade = root / "已有程序 直接升级"
            for source in (args.legacy_main, args.legacy_addon):
                with ZipFile(source) as archive:
                    archive.extractall(upgrade)
            marker = upgrade / "CommentExtractor" / "_internal" / "ocr-addon.json"
            previous_marker = marker.read_bytes()
            assert json.loads(previous_marker)["app_version"] != __version__
            with ZipFile(base) as archive:
                archive.extractall(upgrade)
            assert marker.read_bytes() == previous_marker
            subprocess.run([sys.executable, smoke, str(upgrade / "CommentExtractor" / "CommentExtractor.exe")],
                           check=True, env=environment, timeout=180)
            print("Existing addon reused after upgrading the main program.")
    print("Split downloads passed: each <100,000,000 bytes, main-only Office/Windows OCR, missing-addon recovery, merged offline RapidOCR, Unicode path.")


if __name__ == "__main__":
    main()
