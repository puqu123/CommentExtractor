import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton
from PySide6.QtTest import QTest
from openpyxl import load_workbook

from commentextract.app import MainWindow
from commentextract.extract import extract_file
from commentextract.models import Extraction
from .samples import make_word
from .test_app import wait_for_worker


@pytest.fixture
def window(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    messages = []
    for kind in ("information", "warning"):
        monkeypatch.setattr(QMessageBox, kind, lambda *args: messages.append(args[-1]))
    result = MainWindow()
    for index in range(3):
        result.add_result(extract_file(make_word(tmp_path / f"手册_rev by {index}.docx")))
    result.show()
    application.processEvents()
    yield result, application, messages
    if result.worker:
        wait_for_worker(result)
    result.dirty = False
    result.close()


def test_checkboxes_default_all_and_header_tracks_partial_state(window):
    w, application, _ = window
    assert len(w.checked_results()) == 3
    assert w.select_all_box.checkState() == Qt.Checked
    assert w.checked_count.text() == "已选 3 / 3"
    # Reading a different row does not change the export scope.
    w.file_list.setCurrentRow(0)
    QTest.mouseClick(w.file_list.viewport(), Qt.LeftButton, Qt.NoModifier, w.file_list.visualItemRect(w.file_list.item(1)).center())
    assert len(w.checked_results()) == 3
    w.file_list.setCurrentRow(0)
    QTest.keyClick(w.file_list, Qt.Key_Space)
    assert len(w.checked_results()) == 2
    assert w.select_all_box.checkState() == Qt.PartiallyChecked
    w.select_all_box.click()
    assert len(w.checked_results()) == 3
    assert w.select_all_box.checkState() == Qt.Checked
    w.select_all_box.click()
    assert not w.checked_results()
    assert not w.separate_export_button.isEnabled() and not w.summary_export_button.isEnabled()
    assert "合并所选评审文件" not in [b.text() for b in w.findChildren(QPushButton)]


def test_new_files_are_checked_without_rechecking_old_files(window, tmp_path):
    w, _, _ = window
    w.select_all_box.click()
    w.add_result(extract_file(make_word(tmp_path / "新文件.docx")))
    assert len(w.checked_results()) == 1
    assert w.file_list.item(3).checkState() == Qt.Checked
    assert w.select_all_box.checkState() == Qt.PartiallyChecked


def test_separate_export_uses_checked_files_and_keeps_unexported_edits(window, tmp_path, monkeypatch):
    w, _, messages = window
    w.file_list.setCurrentRow(0)
    w.table.item(0, 6).setText("是")
    w.file_list.setCurrentRow(1)
    w.table.item(0, 6).setText("否")
    w.file_list.item(1).setCheckState(Qt.Unchecked)
    w.file_list.item(2).setCheckState(Qt.Unchecked)
    destination = tmp_path / "out"
    monkeypatch.setattr("commentextract.app.choose_directory", lambda *args: str(destination))
    w.separate_export_button.click()
    wait_for_worker(w)
    assert len(w.output_paths) == 1
    assert "0_评审意见提取.xlsx" in w.output_paths[0]
    assert len(w.results) == 3
    assert w.dirty
    assert id(w.results[1].issues[0]) in w.dirty_issue_ids
    assert id(w.results[0].issues[0]) not in w.dirty_issue_ids
    prompts = []
    monkeypatch.setattr(QMessageBox, "question", lambda *args: prompts.append(args[-1]) or QMessageBox.Cancel)
    assert not w.confirm_discard()
    assert prompts
    # Exporting the remaining edited file as a one-file summary saves that edit.
    w.file_list.item(0).setCheckState(Qt.Unchecked)
    w.file_list.item(1).setCheckState(Qt.Checked)
    target = tmp_path / "remaining.xlsx"
    monkeypatch.setattr("commentextract.app.choose_summary_file", lambda *args: str(target))
    w.summary_export_button.click()
    wait_for_worker(w)
    assert not w.dirty and not w.dirty_issue_ids
    workbook = load_workbook(target)
    assert workbook["评审汇总"]["G2"].value == "否"
    workbook.close()


def test_summary_exports_only_checked_files_without_replacing_input_list(window, tmp_path, monkeypatch):
    w, _, messages = window
    w.file_list.item(1).setCheckState(Qt.Unchecked)
    w.add_result(Extraction(tmp_path / "失败.docx", error="[CE-E201] invalid"))
    original_results = list(w.results)
    target = tmp_path / "汇总.xlsx"
    monkeypatch.setattr("commentextract.app.choose_summary_file", lambda *args: str(target))
    w.summary_export_button.click()
    wait_for_worker(w)
    assert w.output_paths == [str(target)]
    assert w.results == original_results
    assert "另有 1 份源文件提取失败" in w.status.text()
    workbook = load_workbook(target)
    sheet = workbook["评审汇总"]
    assert sheet.max_row == 3
    assert [sheet.cell(row, 2).value for row in (2, 3)] == [w.results[i].source.name for i in (0, 2)]
    assert all("答复人乙" in sheet.cell(row, 9).value for row in (2, 3))
    assert any(row[0].value == "汇总源文件数" and row[1].value == 2 for row in workbook["提取报告"])
    workbook.close()


def test_unchecked_failures_are_not_reported_as_export_exclusions(window, tmp_path, monkeypatch):
    w, _, messages = window
    w.add_result(Extraction(tmp_path / "not-checked.docx", error="failed"))
    w.file_list.item(3).setCheckState(Qt.Unchecked)
    monkeypatch.setattr("commentextract.app.choose_directory", lambda *args: str(tmp_path / "out"))
    w.export()
    wait_for_worker(w)
    assert len(w.output_paths) == 3
    assert "另有 0 份源文件提取失败" in w.status.text()


def test_cancel_and_summary_failure_keep_edits_and_do_not_overwrite(window, tmp_path, monkeypatch):
    w, _, _ = window
    w.file_list.setCurrentRow(0)
    w.table.item(0, 6).setText("重复")
    monkeypatch.setattr("commentextract.app.choose_directory", lambda *args: "")
    monkeypatch.setattr("commentextract.app.choose_summary_file", lambda *args: "")
    w.export()
    w.export_summary()
    assert not w.busy() and w.dirty
    original = tmp_path / "汇总.xlsx"
    original.write_bytes(b"existing output must be preserved")
    monkeypatch.setattr("commentextract.app.choose_summary_file", lambda *args: str(original))
    w.export_summary()
    wait_for_worker(w)
    assert original.read_bytes() == b"existing output must be preserved"
    assert w.output_paths == [str(tmp_path / "汇总_2.xlsx")]
    assert not w.dirty
    w.table.item(0, 6).setText("是")

    def fail(*args, **kwargs):
        raise PermissionError("模拟输出被占用")
    monkeypatch.setattr("commentextract.export.export_result", fail)
    w.export_summary()
    wait_for_worker(w)
    assert w.dirty and w.dirty_issue_ids


def test_no_checked_files_does_not_open_any_picker(window, monkeypatch):
    w, _, messages = window
    w.select_all_box.click()
    calls = []
    monkeypatch.setattr("commentextract.app.choose_directory", lambda *args: calls.append(args))
    monkeypatch.setattr("commentextract.app.choose_summary_file", lambda *args: calls.append(args))
    w.export()
    w.export_summary()
    assert calls == [] and not w.busy()


def test_remove_checked_preserves_files_and_unchecked_edits(window, monkeypatch):
    w, _, _ = window
    original_paths = [result.source for result in w.results]
    w.file_list.setCurrentRow(1)
    w.table.item(0, 6).setText("否")
    w.file_list.item(1).setCheckState(Qt.Unchecked)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: pytest.fail("未移除有修改的文件，不应提示"))
    w.remove_checked_button.click()
    assert len(w.results) == 1 and w.results[0].source == original_paths[1]
    assert all(path.is_file() for path in original_paths)
    assert w.results[0].issues[0].acceptance == "否" and w.dirty
    assert w.file_list.currentRow() == 0
    assert w.select_all_box.checkState() == Qt.Unchecked


def test_remove_checked_dirty_cancel_and_confirm(window, monkeypatch):
    w, _, _ = window
    w.file_list.setCurrentRow(0)
    w.table.item(0, 6).setText("是")
    w.file_list.item(1).setCheckState(Qt.Unchecked)
    w.file_list.item(2).setCheckState(Qt.Unchecked)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Cancel)
    w.remove_checked_button.click()
    assert len(w.results) == 3 and w.dirty
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Discard)
    w.remove_checked_button.click()
    assert len(w.results) == 2 and not w.dirty
    assert w.table.rowCount() == 1
    assert not w.remove_checked_button.isEnabled()
