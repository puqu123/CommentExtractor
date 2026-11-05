"""User-reported batch, source tracing, Excel anchor and file-browser regressions."""
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from openpyxl import load_workbook
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QDialog, QPlainTextEdit
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest

from commentextract.app import MainWindow
from commentextract.dialogs import choose_files
from commentextract.excel import cell_range
from commentextract.extract import extract_file
from commentextract.export import export_result
from commentextract.inputs import collect_files
from commentextract.models import HEADERS
from .samples import S, create_samples, make_excel, make_word, patch_zip
from .test_app import wait_for_worker


@pytest.fixture
def notices(monkeypatch):
    application = QApplication.instance() or QApplication([])
    messages = []
    for kind in ("warning", "information"):
        monkeypatch.setattr(QMessageBox, kind, lambda *args: messages.append(args[-1]))
    return application, messages


@pytest.mark.parametrize("threaded", [False, True])
def test_excel_merged_address_and_long_content_remain_traceable(tmp_path, threaded, notices):
    source = make_excel(tmp_path / "review.xlsx", threaded=threaded)
    content = "这一段是待评审的合并单元格内容。" * 30 + "全文末尾可搜索"
    patch_zip(source, {"xl/worksheets/sheet1.xml": f'<worksheet xmlns="{S}"><sheetData><row r="2"><c r="B2" t="inlineStr"><is><t>{content}</t></is></c></row></sheetData><mergeCells count="1"><mergeCell ref="B2:D3"/></mergeCells></worksheet>'})
    result = extract_file(source)
    assert not result.error
    assert result.issues[0].root.location == "检查表 · B2:D3"
    assert result.issues[0].root.context == content
    window = MainWindow()
    window.add_result(result)
    assert window.table.item(0, 3).text().endswith(".....")
    assert len(window.table.item(0, 3).text()) < len(content)
    window.show()
    item = window.table.item(0, 3)
    window.table.scrollToItem(item)
    notices[0].processEvents()
    point = window.table.visualItemRect(item).center()
    QTest.mouseClick(window.table.viewport(), Qt.LeftButton, Qt.NoModifier, point)
    QTest.mouseDClick(window.table.viewport(), Qt.LeftButton, Qt.NoModifier, point)
    reader = window.findChild(QDialog, "cellTextDialog")
    assert reader.findChild(QPlainTextEdit).toPlainText() == content
    assert reader.findChild(QPlainTextEdit).isReadOnly()
    reader.close()
    window.search.setText("全文末尾可搜索")
    assert not window.table.isRowHidden(0)
    workbook = load_workbook(export_result(result, tmp_path / "out"))
    assert workbook["评审汇总"]["D2"].value == content
    assert workbook["评审汇总"]["C2"].value == "检查表 · B2:D3"
    workbook.close()
    window.close()


def test_range_normalization_and_multi_cell_excerpt(tmp_path):
    assert cell_range("$B$3:$A$2")[0] == "A2:B3"
    source = make_excel(tmp_path / "range.xlsx")
    from zipfile import ZipFile
    with ZipFile(source) as package:
        comment_part = next(p for p in package.namelist() if p.endswith("comment1.xml"))
        comments = package.read(comment_part).decode().replace('ref="B2"', 'ref="A2:B2"')
    patch_zip(source, {comment_part: comments})
    result = extract_file(source)
    assert not result.error
    assert result.issues[0].root.location == "检查表 · A2:B2"
    assert result.issues[0].root.context == "A2：样本数量\nB2：100"


def test_filename_does_not_silently_filter_source(tmp_path):
    source = make_excel(tmp_path / "原始_评审意见提取.xlsx")
    generated = export_result(extract_file(source), tmp_path)
    corrupt = tmp_path / "损坏_评审意见提取.xlsx"
    corrupt.write_bytes(b"invalid")
    pdf = tmp_path / "removed.pdf"
    pdf.write_bytes(b"not supported")
    files, skipped = collect_files([source, generated, corrupt, pdf, source])
    assert files == [source.resolve(), corrupt.resolve()]
    assert any(p == generated and "导出表" in reason for p, reason in skipped)
    assert any(p == pdf and "不支持" in reason for p, reason in skipped)
    assert any(p == source and "重复" in reason for p, reason in skipped)
    assert "PDF" in extract_file(pdf).error


def test_six_inputs_one_corrupt_reports_exact_missing_file(tmp_path, notices, monkeypatch):
    create_samples(tmp_path / "input")
    files = sorted((tmp_path / "input").iterdir())
    files[-1].write_bytes(b"broken review document")
    output = tmp_path / "out"
    monkeypatch.setattr("commentextract.app.choose_directory", lambda *args: str(output))
    window = MainWindow()
    window.add_files(files)
    wait_for_worker(window)
    assert len(window.results) == 6
    assert sum(bool(r.error) for r in window.results) == 1
    assert any(files[-1].name in message for message in notices[1])
    window.export()
    wait_for_worker(window)
    assert len(window.output_paths) == 5
    assert "成功 5 份" in window.status.text()
    assert "1 份源文件提取失败" in window.status.text()
    report = window.report_text()
    assert not list(output.glob("批量导出结果_*.txt"))
    assert all(str(p) in report for p in files)
    assert "BadZipFile" in report
    window.close()


