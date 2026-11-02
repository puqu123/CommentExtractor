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
from tests.samples import create_samples

if __name__ == "__main__":
    executable = Path(sys.argv[1] if len(sys.argv) > 1 else f"dist/v{__version__}/CommentExtractor/CommentExtractor.exe").resolve()
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
            assert sheet.max_column == 9
            issues += sheet.max_row - 1
            for row in sheet.iter_rows(min_row=2):
                assert row[5].value in (None, "")
                if row[8].hyperlink:
                    assert (path.parent / unquote(row[8].hyperlink.target)).is_file()
            workbook.close()
        assert issues == 7, issues
        environment["QT_QPA_PLATFORM"] = "offscreen"
        process = subprocess.Popen([str(executable)], env=environment, cwd=temporary)
        try:
            time.sleep(4)
            assert process.poll() is None, f"GUI terminated with {process.returncode}"
        finally:
            process.terminate()
            process.wait(timeout=15)
    print("Bundle smoke test passed: 6 workbooks, 7 issues, PDF assets, GUI startup.")
