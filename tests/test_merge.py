import os
from xml.etree import ElementTree as ET
from zipfile import ZipFile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from openpyxl import load_workbook
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt

from commentextract.app import MainWindow
from commentextract.extract import extract_file
from commentextract.export import export_result
from commentextract.merge import merge_results, suggest_group_name
from .samples import W, make_word, patch_zip
from .test_app import wait_for_worker


def review_returns(tmp_path):
    first = make_word(tmp_path / "A文件_rev by wwl.docx")
    second = make_word(tmp_path / "A文件_rev by zsl.docx")
    with ZipFile(second) as package:
        comments = ET.fromstring(package.read("word/comments.xml"))
    comments[0].set("{" + W + "}author", "另一位评审人")
    patch_zip(second, {"word/comments.xml": ET.tostring(comments, encoding="utf-8")})
    return [extract_file(first), extract_file(second)]


def test_merge_preserves_rows_identity_replies_and_duplicate_choice(tmp_path):
    results = review_returns(tmp_path)
    assert suggest_group_name(results) == "A文件"
    merged = merge_results(results, "A文件")
    assert len(merged.issues) == 2
    assert merged.issues[0].root.author == "评审人甲"
    assert merged.issues[1].root.author == "另一位评审人"
    assert [issue.id for issue in merged.issues] == ["R0001", "R0002"]
    assert all(len(issue.replies) == 1 for issue in merged.issues)
    assert merged.issues[0].root.id != merged.issues[1].root.id
    assert all(issue.replies[0].parent_id == issue.root.id for issue in merged.issues)
    # Identical text remains separate until a human explicitly marks repetition.
    assert all(issue.acceptance == "" for issue in merged.issues)
    merged.issues[0].acceptance = "是"
    merged.issues[1].acceptance = "重复"
    assert results[0].issues[0].acceptance == ""
    assert results[1].issues[0].acceptance == ""
    output = export_result(merged, tmp_path / "out")
    assert output.name == "A文件_评审意见提取.xlsx"
    workbook = load_workbook(output)
    summary = workbook["评审汇总"]
    assert summary.max_row == 3
    assert summary.max_column == 10
    assert summary["G2"].value == "是"
    assert summary["G3"].value == "重复"
    report = workbook["提取报告"]
    assert report["B3"].value == 2
    assert report["B4"].value == '=COUNTIF(\'评审汇总\'!G:G,"重复")'
    assert report["B5"].value == "=B3-B4"
    assert all(any(str(result.source) == row[1].value for row in report.iter_rows(min_col=1, max_col=2))
               for result in results)
    workbook.close()


def test_gui_summary_keeps_individual_rows_and_acceptance_choices(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    for result in review_returns(tmp_path):
        window.add_result(result)
    assert all(window.file_list.item(i).checkState() == Qt.Checked for i in range(2))
    window.file_list.setCurrentRow(0)
    window.table.item(0, 6).setText("是")
    window.file_list.setCurrentRow(1)
    window.table.item(0, 6).setText("重复")
    output = tmp_path / "out" / "A文件.xlsx"
    monkeypatch.setattr("commentextract.app.choose_summary_file", lambda *args: str(output))
    monkeypatch.setattr(QMessageBox, "information", lambda *args: QMessageBox.Ok)
    window.export_summary()
    wait_for_worker(window)
    assert len(window.results) == 2  # Export does not replace the input list.
    assert not window.dirty
    workbook = load_workbook(output)
    assert workbook["评审汇总"]["G2"].value == "是"
    assert workbook["评审汇总"]["G3"].value == "重复"
    workbook.close()
    window.close()
