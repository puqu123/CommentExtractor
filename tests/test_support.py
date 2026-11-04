import json
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QPlainTextEdit, QPushButton, QMessageBox

from commentextract.extract import extract_file
from commentextract.models import Extraction
from commentextract.support import exception_details, support_report
from .samples import make_word, make_powerpoint, patch_zip
from .compatibility_cases import custom_word
from .test_app import wait_for_worker


PRIVATE = "PRIVATE_COMPANY_机密"


def test_report_has_codes_and_structure_but_no_document_data(tmp_path):
    source = custom_word(tmp_path / (PRIVATE + ".docx"), [("0", PRIVATE, PRIVATE, None)],
                         '<w:p><w:r><w:t>' + PRIVATE + '</w:t></w:r></w:p>')
    result = extract_file(source)
    assert not result.error
    assert PRIVATE not in json.dumps(result.diagnostics, ensure_ascii=False)
    result.warnings.extend(["首条编号前的说明：" + PRIVATE, "未关联的批注部件 " + PRIVATE])
    # The renderer must not dump arbitrary fields or raw exception messages.
    result.diagnostics["unknown"] = PRIVATE
    result.diagnostics["parts"][PRIVATE] = 99
    result.diagnostics["error"]["message"] = PRIVATE
    report = support_report([result])
    assert PRIVATE not in report
    assert str(tmp_path) not in report
    assert source.name not in report
    assert "标准节点 comment：1" in report
    assert "CE-I203" in report
    assert "CE-W304" in report


def test_failures_have_stable_code_without_raw_private_error(tmp_path):
    source = tmp_path / (PRIVATE + ".pptx")
    source.write_bytes(b"invalid")
    result = extract_file(source)
    assert "CE-E201" in result.error
    report = support_report([result])
    assert "CE-E201" in report and "BadZipFile" in report
    assert PRIVATE not in report and str(tmp_path) not in report
    event = {"phase": "export", "error": exception_details(PermissionError(PRIVATE + "\\output.xlsx"))}
    report = support_report([result], [event])
    assert "CE-E102" in report
    assert PRIVATE not in report


def test_xml_failure_records_part_category_without_part_filename(tmp_path):
    source = make_powerpoint(tmp_path / "normal.pptx")
    patch_zip(source, {"ppt/comments/" + PRIVATE + ".xml": "<broken>"})
    result = extract_file(source)
    assert not result.error
    assert result.diagnostics["read_failures"] == 1
    assert result.diagnostics["failed_parts"] == {"ppt_comments": 1}
    assert PRIVATE not in json.dumps(result.diagnostics, ensure_ascii=False)
    report = support_report([result])
    assert "CE-W201" in report
    assert "未读部件类别 ppt_comments：1" in report
    assert PRIVATE not in report


def test_diagnostic_sessions_do_not_mix_after_failures_or_across_threads(tmp_path):
    bad = tmp_path / "bad.docx"
    bad.write_bytes(b"invalid")
    first = custom_word(tmp_path / "one.docx", [("0", "甲", "一", None)])
    second = custom_word(tmp_path / "two.docx", [("0", "甲", "一", None), ("1", "乙", "二", None)])
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(extract_file, [bad, first, second]))
    assert "CE-E201" in results[0].error
    assert results[1].diagnostics["nodes"]["comment"] == 1
    assert results[2].diagnostics["nodes"]["comment"] == 2
    assert not results[1].diagnostics["error"] and not results[2].diagnostics["error"]
    assert all(len(r.diagnostics["packages"]) == 1 for r in results[1:])


def test_copy_button_copies_only_preview_and_export_failures_are_reported(tmp_path, monkeypatch):
    from commentextract.app import MainWindow
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    source = make_word(tmp_path / (PRIVATE + ".docx"))
    window.add_files([source])
    wait_for_worker(window)
    destination = tmp_path / "out"
    monkeypatch.setattr("commentextract.app.choose_directory", lambda *args: str(destination))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: QMessageBox.Ok)

    def fail_export(*args):
        raise PermissionError(PRIVATE + " output")
    monkeypatch.setattr("commentextract.export.export_result", fail_export)
    window.export()
    wait_for_worker(window)
    assert window.diagnostic_events[-1]["error"]["code"] == "CE-E102"
    window.show_support_report()
    reader = window.findChild(QDialog, "supportReportDialog")
    text = reader.findChild(QPlainTextEdit)
    assert text.isReadOnly()
    assert PRIVATE not in text.toPlainText()
    assert "CE-E102" in text.toPlainText()
    assert "界面阶段：空闲" in text.toPlainText()
    copied = []

    class Clipboard:
        def setText(self, value):
            copied.append(value)
    monkeypatch.setattr(QApplication, "clipboard", lambda: Clipboard())
    reader.findChild(QPushButton, "copySupportReport").click()
    assert copied == [text.toPlainText()]
    reader.close()
    window.clear_files()
    assert window.diagnostic_events == []
    window.close()


def test_diagnostics_only_cli_does_not_print_private_paths_or_export(tmp_path, monkeypatch, capsys):
    from commentextract.cli import main
    import sys
    source = custom_word(tmp_path / (PRIVATE + ".docx"), [("0", PRIVATE, PRIVATE, None)])
    monkeypatch.setattr(sys, "argv", ["commentextractor-cli", str(source), "--diagnostics-only"])
    assert main() == 0
    report = capsys.readouterr().out
    assert "CE-D1" in report
    assert PRIVATE not in report and str(tmp_path) not in report
    assert not list(tmp_path.glob("*.xlsx"))
