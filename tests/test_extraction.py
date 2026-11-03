from zipfile import ZipFile

import pytest

from commentextract.extract import extract_file
from .samples import make_word, make_excel, make_powerpoint, patch_zip


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
    assert issue.root.location == "检查表 · B2"
    assert issue.root.author == "评审人甲"
    assert len(issue.replies) == (1 if threaded else 0)
    assert "占位" not in issue.root.text
    if threaded:
        assert issue.replies[0].author == "答复人乙"
        assert issue.replies[0].location == "检查表 · B2"


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


def test_corrupt_and_unsupported_are_errors(tmp_path):
    invalid = tmp_path / "bad.docx"
    invalid.write_text("not a zip")
    assert extract_file(invalid).error
    assert extract_file(tmp_path / "old.doc").error


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
