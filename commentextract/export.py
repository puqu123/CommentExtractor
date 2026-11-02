from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from urllib.parse import quote

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter

from .models import HEADERS, ACCEPTANCE

INVALID_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def export_result(result, output_dir, screenshots=True):
    """One workbook per source; atomically reserve names and never overwrite."""
    if result.error:
        raise ValueError("提取失败的文件不能导出为空意见表：" + result.error)
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    base = result.source.stem + "_评审意见"
    counter = 1
    while True:
        suffix = "" if counter == 1 else f"_{counter}"
        target = output_dir / f"{base}{suffix}.xlsx"
        try:
            with target.open("xb"):
                pass
            break
        except FileExistsError:
            counter += 1
    assets = output_dir / (target.stem + "_附件")
    # Existing adjacent assets may belong to an earlier moved/deleted workbook.
    if assets.exists():
        import uuid
        assets = output_dir / (target.stem + "_附件_" + uuid.uuid4().hex[:8])
    warnings = list(result.warnings)
    created_assets = []
    tempfile_path = None
    workbook = Workbook()
    summary = workbook.active
    summary.title = "评审汇总"
    summary.append(HEADERS)

    def set_text(cell, value):
        value = "" if value is None else str(value)
        clean = INVALID_XML.sub("\ufffd", value)
        if len(clean) > 32767 or clean != value:
            assets.mkdir(exist_ok=True)
            attachment = assets / f"文本_{cell.parent.title}_{cell.coordinate}.txt"
            attachment.write_text(value, encoding="utf-8")
            created_assets.append(attachment)
            relative = attachment.relative_to(output_dir).as_posix()
            clean = clean[:1500] + "\n〔完整原文见此单元格链接的 TXT 附件〕"
            cell.hyperlink = quote(relative, safe="/")
            warnings.append("有超长文字或特殊控制字符，完整原文已保存到 TXT 附件，请与 Excel 一同保留。")
        cell.value = clean
        # Treat all document-origin strings as literal text, including '=...', '+...'.
        cell.data_type = "s"

    try:
        for row, issue in enumerate(result.issues, 2):
            if issue.acceptance not in ACCEPTANCE:
                raise ValueError("是否接受只能填写：是、否、部分接受、重复，或留空。")
            screenshot = None
            source = issue.source or result.source
            if screenshots and source.suffix.lower() == ".pdf":
                try:
                    from .pdf import render_context
                    image = render_context(source, issue.root)
                    if image:
                        assets.mkdir(exist_ok=True)
                        screenshot = assets / f"{issue.id}.png"
                        screenshot.write_bytes(image)
                        created_assets.append(screenshot)
                except Exception as exc:
                    warnings.append(f"{issue.id} 截图未生成：{exc}")
            for column, value in enumerate(issue.values("查看截图" if screenshot else ""), 1):
                set_text(summary.cell(row, column), value)
            if screenshot:
                summary.cell(row, 9).hyperlink = quote(screenshot.relative_to(output_dir).as_posix(), safe="/")
                summary.cell(row, 9).style = "Hyperlink"
        validation = DataValidation(type="list", formula1='"是,否,部分接受,重复"', allow_blank=True)
        validation.errorTitle = "请选择接受情况"
        validation.error = "请选择：是、否、部分接受、重复；也可以留空。"
        validation.showErrorMessage = True
        validation.errorStyle = "stop"
        summary.add_data_validation(validation)
        validation.add(f"F2:F{max(2, summary.max_row)}")
        report = workbook.create_sheet("提取报告")
        report.append(["项目", "结果"])
        report.append(["处理结果", "提取完成" if result.issues else "未发现可读取批注"])
        report.append(["主意见数量", len(result.issues)])
        report.append(["重复意见数量", '=COUNTIF(\'评审汇总\'!F:F,"重复")'])
        report.append(["去除已标记重复的意见数量", "=B3-B4"])
        workbook.calculation.fullCalcOnLoad = True
        workbook.calculation.forceFullCalc = True
        workbook.calculation.calcMode = "auto"
        report.append(["回复数量", result.comment_count - len(result.issues)])
        report.append(["使用说明", "是否接受留空待填写；同一问题首次计入意见，后续相同意见人工标记为重复。回复人仅表示回复作者。"])
        report.append(["统计说明", "重复数和去重后的数量使用公式，Excel 打开后自动计算；同一问题后续各行标记为重复，首次出现的行保留原接受情况。"])
        report.append(["附件说明", "如有截图或 TXT，请将 Excel 和同名附件目录一起移动。"])
        for warning in dict.fromkeys(warnings):
            report.append(["提示", ""])
            set_text(report.cell(report.max_row, 2), warning)
        if result.sources:
            report.append(["意见来源", "原始评审返回文件"])
            for issue in result.issues:
                row = report.max_row + 1
                set_text(report.cell(row, 1), issue.id)
                set_text(report.cell(row, 2), str(issue.source or result.source))
        widths = {"评审汇总": [14, 28, 48, 16, 52, 16, 22, 60, 18], "提取报告": [22, 100]}
        for sheet in workbook:
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            sheet.sheet_view.zoomScale = 90
            sheet.row_dimensions[1].height = 30
            for cell in sheet[1]:
                cell.font = Font(name="微软雅黑", color="FFFFFF", bold=True, size=11)
                cell.fill = PatternFill("solid", fgColor="193652")
                cell.alignment = Alignment(vertical="center", wrap_text=True)
            for row in sheet.iter_rows(min_row=2):
                for cell in row:
                    cell.font = Font(name="微软雅黑", size=11, color="176B8A" if cell.hyperlink else "243447")
                    cell.alignment = Alignment(vertical="top", wrap_text=True)
                    cell.fill = PatternFill("solid", fgColor="F0F6FA" if cell.row % 2 == 0 else "FFFFFF")
                sheet.row_dimensions[row[0].row].height = 74 if sheet != report else 42
            for index, width in enumerate(widths[sheet.title], 1):
                sheet.column_dimensions[get_column_letter(index)].width = width
        fd, name = tempfile.mkstemp(suffix=".xlsx", dir=str(output_dir))
        os.close(fd)
        tempfile_path = Path(name)
        workbook.save(tempfile_path)
        os.replace(tempfile_path, target)
        return target
    except Exception:
        target.unlink(missing_ok=True)
        for asset in created_assets:
            asset.unlink(missing_ok=True)
        if assets.exists() and not any(assets.iterdir()):
            assets.rmdir()
        raise
    finally:
        workbook.close()
        if tempfile_path:
            tempfile_path.unlink(missing_ok=True)