def test_twelve_same_stem_inputs_have_twelve_outputs(tmp_path, notices, monkeypatch):
    # This test covers batch naming, not Word pagination. Real Word startup for
    # twelve synthetic files exceeds the GUI test's short worker deadline.
    monkeypatch.setattr("commentextract.word_layout.read_layout", lambda *args, **kwargs: ([], None))
    files = []
    for index in range(12):
        directory = tmp_path / str(index)
        directory.mkdir()
        files.append(make_word(directory / "同名文件.docx"))
    output = tmp_path / "out"
    monkeypatch.setattr("commentextract.app.choose_directory", lambda *args: str(output))
    window = MainWindow()
    window.add_files(files)
    wait_for_worker(window)
    assert len(window.results) == 12
    window.export()
    wait_for_worker(window)
    assert len(set(window.output_paths)) == 12
    assert len(list(output.glob("*.xlsx"))) == 12
    window.close()


def test_single_write_failure_does_not_stop_batch(tmp_path, notices, monkeypatch):
    create_samples(tmp_path / "input")
    files = sorted((tmp_path / "input").iterdir())
    window = MainWindow()
    for source in files:
        window.add_result(extract_file(source))
    output = tmp_path / "out"
    monkeypatch.setattr("commentextract.app.choose_directory", lambda *args: str(output))

    def fail_one(result, directory):
        if result.source == files[1]:
            raise PermissionError("模拟目录不可写")
        return export_result(result, directory)

    monkeypatch.setattr("commentextract.export.export_result", fail_one)
    window.export()
    wait_for_worker(window)
    assert len(window.output_paths) == 5
    assert "导出失败 1 份" in window.status.text()
    report = window.report_text()
    assert not list(output.glob("批量导出结果_*.txt"))
    assert files[1].name in report and "PermissionError" in report
    assert len(list(output.glob("*.xlsx"))) == 5
    window.close()


def test_five_file_summary_uses_native_save_api_and_source_column(tmp_path, notices, monkeypatch):
    window = MainWindow()
    files = [make_word(tmp_path / f"A_rev by {i}.docx") for i in range(5)]
    for source in files:
        window.add_result(extract_file(source))
    assert all(window.file_list.item(row).checkState() == Qt.Checked for row in range(5))
    assert len(window.results) == 5
    assert "5 份源文件" in window.stat_notes["files"].text()
    output = tmp_path / "合并导出"
    output.mkdir()

    def select_file(parent, title, suggested, filters, options):
        assert parent is window
        assert "汇总导出" in title
        assert suggested == "A_评审意见提取.xlsx"
        assert filters == "Excel 文件 (*.xlsx)"
        assert options & QFileDialog.DontConfirmOverwrite
        assert not options & QFileDialog.DontUseNativeDialog
        return str(output / "A.xlsx"), filters

    monkeypatch.setattr(QFileDialog, "getSaveFileName", select_file)
    window.export_summary()
    wait_for_worker(window)
    assert len(window.output_paths) == 1
    assert len(window.results) == 5
    workbook = load_workbook(window.output_paths[0])
    sheet = workbook["评审汇总"]
    assert [c.value for c in sheet[1]] == HEADERS
    assert [sheet.cell(r, 2).value for r in range(2, 7)] == [p.name for p in files]
    assert sheet.max_row == 6
    assert "G2:G6" in str(list(sheet.data_validations.dataValidation)[0].sqref)
    assert "!G:G" in workbook["提取报告"]["B4"].value
    workbook.close()
    window.close()


def test_native_multiselect_preserves_all_files_and_cancel(notices, monkeypatch):
    files = ["C:/reviews/A.docx", "C:/reviews/B.xlsx", "C:/reviews/C.pptx"]
    calls = []

    def select(parent, title, directory, filters):
        calls.append(filters)
        return (files if len(calls) == 1 else []), filters

    monkeypatch.setattr(QFileDialog, "getOpenFileNames", select)
    assert choose_files(None) == files
    assert all(ext in calls[0] for ext in ("*.docx", "*.xlsx", "*.pptx"))
    assert choose_files(None) == []


def test_many_merge_warnings_cannot_collapse_table_at_minimum_window_size(tmp_path, notices):
    from commentextract.models import Comment, Extraction, Issue
    from PySide6.QtWidgets import QHeaderView
    window = MainWindow()
    window.resize(1100, 720)
    result = Extraction(tmp_path / "合并方案.review", sources=[tmp_path / f"review-{i}.pptx" for i in range(5)])
    result.issues = [Issue(f"R{i:04d}", Comment(str(i), "评审人", "请核对单位。"), source=result.sources[i % 5])
                     for i in range(20)]
    result.warnings = [f"review-{i}.pptx：这是较长的格式提示，用来确认提示不会挤占评审表格。" for i in range(100)]
    window.add_result(result)
    window.show()
    notices[0].processEvents()
    assert not hasattr(window, "detail")
    assert window.table.viewport().height() >= 250
    assert window.table.rowAt(100) >= 0
    opinion_column = HEADERS.index("评审意见")
    assert window.table.columnViewportPosition(opinion_column) < window.table.viewport().width()
    window.table.scrollToItem(window.table.item(0, opinion_column))
    assert window.table.columnViewportPosition(opinion_column) + window.table.columnWidth(opinion_column) <= window.table.viewport().width()
    assert window.message.height() <= window.message.fontMetrics().height() * 2
    assert window.table.verticalHeader().isVisible()
    assert window.table.verticalHeader().sectionResizeMode(0) == QHeaderView.Interactive
    header = window.table.verticalHeader()
    surface = header.viewport()
    before = header.sectionSize(0)
    start = QPoint(surface.width() // 2, header.sectionViewportPosition(0) + before - 2)
    end = start + QPoint(0, 65)
    QTest.mousePress(surface, Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(surface, end, 30)
    QTest.mouseRelease(surface, Qt.LeftButton, Qt.NoModifier, end)
    assert header.sectionSize(0) > before + 40
    assert "review-99.pptx" in window.report_text()
    window.close()
