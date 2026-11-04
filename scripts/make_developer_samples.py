"""Generate only fictional numbered reviews and a reproducible PPT regression."""
from pathlib import Path
import sys
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from docx import Document
from docx.shared import Inches
from PIL import Image, ImageDraw, ImageFont
from commentextract import __version__
from tests.samples import P, make_powerpoint, patch_zip


def screenshot(lines):
    image = Image.new("RGB", (1300, 360), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 32)
    for index, line in enumerate(lines):
        draw.text((36, 30 + index * 60), line, font=font, fill="#203447")
    result = BytesIO()
    image.save(result, format="PNG")
    result.seek(0)
    return result


def make_developer_samples(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    source = Document()
    source.add_paragraph("设备启动后应自动记录本次运行的测试环境和样本编号。")
    source.add_heading("3.2 接口设计", level=1)
    source.add_paragraph("接口响应时间不超过两秒，并记录超时后的处理结果。")
    source.add_heading("4.1 数据统计", level=1)
    source.add_paragraph("图 4-1 样本数量统计")
    source.add_paragraph("每次采样应记录测量单位和数据来源。")
    source.save(folder / "01_被评审原文_虚构.docx")
    review = Document()
    review.add_paragraph("虚构开发评审，供本地功能测试。截图中的 Page 12 是测试标签，用来验证 OCR 页码优先级，不代表此短样例的实际排版页数。")
    items = [
        ("1、请补充接口测量条件，下面两张图属于同一意见。", [
            ["Page 12", "3.2 接口设计", "接口响应时间不超过两秒，并记录超时后的处理结果。"],
            ["Page 12", "接口响应时间不超过两秒，并记录超时后的处理结果。"]]),
        ("2、这张图没有页码，应该通过原文匹配到接口设计章节。", [
            ["接口响应时间不超过两秒，并记录超时后的处理结果。"]]),
        ("3、这张图只有图标题，提供章节或图标题定位。", [["图 4-1 样本数量统计"]]),
        ("4、只有纯段落时，应提供可以搜索的原文短句。", [
            ["设备启动后应自动记录本次运行的测试环境和样本编号。"]]),
        ("5、没有截图也没有位置线索时，保留意见，明确位置未确定。", []),
    ]
    for value, pictures in items:
        review.add_paragraph(value)
        for lines in pictures:
            review.add_picture(screenshot(lines), width=Inches(6))
        if value.startswith("1"):
            review.add_paragraph("截图后的补充文字必须保留在第一条，不能成为新意见。")
    review.save(folder / "02_开发评审_五条意见.docx")
    ppt = make_powerpoint(folder / "03_PPT_两位作者编号均为1.pptx")
    authors = f'<p:cmAuthorLst xmlns:p="{P}"><p:cmAuthor id="0" name="评审甲"/><p:cmAuthor id="1" name="评审乙"/></p:cmAuthorLst>'
    comments = f'<p:cmLst xmlns:p="{P}"><p:cm authorId="0" idx="1"><p:text>请说明样本来源。</p:text></p:cm><p:cm authorId="1" idx="1"><p:text>图表需要补充单位。</p:text></p:cm></p:cmLst>'
    patch_zip(ppt, {"ppt/commentAuthors.xml": authors, "ppt/comments/comment1.xml": comments})
    (folder / "测试说明.txt").write_text(
        "全部为虚构数据，可自由测试。\n\n"
        "1. 点‘评审 Word ＋ 原手册…’，在①开发评审 Word选 02_开发评审_五条意见.docx。\n"
        "2. 在②原手册 Word选 01_被评审原文_虚构.docx，评审人填写‘开发甲’。\n"
        "3. 保持离线 OCR 选中。应为 5 条意见、5 张截图、0 回复。第1条保留截图后的补充文字。\n"
        "4. Windows OCR 可用时：第1条定位含第12页；第2条接口设计；第3条数据统计或图标题；第4条搜索短句；第5条位置未确定。识别失败时保留所有文字和截图，处理记录有提示。\n"
        "5. 双击上下文截图可预览；导出后保留 Excel 及同名附件目录，里面应有5张原图。\n"
        "6. 用普通‘添加文件’导入03_PPT，应为2条意见，评审甲和评审乙各1条，不因批注编号同为1而失败。\n"
        "7. 普通入口导入02不会把正文自动当批注，避免误处理普通技术文档。\n", encoding="utf-8-sig")
    archive = Path(str(folder) + ".zip")
    with ZipFile(archive, "w", ZIP_DEFLATED) as output:
        for path in folder.iterdir():
            if path.is_file():
                output.write(path, path.relative_to(folder.parent))
    return folder, archive


if __name__ == "__main__":
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("local_data") / f"CommentExtractor-v{__version__}-开发评审测试"
    for path in make_developer_samples(destination):
        print(path)
