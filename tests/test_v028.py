"""Production regressions and the optional offline export features."""
from io import BytesIO
from zipfile import ZipFile

from openpyxl import load_workbook
from PIL import Image
import pytest

from commentextract.extract import extract_file
from commentextract.export import export_result
from commentextract.models import Comment, Extraction, Issue, Screenshot
from commentextract.word_layout import add_pages
from .samples import make_excel, make_word, patch_zip, REL


def png(color, size=(800, 400)):
    stream = BytesIO()
    Image.new("RGB", size, color).save(stream, format="PNG")
    return stream.getvalue()


@pytest.mark.parametrize("part", ["xl/workbook.xml", "xl/worksheets/sheet1.xml"])
def test_excel_new_ancillary_extension_without_fallback_preserves_threads(tmp_path, part):
    source = make_excel(tmp_path / "new-extension.xlsx", threaded=True)
    with ZipFile(source) as package:
        xml = package.read(part).decode("utf-8")
    end = xml.rfind("</")
    extension = ('<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
                 'xmlns:new="urn:future-office-extension"><mc:Choice Requires="new">'
                 '<new:layout feature="future"/></mc:Choice></mc:AlternateContent>')
    patch_zip(source, {part: xml[:end] + extension + xml[end:]})
    before = source.read_bytes()
    result = extract_file(source)
    assert not result.error
    assert result.comment_count == 2
    assert result.issues[0].root.text == "请核实样本数量。"
    assert result.issues[0].replies[0].text == "已核实，数量为 100。"
    assert any("兼容恢复" in warning for warning in result.warnings)
    from commentextract.support import warning_codes
    assert warning_codes(result.warnings)["CE-W203"]
    assert source.read_bytes() == before


@pytest.mark.parametrize("mode", ["both", "text", "images"])
def test_image_modes_keep_review_and_replies_and_readable_gallery(tmp_path, mode):
    root = Comment("1", "A", "评审正文", context="已识别截图文字", screenshots=[Screenshot("a.png", png("red"))])
    reply = Comment("2", "B", "回复正文", "1", screenshots=[Screenshot("b.png", png("blue"))])
    result = Extraction(tmp_path / "原文件.docx", [Issue("R0001", root, [reply])])
    path = export_result(result, tmp_path / mode, content_mode=mode)
    workbook = load_workbook(path)
    sheet = workbook["评审汇总"]
    assert sheet["F2"].value == "评审正文"
    assert "回复正文" in sheet["I2"].value
    assert sheet.row_dimensions[2].height == 60
    assert sheet["D2"].value == (None if mode == "images" else "已识别截图文字")
    if mode == "text":
        assert sheet["J2"].value is None
        assert not sheet._images
        assert not list(path.parent.glob("*_附件"))
    else:
        assert len(sheet._images) == 1
        assert sheet["J2"].value == "查看截图（2张）"
        preview = path.parent / sheet["J2"].hyperlink.target
        with Image.open(preview) as gallery:
            assert gallery.size == (800, 820)  # linked image retains original detail
        originals = sorted(p for p in preview.parent.glob("*.png") if not p.name.endswith("_预览.png"))
        assert [p.read_bytes() for p in originals] == [root.screenshots[0].data, reply.screenshots[0].data]
    workbook.close()


def test_word_comment_and_reply_images_are_kept(tmp_path):
    source = make_word(tmp_path / "images.docx")
    with ZipFile(source) as package:
        comments = package.read("word/comments.xml").decode("utf-8")
    # Add both a DrawingML root-comment picture and a VML reply picture.
    from xml.etree import ElementTree as ET
    from .samples import W, A, OREL
    root = ET.fromstring(comments)
    for index, node in enumerate(root, 1):
        p = ET.SubElement(node, "{" + W + "}p")
        tag = "{" + A + "}blip" if index == 1 else "{urn:schemas-microsoft-com:vml}imagedata"
        key = "embed" if index == 1 else "id"
        ET.SubElement(p, tag, {"{" + OREL + "}" + key: f"pic{index}"})
    rels = f'<Relationships xmlns="{REL}">'
    for index in (1, 2):
        rels += f'<Relationship Id="pic{index}" Type="{OREL}/image" Target="media/image{index}.png"/>'
    rels += '</Relationships>'
    patch_zip(source, {"word/comments.xml": ET.tostring(root), "word/_rels/comments.xml.rels": rels,
                       "word/media/image1.png": png("red"), "word/media/image2.png": png("blue")})
    result = extract_file(source)
    assert not result.error
    assert len(result.issues) == 1 and result.comment_count == 2
    assert len(result.issues[0].screenshots) == 2


