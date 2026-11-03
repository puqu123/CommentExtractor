"""Build a fictional, reproducible manual acceptance pack for the desktop app."""
import json
from pathlib import Path
import shutil
import sys
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openpyxl import load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill

from commentextract.extract import extract_file
from tests.samples import W, make_excel, make_powerpoint, make_word, patch_zip


GUIDE = """CommentExtractor v0.2.5 手工测试包（全部为虚构数据）

先完整解压本测试包；程序使用 CommentExtractor v0.2.5。
每个场景开始前点击“清空列表”。导出到测试包之外的新建空文件夹，方便数文件。
只选择场景里的 Word / Excel / PPT 文件，不要将说明、清单作为输入。
所有人名、评审意见和回复均为虚构；现代评论／回复由程序构造 OOXML，用于本工具回归测试。
它们不能代替 Microsoft Office / WPS 真实文件的兼容性验证；某些 Office 版本可能以兼容便笺显示现代评论。

测试一：01_六份混合格式
1. “添加文件”一次选择全部 6 份文件，也可以直接选择这个文件夹。
2. 应显示 6 份待导出文件、8 条评审意见、4 条回复、0 份提取失败。
3. 02_Excel合并单元格和长内容.xlsx 应有 3 条意见：
   - 检查表 · B2，对应内容为 100。
   - 检查表 · B4:D5，是合并单元格，列表中长内容以 ..... 结束。
     双击此行的“对应原文／内容”单元格，弹窗里能找到“全文结尾核对码：LONG-END-2026”。
     导出的 Excel 同样保留这个结尾，不能截掉。
   - 检查表 · B7，是空单元格；对应原文为空，但评审意见必须保留。
4. 04_原始_评审意见.docx 是原始文件，不能仅因为名字包含“_评审意见”就漏掉。
5. 直接导出，应得到 6 个 .xlsx 和一份“批量导出结果_*.txt”。
   导出表只含“评审汇总”“提取报告”两个页签。“是否接受”保持空白，不能从回复自动填写。

测试二：02_五份评审合并
1. 添加这个文件夹中的 5 个 Word 文件。
2. 左侧 Ctrl+A 选中这 5 份，点击“合并所选评审文件”，文档名称填“接口方案”。
3. 应显示 5 份源文件、1 份待导出 Excel、5 条意见、5 条回复。
4. 第一、第二位评审人提了同一个意见，必须保留两行，不能自动删掉。
5. 按文件名 01 至 05 的顺序，将“是否接受”分别填为：是、重复、是、否、否。
6. 应显示 4 条有效意见、1 条重复；导出只得到“接口方案_评审意见.xlsx”一份。
7. 汇总表中的“文件名”应逐行显示 5 个不同的原始评审返回文件名。
   “回复人”均为虚构的“被评审人周工”，回复内容各不相同。
8. Excel 中“提取报告”打开并计算后：主意见 5、重复 1、去重后 4、回复 5。
   文件名、对应原文、评审人、评审意见等在程序中不可编辑；只有“是否接受”可编辑。
9. 导出路径窗口中应能看到文件夹和磁盘图标，可新建目录或选已有目录。

测试三：03_六份中一份故意损坏
1. 这里有 5 份有效文件和“06_故意损坏_应失败.docx”。最后一份刻意不是合法 Word，不要拿它当正常文档打开。
2. 一次添加全部 6 份，应保留 6 项记录，明确报告最后一份提取失败；待导出应为 5 份。
3. 导出得到 5 个 Excel，不能假装 6 份全部成功。
4. 点击“处理记录”，或打开输出目录中的 TXT，应能查到具体失败文件和 BadZipFile 错误。

核对提示
- 本包共 17 个输入文件，分 3 个场景；场景三里 1 个是故意损坏的。
- 程序没有设置最多 5 / 6 个文件的数量限制；5 份合并成 1 份导出是正常行为。
- “上下文截图”列目前保留为空，界面隐藏该列；本版本不支持 PDF。
- 不需要安装 Python 就能用免安装程序跑这些数据。
- 如果出问题，请记下场景、步骤、实际结果，并保留“批量导出结果_*.txt”。
"""


