from io import BytesIO
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from openpyxl import load_workbook
from PIL import Image

from commentextract.developer_word import match_reference, explicit_location
from commentextract.extract import extract_file
from commentextract.export import export_result
from commentextract.merge import merge_results


def picture():
    stream = BytesIO()
    Image.new("RGB", (120, 70), "white").save(stream, format="PNG")
    stream.seek(0)
    return stream


def make_review(path):
    document = Document()
    document.add_paragraph("开发评审说明：以下为虚构测试数据。")
    document.add_paragraph("1、请说明响应时间的测量条件。")
    document.add_picture(picture())
    document.add_picture(picture())
    document.add_paragraph("这是截图之后的补充意见，不要拆成另一条。")
    document.add_paragraph("2、请补充表格中的单位。")
    document.add_picture(picture())
    document.add_paragraph("3、这条没有截图，也必须保留。")
    document.save(path)
    return path


def test_numbered_review_images_continuation_and_reference(tmp_path, monkeypatch):
    review = make_review(tmp_path / "开发评审.docx")
    original = Document()
    original.add_heading("3.2 接口设计", level=1)
    original.add_paragraph("接口响应时间不超过 2 秒，并记录处理结果。")
    reference = tmp_path / "原始文档.docx"
    original.save(reference)

    def recognize(images, warnings):
        assert len(images) == 3
        images[0].ocr_text = "Page 1 2\n3.2 接口设计\n接口响应时间不超过 2 秒"
        images[1].ocr_text = "接口响应时间不超过 2 秒"
        images[2].ocr_text = "表 2-1 样本数量统计"
    monkeypatch.setattr("commentextract.ocr.recognize_images", recognize)
    before = review.read_bytes()
    result = extract_file(review, developer=True, reviewer="开发甲", reference=reference)
    assert not result.error
    assert len(result.issues) == 3
    first, second, third = [i.root for i in result.issues]
    assert first.author == "开发甲"
    assert "第 12 页" in first.location and "OCR" in first.location
    assert "补充意见" in first.text
    assert len(first.screenshots) == 2
    assert "原文匹配候选" in first.context
    assert "图表标题候选：表 2-1" in second.location
    assert third.location.startswith("位置未确定")
    assert not third.screenshots
    assert any("首条编号前" in w for w in result.warnings)
    assert not extract_file(review).issues  # no heuristic conversion in ordinary mode
    output = export_result(result, tmp_path / "output")
    workbook = load_workbook(output)
    assert workbook.sheetnames == ["评审汇总", "提取报告"]
    sheet = workbook["评审汇总"]
    assert sheet["E2"].value == "开发甲"
    assert "补充意见" in sheet["F2"].value
    assert sheet["J2"].hyperlink
    images = list(output.parent.glob("*_附件/*.png"))
    assert len(images) == 3
    assert all(image.read_bytes() == first.screenshots[0].data for image in images)
    assert review.read_bytes() == before
    workbook.close()
    merged = merge_results([result, extract_file(review, developer=True, ocr=False)], "合并")
    assert len(merged.issues[0].root.screenshots) == 2


def test_word_automatic_list_and_nested_items(tmp_path):
    document = Document()
    for number in (1, 2):
        p = document.add_paragraph(f"第 {number} 项意见", style="List Number")
        document.add_paragraph("这一段是补充说明。")
        nested = document.add_paragraph("嵌套子项不应另起意见。")
        props = nested._p.get_or_add_pPr()
        numbering = OxmlElement("w:numPr")
        level = OxmlElement("w:ilvl")
        level.set(qn("w:val"), "1")
        numid = OxmlElement("w:numId")
        numid.set(qn("w:val"), "5")
        numbering.extend([level, numid])
        props.append(numbering)
    path = tmp_path / "auto.docx"
    document.save(path)
    result = extract_file(path, developer=True, ocr=False)
    assert not result.error
    assert len(result.issues) == 2
    assert all("嵌套子项" in issue.root.text for issue in result.issues)


def test_no_ocr_or_missing_reference_still_preserves_every_image(tmp_path):
    result = extract_file(make_review(tmp_path / "review.docx"), developer=True,
                          reference=tmp_path / "missing.docx", ocr=False)
    assert not result.error
    assert len(result.issues) == 3
    assert sum(len(i.root.screenshots) for i in result.issues) == 3
    assert all(i.root.author == "" for i in result.issues)
    assert any("原始文档无法读取" in w for w in result.warnings)
    assert any("未指定评审人" in w for w in result.warnings)


def test_no_number_is_explicit_failure_and_ambiguous_reference_not_guessed(tmp_path):
    document = Document()
    document.add_paragraph("普通技术说明，不应抽取为意见。")
    path = tmp_path / "ordinary.docx"
    document.save(path)
    assert "未找到编号意见" in extract_file(path, developer=True, ocr=False).error
    paragraph = "接口响应时间不超过 2 秒"
    location, context = match_reference(paragraph, [(paragraph, "第一章", None), (paragraph, "第二章", None)])
    assert location == "原文存在多处匹配，位置待核对"
    assert context == ""
    assert explicit_location("第 1 2 页") == "第 12 页"
    assert explicit_location("Page 1 2\n3.2 接口设计") == "第 12 页"
    assert explicit_location("3 ． 2 接 口 设 计") == "章节候选：3.2 接口设计"


def test_reference_heading_and_searchable_paragraph_without_fabricated_page(tmp_path, monkeypatch):
    review = make_review(tmp_path / "review.docx")
    document = Document()
    document.add_heading("4.1 处理规则", level=1)
    document.add_paragraph("接口响应时间不超过 2 秒")
    reference = tmp_path / "original.docx"
    document.save(reference)

    def recognize(images, warnings):
        images[0].ocr_text = "接口响应时间不超过 2 秒"
    monkeypatch.setattr("commentextract.ocr.recognize_images", recognize)
    result = extract_file(review, developer=True, reference=reference)
    assert not result.error
    assert "4.1 处理规则" in result.issues[0].root.location
    assert "搜索" in result.issues[0].root.location
    assert "页" not in result.issues[0].root.location


def test_standard_word_uses_heading_and_quote_not_paragraph_number(tmp_path):
    document = Document()
    document.add_heading("3 接口设计", level=1)
    p = document.add_paragraph()
    run = p.add_run("接口响应时间不超过 2 秒")
    document.add_comment(run, "请补充条件", "评审甲")
    path = tmp_path / "standard.docx"
    document.save(path)
    result = extract_file(path)
    assert not result.error
    location = result.issues[0].root.location
    assert "3 接口设计" in location
    assert "搜索“接口响应时间不超过 2 秒”" in location
    assert "第 2 段" not in location and "页" not in location


def test_developer_ui_import_and_readonly_screenshot_viewer(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QDialog, QScrollArea
    from commentextract.app import MainWindow
    from .test_app import wait_for_worker
    application = QApplication.instance() or QApplication([])
    source = make_review(tmp_path / "review.docx")
    monkeypatch.setattr("commentextract.app.choose_developer_files", lambda parent:
                        ([str(source)], {"developer": True, "reviewer": "开发甲", "ocr": False}))
    window = MainWindow()
    window.choose_developer()
    wait_for_worker(window)
    assert len(window.results[0].issues) == 3
    assert not window.table.isColumnHidden(9)
    window.open_cell_text(0, 9)
    reader = window.findChild(QDialog, "cellTextDialog")
    assert reader.findChild(QScrollArea) is not None
    assert len(list(Path(reader.screenshot_temp.path()).glob("*.png"))) == 2
    reader.close()
    window.close()
