import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton
from PySide6.QtTest import QTest

from commentextract.app import MainWindow
from .samples import make_word, create_samples


@pytest.fixture(scope="module")
def application():
    return QApplication.instance() or QApplication([])


def wait_for_worker(window):
    deadline = time.monotonic() + 20
    while window.worker is not None and time.monotonic() < deadline:
        QTest.qWait(10)
        # qWait pumps events but can retain the Python GIL; let the real worker
        # run as QApplication.exec() does in the desktop application.
        time.sleep(0.01)
    assert window.worker is None


def test_only_acceptance_is_editable(application, tmp_path):
    path = make_word(tmp_path / "review.docx")
    window = MainWindow()
    assert not window.windowIcon().isNull()
    window.add_files([path])
    wait_for_worker(window)
    assert len(window.results) == 1
    assert window.table.rowCount() == 1
    assert window.table.columnCount() == 10
    assert window.stat_values["opinions"].text() == "1"
    issue = window.results[0].issues[0]
    original = issue.values()
    for column in range(10):
        item = window.table.item(0, column)
        assert bool(item.flags() & Qt.ItemIsEditable) == (column == 6)
        if column != 6:
            item.setText("不能修改")
            assert item.text() == str(original[column])
    assert issue.values() == original
    window.table.item(0, 6).setText("是")
    assert window.results[0].issues[0].acceptance == "是"
    window.table.item(0, 6).setText("非法选项")
    assert window.table.item(0, 6).text() == "是"
    assert window.dirty
    window.acceptance_filter.setCurrentText("否")
    assert window.table.isRowHidden(0)
    window.acceptance_filter.setCurrentText("是")
    assert not window.table.isRowHidden(0)
    window.acceptance_filter.setCurrentText("全部接受情况")
    buttons = [button.text() for button in window.findChildren(QPushButton)]
    assert "编辑回复" not in buttons
    assert "保存项目" not in buttons
    assert "打开项目" not in buttons
    window.search.setText("does-not-exist")
    assert window.table.isRowHidden(0)
    window.search.clear()
    assert not window.table.isRowHidden(0)
    window.dirty = False
    window.close()


def test_multiselect_mixed_files_exports_one_workbook_each(application, tmp_path, monkeypatch):
    from openpyxl import load_workbook
    inputs = tmp_path / "input"
    output = tmp_path / "output"
    output.mkdir()
    create_samples(inputs)
    files = sorted(inputs.iterdir())
    originals = {path: path.read_bytes() for path in files}

    def choose(*args):
        return [str(path) for path in files]

    monkeypatch.setattr("commentextract.app.choose_files", choose)
    monkeypatch.setattr("commentextract.app.choose_directory", lambda *args: str(output))
    monkeypatch.setattr(QMessageBox, "information", lambda *args: QMessageBox.Ok)
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: errors.append(args[-1]))
    window = MainWindow()
    window.choose_files()
    wait_for_worker(window)
    assert len(window.results) == 6
    assert len(window.file_list.selectedIndexes()) == 1
    assert all(not result.error for result in window.results)
    assert not window.dirty  # extraction alone does not trigger a discard prompt
    window.file_list.setCurrentRow(0)
    window.table.item(0, 6).setText("部分接受")
    window.export()
    wait_for_worker(window)
    assert not errors
    assert len(window.output_paths) == 6
    assert not window.dirty
    for source in files:
        path = output / (source.stem + "_评审意见.xlsx")
        assert path.is_file()
        workbook = load_workbook(path)
        sheet = workbook["评审汇总"]
        assert sheet.max_column == 10
        assert sheet["G2"].value == ("部分接受" if source == files[0] else None)
        workbook.close()
        assert source.read_bytes() == originals[source]
    window.clear_files()
    assert window.table.rowCount() == 0
    assert window.results == []
    window.close()


def test_folder_import_accepts_all_supported_formats(application, tmp_path, monkeypatch):
    create_samples(tmp_path)
    (tmp_path / "~$temporary.docx").write_text("skip")
    from commentextract.extract import extract_file
    from commentextract.export import export_result
    export_result(extract_file(tmp_path / "01_Word评审.docx"), tmp_path)
    (tmp_path / "instructions.txt").write_text("skip")
    monkeypatch.setattr("commentextract.app.choose_directory", lambda *args: str(tmp_path))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: QMessageBox.Ok)
    window = MainWindow()
    window.choose_folder()
    wait_for_worker(window)
    assert len(window.results) == 6
    assert all(not result.error for result in window.results)
    window.close()