def test_every_reused_passage_gets_its_own_page():
    locations = '原文匹配 · 6.1 校验 · 搜索“请校验软件安装包的MD5值”\n原文匹配 · 8.2 升级 · 搜索“请校验软件安装包的MD5值”'
    paragraphs = [dict(text="请校验软件安装包的MD5值", heading="6.1 校验", page=5),
                  dict(text="请校验软件安装包的MD5值", heading="8.2 升级", page=12)]
    value = add_pages(locations, "请校验软件安装包的MD5值", paragraphs).splitlines()
    assert value[0].endswith("（第 5 页）")
    assert value[1].endswith("（第 12 页）")
    assert "页码未获取" in add_pages('正文 · 搜索“找不到的短句”', "", paragraphs)


def test_legacy_doc_conversion_never_changes_original(tmp_path, monkeypatch):
    converted = make_word(tmp_path / "converted.docx").read_bytes()
    source = tmp_path / "old.doc"
    source.write_bytes(b"synthetic legacy fixture, conversion mocked")
    before = source.read_bytes()
    monkeypatch.setattr("commentextract.word_layout.read_layout", lambda path, convert=False: ([], converted))
    result = extract_file(source)
    assert not result.error and result.comment_count == 2
    assert result.source == source
    assert result.issues[0].source == source
    assert result.diagnostics["packages"][0]["role"] == "source"
    assert source.read_bytes() == before


def test_page_failure_and_missing_original_keep_comments(tmp_path, monkeypatch):
    source = make_word(tmp_path / "new.docx")
    def unavailable(*args, **kwargs):
        raise RuntimeError("需要本机已安装且可正常使用的 Microsoft Word；转换或页码读取未完成。")
    monkeypatch.setattr("commentextract.word_layout.read_layout", unavailable)
    result = extract_file(source, word_pages=True)
    assert not result.error and result.comment_count == 2
    assert any("保留提取内容" in warning for warning in result.warnings)
    legacy = tmp_path / "old.doc"
    legacy.write_bytes(b"legacy")
    assert "CE-E208" in extract_file(legacy).error
    from .test_developer_word import make_review
    developer = extract_file(make_review(tmp_path / "review.docx"), developer=True, ocr=False, word_pages=True)
    assert not developer.error and len(developer.issues) == 3
    assert any("不会把评审文件的页码" in warning for warning in developer.warnings)


def test_progress_emits_intermediate_stages(tmp_path):
    updates = []
    result = extract_file(make_word(tmp_path / "progress.docx"), progress=lambda percent, text: updates.append((percent, text)))
    assert not result.error
    assert updates[-1][0] == 100
    assert any(0 < percent < 100 for percent, _ in updates)
    assert all(text for _, text in updates)


def test_progress_resets_for_the_next_batch_with_same_size(monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from commentextract.app import MainWindow, Worker
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.update_progress(100, 100, "上一批完成")
    monkeypatch.setattr(Worker, "start", lambda self: None)
    worker = Worker(["next.docx"], parent=window)
    window.start_worker(worker)
    assert window.progress.value() == 0
    window.update_progress(25, 100, "读取结构")
    assert window.progress.value() == 25
    window.update_progress(10, 100, "另一个部件")
    assert window.progress.value() == 25
    window.worker = None
    window.close()


def test_rapidocr_uses_bundled_models_without_network(monkeypatch):
    pytest.importorskip("rapidocr_onnxruntime")
    from pathlib import Path
    if not Path("C:/Windows/Fonts/msyh.ttc").is_file():
        pytest.skip("Synthetic Chinese screenshot uses a Windows font")
    from scripts.make_developer_samples import screenshot
    import socket
    from commentextract.ocr import recognize_images_rapid
    def network_forbidden(*args, **kwargs):
        raise AssertionError("OCR must not open a network socket")
    monkeypatch.setattr(socket, "socket", network_forbidden)
    monkeypatch.setattr("commentextract.ocr._rapid_engine", None)
    image = Screenshot("local.png", screenshot(["Page 12", "6.1.3 校验 MD5", "安装前请校验软件包的 MD5 值。"] ).getvalue())
    warnings = []
    recognize_images_rapid([image], warnings)
    assert "12" in image.ocr_text and "校验" in image.ocr_text and "MD5" in image.ocr_text
    assert not any("失败" in warning for warning in warnings)


def test_visible_page_does_not_hide_all_reference_matches(tmp_path, monkeypatch):
    from docx import Document
    from .test_developer_word import picture
    original = Document()
    for heading in ("6.1 安装校验", "8.2 升级校验"):
        original.add_heading(heading, 1)
        original.add_paragraph("安装前请校验软件包的MD5值。")
    reference = tmp_path / "manual.docx"
    original.save(reference)
    review = Document(); review.add_paragraph("1、请增加说明。"); review.add_picture(picture())
    path = tmp_path / "review.docx"; review.save(path)
    def recognize(images, warnings):
        images[0].ocr_text = "Page 5\n安装前请校验软件包的MD5值。"
    monkeypatch.setattr("commentextract.ocr.recognize_images", recognize)
    result = extract_file(path, developer=True, reference=reference)
    assert not result.error
    location = result.issues[0].root.location
    assert location.startswith("第 5 页")
    assert "6.1 安装校验" in location and "8.2 升级校验" in location

