from zipfile import ZipFile

import pytest

from commentextract.extract import extract_file
from commentextract.pdf import render_context
from .samples import make_word, make_excel, make_powerpoint, make_pdf, patch_zip


def test_word_selection_and_reply(tmp_path):
    result = extract_file(make_word(tmp_path / "review.docx"))
    assert not result.error
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.root.context == "接口响应时间不超过 2 秒"
    assert issue.root.author == "评审人甲"
    assert issue.root.location.startswith("正文")
    assert len(issue.replies) == 1
    assert issue.replies[0].author == "答复人乙"
    assert "测量条件" in issue.root.text
    assert "接受" not in issue.root.text
    assert issue.acceptance == ""


@pytest.mark.parametrize("threaded", [False, True])
def test_excel_location_value_and_thread(tmp_path, threaded):
    result = extract_file(make_excel(tmp_path / "review.xlsx", threaded))
    assert not result.error
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.root.context == "100"
    assert issue.root.location == "检查表!B2"
    assert issue.root.author == "评审人甲"
    assert len(issue.replies) == (1 if threaded else 0)
    assert "占位" not in issue.root.text
    if threaded:
        assert issue.replies[0].author == "答复人乙"
        assert issue.replies[0].location == "检查表!B2"


@pytest.mark.parametrize("modern", [False, True])
def test_powerpoint_thread_and_slide(tmp_path, modern):
    result = extract_file(make_powerpoint(tmp_path / "review.pptx", modern))
    assert not result.error
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.root.location == "第 1 张幻灯片"
    assert issue.root.author == "评审人甲"
    assert issue.root.text == "图表缺少单位。"
    assert len(issue.replies) == (1 if modern else 0)
    if modern:
        assert issue.replies[0].text == "将补充单位。"


@pytest.mark.parametrize("rotated", [False, True])
def test_pdf_highlight_reply_and_floating_note(tmp_path, rotated):
    result = extract_file(make_pdf(tmp_path / "review.pdf", rotated))
    assert not result.error
    assert len(result.issues) == 2
    issue = result.issues[0]
    assert issue.root.context == "two seconds"
    assert len(issue.replies) == 1
    assert issue.replies[0].author == "Responder B"
    assert result.issues[1].root.context == ""
    image = render_context(result.source, issue.root)
    assert image.startswith(b"\x89PNG")
    from PIL import Image
    import io
    preview = Image.open(io.BytesIO(image))
    assert any(r > 180 and g < 80 and b < 80 for r, g, b in preview.getdata())


def test_corrupt_and_unsupported_are_errors(tmp_path):
    invalid = tmp_path / "bad.docx"
    invalid.write_text("not a zip")
    assert extract_file(invalid).error
    assert extract_file(tmp_path / "old.doc").error


def test_pdf_without_annotations_is_distinct_from_failure(tmp_path):
    import fitz
    path = tmp_path / "empty.pdf"
    with fitz.open() as document:
        document.new_page()
        document.save(path)
    result = extract_file(path)
    assert not result.error
    assert result.issues == []
    assert result.warnings


def test_pdf_password_is_reported(tmp_path):
    import fitz
    path = tmp_path / "locked.pdf"
    with fitz.open() as document:
        document.new_page()
        document.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="secret")
    assert "加密" in extract_file(path).error


def test_word_entity_expansion_rejected(tmp_path):
    path = make_word(tmp_path / "entity.docx")
    patch_zip(path, {"word/comments.xml": '<!DOCTYPE x [<!ENTITY payload "expanded">]><comments>&payload;</comments>'})
    assert extract_file(path).error


def test_excel_shared_strings_rich_text_and_formula(tmp_path):
    path = make_excel(tmp_path / "shared.xlsx")
    from .samples import S
    patch_zip(path, {"xl/sharedStrings.xml": f'<sst xmlns="{S}"><si><r><t>样本</t></r><r><t>数量</t></r></si></sst>',
                     "xl/worksheets/sheet1.xml": f'<worksheet xmlns="{S}"><sheetData><row r="2"><c r="B2" t="s"><v>0</v></c></row></sheetData></worksheet>'})
    assert extract_file(path).issues[0].root.context == "样本数量"
