from __future__ import annotations

import os
import re
import tempfile
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter

from .models import HEADERS, ACCEPTANCE, ACCEPTANCE_COLUMN, SCREENSHOT_COLUMN, CONTEXT_COLUMN, IMAGE_EXTENSIONS

INVALID_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def export_result(result, output_dir, filename=None, content_mode="both"):
    """One workbook per source; atomically reserve names and never overwrite."""
    if content_mode not in {"both", "text", "images"}:
        raise ValueError("未知的内容导出方式。")
    if result.error:
        raise ValueError("提取失败的文件不能导出为空意见表：" + result.error)
    from .progress import stage
    stage(5, "准备 Excel 和截图附件")
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if filename is not None:
        if Path(filename).name != filename or not filename.lower().endswith(".xlsx") or re.search(r'[<>:"/\\|?*\x00-\x1f]', filename):
            raise ValueError("请指定有效的 Excel 文件名（.xlsx），不要包含路径或文件名特殊字符。")
        base = Path(filename).stem
    else:
        base = result.source.stem + "_评审意见提取"
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
            issue_mode = issue.root.export_mode if content_mode == "both" else content_mode
            stage(10 + int(70 * (row - 1) / max(1, len(result.issues))), f"整理 Excel 意见 {row-1}/{len(result.issues)}")
            if issue.acceptance not in ACCEPTANCE:
                raise ValueError("是否接受只能填写：是、否、重复，或留空。")
            for column, value in enumerate(issue.values(result.source.name), 1):
                if column == CONTEXT_COLUMN + 1 and issue_mode == "images" and issue.screenshots:
                    value = ""
                set_text(summary.cell(row, column), value)
            if issue.screenshots and issue_mode != "text":
                from PIL import Image as PILImage, ImageOps
                from openpyxl.drawing.image import Image as ExcelImage
                assets.mkdir(exist_ok=True)
                image_names = []
                originals = []
                for index, image in enumerate(issue.screenshots, 1):
                    extension = Path(image.name).suffix.lower()
                    if extension not in IMAGE_EXTENSIONS:
                        extension = ".bin"
                    attachment = assets / f"截图_{row - 1:04d}_{index:02d}{extension}"
                    attachment.write_bytes(image.data)
                    created_assets.append(attachment)
                    image_names.append(attachment.name)
                    try:
                        with PILImage.open(BytesIO(image.data)) as source:
                            originals.append(source.convert("RGB"))
                    except Exception:
                        warnings.append("有截图不能生成缩略图，已保留原始附件。")
                cell = summary.cell(row, HEADERS.index("上下文截图") + 1)
                preview = assets / f"截图_{row - 1:04d}_预览.png"
                if originals:
                    # Preserve readable resolution in the linked preview; only
                    # the separate image embedded in Excel is a tiny thumbnail.
                    width = max(image.width for image in originals)
                    height = sum(image.height + 10 for image in originals)
                    scale = min(1, 16000 / max(width, height), (32_000_000 / (width * height)) ** .5)
                    gallery = PILImage.new("RGB", (max(1, int(width * scale)), max(1, int(height * scale))), "white")
                    offset = 0
                    for image in originals:
                        tile = ImageOps.contain(image, (max(1, int(image.width * scale)), max(1, int(image.height * scale))))
                        gallery.paste(tile, (0, offset))
                        offset += tile.height + max(1, int(10 * scale))
                    gallery.save(preview)
                    created_assets.append(preview)
                    thumbnail_data = BytesIO()
                    ImageOps.contain(gallery, (170, 52)).save(thumbnail_data, format="PNG")
                    thumbnail_data.seek(0)
                    thumbnail = ExcelImage(thumbnail_data)
                    from openpyxl.drawing.spreadsheet_drawing import OneCellAnchor, AnchorMarker
                    from openpyxl.drawing.xdr import XDRPositiveSize2D
                    thumbnail.anchor = OneCellAnchor(_from=AnchorMarker(col=SCREENSHOT_COLUMN, row=row-1, rowOff=20*9525),
                                                    ext=XDRPositiveSize2D(int(thumbnail.width*9525), int(thumbnail.height*9525)))
                    summary.add_image(thumbnail)
                set_text(cell, f"查看截图（{len(image_names)}张）")
                link = preview if originals else assets / image_names[0]
                cell.hyperlink = link.relative_to(output_dir).as_posix()
                for image in originals:
                    image.close()
            elif issue_mode == "text":
                set_text(summary.cell(row, SCREENSHOT_COLUMN + 1), "")
        validation = DataValidation(type="list", formula1='"' + ",".join(ACCEPTANCE[1:]) + '"', allow_blank=True)
        validation.errorTitle = "请选择接受情况"
        validation.error = "请选择：是、否、重复；也可以留空。"
        validation.showErrorMessage = True
        validation.errorStyle = "stop"
        summary.add_data_validation(validation)
        acceptance_letter = get_column_letter(ACCEPTANCE_COLUMN + 1)
        validation.add(f"{acceptance_letter}2:{acceptance_letter}{max(2, summary.max_row)}")
        report = workbook.create_sheet("提取报告")
        report.append(["项目", "结果"])
        partial = any(w.startswith("部分提取：") for w in warnings)
        status = "部分提取（存在未读取部件，请核对）" if partial else ("提取完成（有提示，请核对完整性）" if warnings else "提取完成")
        report.append(["处理结果", status if result.issues else "未发现可读取批注"])
        report.append(["主意见数量", len(result.issues)])
        report.append(["重复意见数量", f'=COUNTIF(\'评审汇总\'!{acceptance_letter}:{acceptance_letter},"重复")'])
        report.append(["去除已标记重复的意见数量", "=B3-B4"])
        workbook.calculation.fullCalcOnLoad = True
        workbook.calculation.forceFullCalc = True
        workbook.calculation.calcMode = "auto"
        report.append(["回复数量", result.comment_count - len(result.issues)])
        report.append(["使用说明", "是否接受留空待填写；同一问题首次计入意见，后续相同意见人工标记为重复。回复人仅表示回复作者。"])
        report.append(["统计说明", "重复数和去重后的数量使用公式，Excel 打开后自动计算；同一问题后续各行标记为重复，首次出现的行保留原接受情况。"])
        report.append(["附件说明", "如有 TXT 或截图，请将 Excel 和同名附件目录一起移动。截图列显示缩略图，点击单元格顶部的文字链接可打开该条意见的全部截图预览；原始图片也按意见顺序保存在附件目录。普通 .xlsx 不含双击放大宏。"])
        for warning in dict.fromkeys(warnings):
            report.append(["提示", ""])
            set_text(report.cell(report.max_row, 2), warning)
        if result.sources:
            report.append(["汇总源文件数", len(result.sources)])
            for source in result.sources:
                report.append(["汇总来源文件", ""])
                set_text(report.cell(report.max_row, 2), str(source))
            report.append(["意见来源", "原始评审返回文件"])
            for issue in result.issues:
                row = report.max_row + 1
                set_text(report.cell(row, 1), issue.id)
                set_text(report.cell(row, 2), str(issue.source or result.source))
        source_types = {Path(p).suffix.lower() for p in (result.sources or [result.source])}
        location_width = 16 if source_types == {".xlsx"} else 32
        widths = {"评审汇总": [14, 38, location_width, 48, 18, 16, 52, 16, 22, 60], "提取报告": [22, 100]}
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
                sheet.row_dimensions[row[0].row].height = 60 if sheet != report else 42
            for index, width in enumerate(widths[sheet.title], 1):
                sheet.column_dimensions[get_column_letter(index)].width = width
        fd, name = tempfile.mkstemp(suffix=".xlsx", dir=str(output_dir))
        os.close(fd)
        tempfile_path = Path(name)
        stage(90, "写入 Excel 文件")
        workbook.save(tempfile_path)
        os.replace(tempfile_path, target)
        stage(100, "Excel 导出完成")
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
