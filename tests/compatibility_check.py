"""Assertions shared by pytest, synthetic reports and real-file manifests."""
import hashlib
from pathlib import Path
from urllib.parse import unquote

from openpyxl import load_workbook

from commentextract.extract import extract_file
from commentextract.export import export_result
from commentextract.models import HEADERS


def check_case(case, output, exporter=None):
    digest = hashlib.sha256(case.source.read_bytes()).hexdigest()
    result = extract_file(case.source, **case.options)
    assert hashlib.sha256(case.source.read_bytes()).hexdigest() == digest, "提取修改了源文件"
    if case.kind == "negative":
        assert case.error_contains and case.error_contains in result.error, f"预期明确失败，实际：{result.error!r}"
        return result, None
    assert not result.error, result.error
    assert len(result.issues) == len(case.expected), f"主意见数预期 {len(case.expected)}，实际 {len(result.issues)}"
    assert len({i.id for i in result.issues}) == len(result.issues), "导出意见编号重复"
    for index, (issue, expected) in enumerate(zip(result.issues, case.expected), 1):
        assert issue.root.author == expected["reviewer"], f"第{index}条作者错误：{issue.root.author!r}"
        assert issue.root.text == expected["opinion"], f"第{index}条意见文字错误：{issue.root.text[:160]!r}"
        replies = [(r.author, r.text) for r in issue.replies]
        assert replies == [tuple(r) for r in expected.get("replies", [])], f"第{index}条回复错误：{replies!r}"
        if "context" in expected:
            assert issue.root.context == expected["context"], f"第{index}条选区／单元格内容错误：{issue.root.context!r}"
        if "location_contains" in expected:
            assert expected["location_contains"] in issue.root.location, f"第{index}条定位错误：{issue.root.location!r}"
    for fragment in case.warning_contains:
        assert any(fragment in w for w in result.warnings), f"缺少恢复提示：{fragment}"
    if case.kind == "recovery":
        assert result.warnings, "恢复用例必须提供警告"
    target = (exporter or export_result)(result, output)
    workbook = load_workbook(target)
    try:
        assert workbook.sheetnames == ["评审汇总", "提取报告"]
        sheet = workbook["评审汇总"]
        assert [c.value for c in sheet[1]] == HEADERS
        assert sheet.max_row == len(case.expected) + 1

        def exported_text(row, column):
            cell = sheet.cell(row, column)
            if cell.hyperlink and cell.hyperlink.target.endswith(".txt"):
                return (target.parent / unquote(cell.hyperlink.target)).read_text(encoding="utf-8")
            return cell.value or ""

        for row, expected in enumerate(case.expected, 2):
            for column, value in [(2, case.source.name), (5, expected["reviewer"]), (6, expected["opinion"])]:
                assert exported_text(row, column) == value, f"Excel 第{row}行第{column}列未完整保留文字"
            if "context" in expected:
                assert exported_text(row, 4) == expected["context"], f"Excel 第{row}行未完整保留对应内容"
            expected_reply = "\n\n".join(f"{i}. {author or '未署名'}：{body}" for i, (author, body) in enumerate(expected.get("replies", []), 1))
            assert exported_text(row, 9) == expected_reply
            assert sheet.cell(row, 7).value is None, "不应自动填写是否接受"
    finally:
        workbook.close()
    assert hashlib.sha256(case.source.read_bytes()).hexdigest() == digest, "导出修改了源文件"
    return result, target
