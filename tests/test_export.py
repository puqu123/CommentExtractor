from pathlib import Path
from urllib.parse import unquote

import pytest
from openpyxl import load_workbook

from commentextract.extract import extract_file
from commentextract.export import export_result
from commentextract.models import HEADERS, Comment, Extraction, Issue, group_comments
from .samples import make_word


def test_export_schema_validation_and_unique_names(tmp_path):
    result = extract_file(make_word(tmp_path / "来源.docx"))
    result.issues[0].acceptance = "是"
    before = result.source.read_bytes()
    path = export_result(result, tmp_path / "output")
    second = export_result(result, tmp_path / "output")
    assert path.name == "来源_评审意见提取.xlsx"
    assert second.name == "来源_评审意见提取_2.xlsx"
    assert result.source.read_bytes() == before
    workbook = load_workbook(path)
    assert workbook.sheetnames == ["评审汇总", "提取报告"]
    sheet = workbook["评审汇总"]
    assert [c.value for c in sheet[1]] == HEADERS
    assert sheet.max_column == 10
    assert sheet["H2"].value == "是"
    assert sheet.freeze_panes == "A2"
    validation = list(sheet.data_validations.dataValidation)[0]
    assert validation.formula1 == '"是,否,重复"'
    assert validation.showErrorMessage
    assert "答复人乙" in sheet["J2"].value
    assert "补充测试环境和并发数量" in sheet["J2"].value
    workbook.close()


def test_export_literal_formula_long_text_and_controls(tmp_path):
    root = Comment("1", "=HYPERLINK(\"bad\")", "=1+1", context="x" * 40000)
    result = Extraction(tmp_path / "hostile.docx", [Issue("R0001", root)])
    path = export_result(result, tmp_path / "out")
    workbook = load_workbook(path, data_only=False)
    sheet = workbook["评审汇总"]
    assert sheet["F2"].data_type == "s"
    assert sheet["G2"].data_type == "s"
    assert sheet["G2"].value == "=1+1"
    assert (path.parent / unquote(sheet["D2"].hyperlink.target)).read_text(encoding="utf-8") == "x" * 40000
    workbook.close()


def test_failed_extraction_does_not_become_empty_success(tmp_path):
    result = Extraction(tmp_path / "bad.docx", error="failed")
    with pytest.raises(ValueError):
        export_result(result, tmp_path)
    assert not list(tmp_path.glob("*.xlsx"))


def test_orphan_and_cycle_comments_never_disappear():
    warnings = []
    comments = [Comment("a", "A", "a", "b"), Comment("b", "B", "b", "a"),
                Comment("c", "C", "c", "missing")]
    issues = group_comments(comments, warnings)
    assert sum(1 + len(issue.replies) for issue in issues) == 3
    assert warnings
