"""Verify the bundled application without relying on an installed target Python."""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from openpyxl import load_workbook
from commentextract import __version__
from tests.samples import create_samples, make_word
from scripts.make_developer_samples import make_developer_samples

if __name__ == "__main__":
    executable = Path(sys.argv[1] if len(sys.argv) > 1 else f"dist/v{__version__}/CommentExtractor/CommentExtractor.exe").resolve()
    internal = executable.parent / "_internal"
    forbidden = [p for p in internal.rglob("*") if p.name.lower().startswith(("pymupdf", "fitz", "mupdf"))]
    assert not forbidden, forbidden
    with tempfile.TemporaryDirectory(prefix="commentextract-bundle-") as temporary:
        root = Path(temporary)
        inputs = root / "input"
        outputs = root / "output"
        create_samples(inputs)
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        subprocess.run([str(executable), "--cli", str(inputs), "-o", str(outputs)],
                       check=True, timeout=90, env=environment, cwd=temporary)
        workbooks = sorted(outputs.glob("*.xlsx"))
        assert len(workbooks) == 6, [path.name for path in workbooks]
        issues = 0
        for path in workbooks:
            workbook = load_workbook(path)
            assert workbook.sheetnames == ["评审汇总", "提取报告"]
            sheet = workbook["评审汇总"]
            assert sheet.max_column == 10
            assert list(sheet.data_validations.dataValidation)[0].formula1 == '"是,否,重复"'
            issues += sheet.max_row - 1
            for row in sheet.iter_rows(min_row=2):
                assert row[6].value in (None, "")
                if row[9].hyperlink:
                    assert (path.parent / unquote(row[9].hyperlink.target)).is_file()
            workbook.close()
        assert issues == 6, issues
        developer_inputs, _ = make_developer_samples(root / "developer-input")
        developer_outputs = root / "developer-output"
        subprocess.run([str(executable), "--cli", str(developer_inputs / "02_开发评审_五条意见.docx"),
                        "--developer-word", "--reference", str(developer_inputs / "01_被评审原文_虚构.docx"),
                        "--reviewer", "开发甲", "-o", str(developer_outputs)],
                       check=True, timeout=90, env=environment, cwd=temporary)
        developer_workbook = next(developer_outputs.glob("*.xlsx"))
        workbook = load_workbook(developer_workbook)
        sheet = workbook["评审汇总"]
        assert sheet.max_row == 6
        assert sheet["E2"].value == "开发甲"
        assert "截图后的补充文字" in sheet["F2"].value
        assert sheet["J2"].hyperlink
        assert (developer_workbook.parent / unquote(sheet["J2"].hyperlink.target)).is_dir()
        assert len(list(developer_outputs.glob("*_附件/*.png"))) == 5
        workbook.close()
        private_name = "DO_NOT_DISCLOSE_FILENAME"
        diagnostic_source = make_word(inputs / (private_name + ".docx"))
        diagnosis = subprocess.run([str(executable), "--cli", str(diagnostic_source), "--diagnostics-only"],
                                   check=True, capture_output=True, timeout=30, env=environment, cwd=temporary)
        assert b"CE-D1" in diagnosis.stdout
        assert private_name.encode() not in diagnosis.stdout + diagnosis.stderr
        diagnostic_source.write_bytes(b"intentionally broken")
        diagnosis = subprocess.run([str(executable), "--cli", str(diagnostic_source), "--diagnostics-only"],
                                   capture_output=True, timeout=30, env=environment, cwd=temporary)
        assert diagnosis.returncode == 1
        assert b"CE-E201" in diagnosis.stdout
        assert private_name.encode() not in diagnosis.stdout + diagnosis.stderr
        environment["QT_QPA_PLATFORM"] = "offscreen"
        process = subprocess.Popen([str(executable)], env=environment, cwd=temporary)
        try:
            time.sleep(4)
            assert process.poll() is None, f"GUI terminated with {process.returncode}"
        finally:
            process.terminate()
            process.wait(timeout=15)
    print("Bundle smoke test passed: 6 Office workbooks, numbered Word with 5 issues/5 images, private-safe diagnostics, GUI startup; no PDF runtime.")