def make_pack(output):
    output = Path(output).resolve()
    # Never overwrite an earlier manual run or its results.
    output.mkdir(parents=True, exist_ok=False)
    mixed = output / "01_六份混合格式"
    merged = output / "02_五份评审合并"
    broken = output / "03_六份中一份故意损坏"
    for directory in (mixed, merged, broken):
        directory.mkdir()

    make_word(mixed / "01_Word选区批注与回复.docx")
    source = make_excel(mixed / "02_Excel合并单元格和长内容.xlsx")
    workbook = load_workbook(source)
    sheet = workbook.active
    sheet["A4"] = "合并单元格长内容"
    sheet.merge_cells("B4:D5")
    sheet["B4"] = ("测试说明：接口峰值并发为 120，响应时间目标为 2 秒，统计口径为百分之九十五分位；请核对测试条件、采样窗口和失败请求的处理规则。" * 8
                    + "全文结尾核对码：LONG-END-2026")
    sheet["B4"].comment = Comment("请补充并发峰值下的测量方法。", "虚构评审陈工")
    sheet["A7"] = "空单元格也有批注"
    sheet["B7"].comment = Comment("这里尚未填写，请补充超时阈值。", "虚构评审李工")
    sheet.column_dimensions["A"].width = 28
    for column in ("B", "C", "D"):
        sheet.column_dimensions[column].width = 22
    sheet.row_dimensions[4].height = 65
    sheet.row_dimensions[5].height = 65
    for row in sheet:
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="193652")
    workbook.save(source)
    workbook.close()
    make_excel(mixed / "03_Excel现代评论和回复.xlsx", threaded=True)
    make_word(mixed / "04_原始_评审意见.docx")
    make_powerpoint(mixed / "05_PPT传统批注.pptx")
    make_powerpoint(mixed / "06_PPT现代批注和回复.pptx", modern=True)

    reviewers = ["评审人王工", "评审人赵工", "评审人陈工", "评审人李工", "评审人孙工"]
    opinions = ["请说明响应时间的测量条件。", "请说明响应时间的测量条件。", "请补充超时后的错误提示。",
                "请补充峰值并发时的响应时间指标。", "建议所有请求日志保留十年。"]
    replies = ["接受，已补充测试环境和测量条件。", "与王工的意见重复，统一按同一问题处理。", "接受，将补充超时错误提示。",
               "部分接受，本轮补充峰值压测结果，长期指标后续完善。", "不接受，按现有保存期限执行，十年超出本次范围。"]
    for index, (reviewer, opinion, reply_text) in enumerate(zip(reviewers, opinions, replies), 1):
        path = make_word(merged / f"{index:02d}_接口方案_rev by {reviewer}.docx")
        with ZipFile(path) as package:
            comments = ET.fromstring(package.read("word/comments.xml"))
        roots = list(comments)
        roots[0].set("{" + W + "}author", reviewer)
        roots[1].set("{" + W + "}author", "被评审人周工")
        roots[0].find(".//{" + W + "}t").text = opinion
        roots[1].find(".//{" + W + "}t").text = reply_text
        patch_zip(path, {"word/comments.xml": ET.tostring(comments, encoding="utf-8")})

    for path in sorted(mixed.iterdir())[:5]:
        shutil.copy2(path, broken / path.name)
    (broken / "06_故意损坏_应失败.docx").write_text("此文件故意不是合法的 Word，用来测试提取失败是否明确报告。", encoding="utf-8")

    expected = {mixed.name: [(1, 1), (3, 0), (1, 1), (1, 1), (1, 0), (1, 1)],
                merged.name: [(1, 1)] * 5,
                broken.name: [(1, 1), (3, 0), (1, 1), (1, 1), (1, 0), None]}
    manifest = []
    for directory in (mixed, merged, broken):
        for path, expectation in zip(sorted(directory.iterdir()), expected[directory.name]):
            result = extract_file(path)
            if expectation is None:
                assert result.error and "BadZipFile" in result.error, result.error
            else:
                assert not result.error, result.error
                actual = (len(result.issues), result.comment_count - len(result.issues))
                assert actual == expectation, (path, actual, expectation)
            manifest.append({"文件": path.relative_to(output).as_posix(),
                             "预期意见数": expectation[0] if expectation else None,
                             "预期回复数": expectation[1] if expectation else None,
                             "预期失败": expectation is None})
    (output / "先看这里_测试步骤与预期结果.txt").write_text(GUIDE, encoding="utf-8-sig")
    (output / "预期结果清单.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    archive = output.parent / (output.name + ".zip")
    with ZipFile(archive, "x", ZIP_DEFLATED) as package:
        for path in sorted(output.rglob("*")):
            if path.is_file():
                package.write(path, path.relative_to(output.parent))
    return archive


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("local_data/CommentExtractor-v0.2.5-手工测试数据")
    print(make_pack(target))
