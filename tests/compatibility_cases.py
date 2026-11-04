"""Independent expected results for synthetic compatibility cases.

These files are generated/ZIP-patched, NOT saved by Office or WPS. Passing
them never constitutes a claim that either vendor/version was verified.
"""
from dataclasses import dataclass, field
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree import ElementTree as ET
from urllib.parse import quote

from .samples import (A, P, PC, W, W14, W15, S, TC, REL, OREL,
                      make_word, make_excel, make_powerpoint, patch_zip,
                      append_relationship, add_types)

WORD_TEXT = "请说明响应时间的测量条件。"
WORD_REPLY = "接受，将补充测试环境和并发数量。"
WORD_CONTEXT = "接口响应时间不超过 2 秒"


def opinion(author, body, replies=(), context=None, location=None):
    result = {"reviewer": author, "opinion": body, "replies": list(replies)}
    if context is not None:
        result["context"] = context
    if location is not None:
        result["location_contains"] = location
    return result


WORD = [opinion("评审人甲", WORD_TEXT, [("答复人乙", WORD_REPLY)], WORD_CONTEXT)]
EXCEL = [opinion("评审人甲", "请核实样本数量。", context="100", location="检查表 · B2")]
THREADED = [opinion("评审人甲", "请核实样本数量。", [("答复人乙", "已核实，数量为 100。")], "100", "检查表 · B2")]
PPT = [opinion("评审人甲", "图表缺少单位。", location="第 1 张幻灯片")]
MODERN_PPT = [opinion("评审人甲", "图表缺少单位。", [("答复人乙", "将补充单位。")], location="第 1 张幻灯片")]


@dataclass
class CompatibilityCase:
    id: str
    source: Path
    description: str
    expected: list
    kind: str = "positive"  # positive / recovery / negative; never combine rates
    warning_contains: tuple = ()
    error_contains: str = ""
    options: dict = field(default_factory=dict)


def xml(path, part):
    with ZipFile(path) as package:
        return ET.fromstring(package.read(part))


def replace_part(path, old, new):
    """Relocate a part and rewrite relative relationship targets/content types."""
    import posixpath
    with ZipFile(path) as package:
        contents = {n: package.read(n) for n in package.namelist()}
    contents[new] = contents.pop(old)
    for name, data in list(contents.items()):
        if name.endswith(".rels"):
            root = ET.fromstring(data)
            base = "" if name == "_rels/.rels" else posixpath.dirname(posixpath.dirname(name))
            for rel in root:
                target = rel.get("Target", "")
                resolved = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(base, target))
                if resolved == old:
                    rel.set("Target", posixpath.relpath(new, base or "."))
            contents[name] = ET.tostring(root, encoding="utf-8")
        elif name == "[Content_Types].xml":
            contents[name] = data.replace(("/" + old).encode(), ("/" + new).encode())
    with ZipFile(path, "w", ZIP_DEFLATED) as package:
        for name, data in contents.items():
            package.writestr(name, data)


def custom_word(path, entries, document=None, extended=None):
    make_word(path)
    root = ET.Element("{" + W + "}comments")
    ext = ET.Element("{" + W15 + "}commentsEx")
    for cid, author, body, parent in entries:
        node = ET.SubElement(root, "{" + W + "}comment", {"{" + W + "}id": cid, "{" + W + "}author": author})
        paragraph = ET.SubElement(node, "{" + W + "}p", {"{" + W14 + "}paraId": "p-" + cid})
        ET.SubElement(ET.SubElement(paragraph, "{" + W + "}r"), "{" + W + "}t").text = body
        attrs = {"{" + W15 + "}paraId": "p-" + cid}
        if parent is not None:
            attrs["{" + W15 + "}paraIdParent"] = "p-" + parent
        ET.SubElement(ext, "{" + W15 + "}commentEx", attrs)
    changes = {"word/comments.xml": ET.tostring(root, encoding="utf-8"),
               "word/commentsExtended.xml": ET.tostring(ext, encoding="utf-8") if extended is None else extended}
    if document is not None:
        changes["word/document.xml"] = f'<w:document xmlns:w="{W}"><w:body>{document}<w:sectPr/></w:body></w:document>'
    patch_zip(path, changes)
    return path


def build_compatibility_cases(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    cases = []

    def add(cid, suffix, description, expected, maker=None, **kwargs):
        path = folder / (cid + suffix)
        if maker:
            maker(path)
        case = CompatibilityCase(cid, path, description, expected, **kwargs)
        cases.append(case)
        return path

    for cid, suffix, description, maker, expected in [
        ("W01", ".docx", "Word 选区及明确回复", make_word, WORD),
        ("X01", ".xlsx", "Excel 旧式便笺", make_excel, EXCEL),
        ("X02", ".xlsx", "Excel 现代评论及兼容占位", lambda p: make_excel(p, True), THREADED),
        ("P01", ".pptx", "PPT 传统批注", make_powerpoint, PPT),
        ("P02", ".pptx", "PPT 现代批注及回复", lambda p: make_powerpoint(p, True), MODERN_PPT),
    ]:
        add(cid, suffix, description, expected, maker)
    # Namespace prefixes, strict namespace URIs, and XML byte encoding must
    # not change comment meaning. Each vendor still needs actual saved files.
    for prefix, suffix, maker, expected in [("W", ".docx", make_word, WORD), ("X", ".xlsx", make_excel, EXCEL), ("P", ".pptx", make_powerpoint, PPT)]:
        for code, variant in [("03", "utf16"), ("04", "strict")]:
            path = add(prefix + code, suffix, "XML UTF-16" if variant == "utf16" else "Strict 命名空间结构", expected, maker)
            with ZipFile(path) as package:
                changes = {}
                for name in package.namelist():
                    if not name.endswith(".xml"):
                        continue
                    value = package.read(name).decode("utf-8-sig")
                    if variant == "utf16":
                        if value.startswith("<?xml"):
                            value = value[value.index("?>") + 2:]
                        changes[name] = ('<?xml version="1.0" encoding="UTF-16"?>' + value).encode("utf-16")
                    else:
                        changes[name] = value.replace("http://schemas.openxmlformats.org/wordprocessingml/2006/main", "http://purl.oclc.org/ooxml/wordprocessingml/main").replace("http://schemas.openxmlformats.org/spreadsheetml/2006/main", "http://purl.oclc.org/ooxml/spreadsheetml/main").replace("http://schemas.openxmlformats.org/presentationml/2006/main", "http://purl.oclc.org/ooxml/presentationml/main")
            patch_zip(path, changes)

    # Independently specified Word body, root/reply authors and order.
    word_specs = [
        ("W05", "回复先于原意见／三级回复", [("2", "答复乙", "第二次回复", "1"), ("0", "评审甲", "原意见", None), ("1", "答复乙", "第一次回复", "0")],
         [opinion("评审甲", "原意见", [("答复乙", "第二次回复"), ("答复乙", "第一次回复")])]),
        ("W06", "同名评审人和同文意见不得自动去重", [("0", "administrator", "请核实", None), ("9", "administrator", "请核实", None)],
         [opinion("administrator", "请核实"), opinion("administrator", "请核实")]),
        ("W07", "空姓名、空批注、特殊字符", [("0", "", "", None), ("7", "王工🙂", "中文 English <>&\n第二行\t末尾", None)],
         [opinion("", ""), opinion("王工🙂", "中文 English <>&\n第二行\t末尾")]),
        ("W08", "非连续编号", [("0", "甲", "意见一", None), ("999", "乙", "意见二", None)], [opinion("甲", "意见一"), opinion("乙", "意见二")]),
    ]
    for cid, description, entries, expected in word_specs:
        add(cid, ".docx", description, expected, lambda p, e=entries: custom_word(p, e))
    path = add("W09", ".docx", "已解决状态不丢失意见", WORD, make_word)
    ext = xml(path, "word/commentsExtended.xml")
    for node in ext:
        node.set("{" + W15 + "}done", "1")
    patch_zip(path, {"word/commentsExtended.xml": ET.tostring(ext, encoding="utf-8")})
    path = add("W10", ".docx", "批注部件采用非默认文件名", WORD, make_word)
    replace_part(path, "word/comments.xml", "word/review-notes.xml")
    path = add("W11", ".docx", "表格单元格中的选区", [opinion("甲", "表格意见", context="表格原文")],
               lambda p: custom_word(p, [("0", "甲", "表格意见", None)], '<w:tbl><w:tr><w:tc><w:p><w:commentRangeStart w:id="0"/><w:r><w:t>表格原文</w:t></w:r><w:commentRangeEnd w:id="0"/></w:p></w:tc></w:tr></w:tbl>'))
    add("W12", ".docx", "选区跨段落", [opinion("甲", "跨段意见", context="第一段\n第二段")],
        lambda p: custom_word(p, [("0", "甲", "跨段意见", None)], '<w:p><w:commentRangeStart w:id="0"/><w:r><w:t>第一段</w:t></w:r></w:p><w:p><w:r><w:t>第二段</w:t></w:r><w:commentRangeEnd w:id="0"/></w:p>'))
    add("W13", ".docx", "重叠选区各自保留", [opinion("甲", "一", context="AB"), opinion("乙", "二", context="BC")],
        lambda p: custom_word(p, [("0", "甲", "一", None), ("1", "乙", "二", None)], '<w:p><w:commentRangeStart w:id="0"/><w:r><w:t>A</w:t></w:r><w:commentRangeStart w:id="1"/><w:r><w:t>B</w:t></w:r><w:commentRangeEnd w:id="0"/><w:r><w:t>C</w:t></w:r><w:commentRangeEnd w:id="1"/></w:p>'))
    add("W14", ".docx", "点批注／无选区", [opinion("甲", "点意见", context="", location="搜索")],
        lambda p: custom_word(p, [("0", "甲", "点意见", None)], '<w:p><w:r><w:t>可搜索原文</w:t></w:r><w:r><w:commentReference w:id="0"/></w:r></w:p>'))
    many = [(str(i), "评审甲" if i % 2 else "评审乙", f"压力意见 {i}", None) for i in range(500)]
    add("W15", ".docx", "500 条意见逐条核对", [opinion(author, body) for _, author, body, _ in many], lambda p: custom_word(p, many))

    # Word fallback: damaged optional metadata must not discard comment bodies.
    add("WR01", ".docx", "回复元数据损坏仍保留全部文字", [opinion("评审人甲", WORD_TEXT), opinion("答复人乙", WORD_REPLY)],
        lambda p: (make_word(p), patch_zip(p, {"word/commentsExtended.xml": "<broken>"})), kind="recovery", warning_contains=("回复",))
    add("WR02", ".docx", "样式损坏不影响评论文字", WORD,
        lambda p: (make_word(p), patch_zip(p, {"word/styles.xml": "<broken>"})), kind="recovery", warning_contains=("样式",))

    # Excel: independent sheets / authors / contexts.
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    def excel_sheets(path):
        wb = Workbook()
        for i, name in enumerate(("可见", "隐藏", "深度隐藏")):
            sheet = wb.active if i == 0 else wb.create_sheet()
            sheet.title = name
            sheet.sheet_state = ("visible", "hidden", "veryHidden")[i]
            sheet["C3"] = str(i)
            sheet["C3"].comment = Comment("意见" + str(i), "评审" + str(i))
        wb.save(path)
    add("X05", ".xlsx", "隐藏与深度隐藏工作表", [opinion("评审" + str(i), "意见" + str(i), context=str(i), location=name + " · C3") for i, name in enumerate(("可见", "隐藏", "深度隐藏"))], excel_sheets)
    path = add("X06", ".xlsx", "人员表关系采用非默认目录", THREADED, lambda p: make_excel(p, True))
    replace_part(path, "xl/persons/person.xml", "xl/metadata/reviewers.xml")
    path = add("X07", ".xlsx", "多级回复且子回复先出现", [opinion("评审人甲", "主意见", [("答复人乙", "二级回复"), ("答复人乙", "一级回复")], "100")], lambda p: make_excel(p, True))
    patch_zip(path, {"xl/threadedComments/threadedComment1.xml": f'<ThreadedComments xmlns="{TC}"><threadedComment id="two" parentId="one" personId="person2"><text>二级回复</text></threadedComment><threadedComment ref="B2" id="root" personId="person1"><text>主意见</text></threadedComment><threadedComment id="one" parentId="root" personId="person2"><text>一级回复</text></threadedComment></ThreadedComments>'})
    path = add("X08", ".xlsx", "公式缓存与公式原文", [opinion("评审人甲", "请核实样本数量。", context="=SUM(A1:A2)")], make_excel)
    patch_zip(path, {"xl/worksheets/sheet1.xml": f'<worksheet xmlns="{S}"><sheetData><row r="2"><c r="B2"><f>SUM(A1:A2)</f></c></row></sheetData></worksheet>'})
    path = add("X09", ".xlsx", "最末列和最末行", [opinion("评审人甲", "请核实样本数量。", context="", location="XFD1048576")], make_excel)
    with ZipFile(path) as package:
        part = next(n for n in package.namelist() if n.endswith("comment1.xml"))
        value = package.read(part).replace(b'ref="B2"', b'ref="XFD1048576"')
    patch_zip(path, {part: value})
    path = add("X10", ".xlsx", "富文本批注", [opinion("评审人甲", "第一段第二段")], make_excel)
    root = xml(path, part)
    node = next(root.iter("{" + S + "}comment"))
    for child in list(node):
        node.remove(child)
    body = ET.SubElement(node, "{" + S + "}text")
    for value in ("第一段", "第二段"):
        ET.SubElement(ET.SubElement(body, "{" + S + "}r"), "{" + S + "}t").text = value
    patch_zip(path, {part: ET.tostring(root, encoding="utf-8")})
    path = add("XR01", ".xlsx", "作者编号非法不丢评论", [opinion("", "请核实样本数量。", context="100")], make_excel, kind="recovery", warning_contains=("作者",))
    root = xml(path, part)
    next(root.iter("{" + S + "}comment")).set("authorId", "-1")
    patch_zip(path, {part: ET.tostring(root, encoding="utf-8")})
    path = add("XR02", ".xlsx", "坏共享字符串不丢评论", [opinion("评审人甲", "请核实样本数量。")], make_excel, kind="recovery", warning_contains=("共享字符串",))
    patch_zip(path, {"xl/sharedStrings.xml": f'<sst xmlns="{S}"><si><t>唯一值</t></si></sst>', "xl/worksheets/sheet1.xml": f'<worksheet xmlns="{S}"><sheetData><row r="2"><c r="B2" t="s"><v>99</v></c></row></sheetData></worksheet>'})

    path = add("P05", ".pptx", "作者表采用非默认部件名", MODERN_PPT, lambda p: make_powerpoint(p, True))
    replace_part(path, "ppt/authors.xml", "ppt/metadata/people.xml")
    path = add("P06", ".pptx", "幻灯片显示顺序不同于文件编号", [opinion("评审人甲", "图表缺少单位。", location="第 2 张幻灯片")], make_powerpoint)
    presentation = xml(path, "ppt/presentation.xml")
    slides = next(presentation.iter("{" + P + "}sldIdLst"))
    ET.SubElement(slides, "{" + P + "}sldId", {"id": "999", "{" + OREL + "}id": "rIdEmpty"})
    slides[:] = list(reversed(list(slides)))
    with ZipFile(path) as package:
        rels = append_relationship(package.read("ppt/_rels/presentation.xml.rels"), "rIdEmpty", OREL + "/slide", "slides/empty.xml")
    patch_zip(path, {"ppt/presentation.xml": ET.tostring(presentation, encoding="utf-8"), "ppt/_rels/presentation.xml.rels": rels, "ppt/slides/empty.xml": f'<p:sld xmlns:p="{P}"/>'})
    path = add("PR01", ".pptx", "一个坏批注部件不影响其余意见", PPT, make_powerpoint, kind="recovery", warning_contains=("部分提取",))
    patch_zip(path, {"ppt/comments/broken.xml": "<broken>"})
    for cid, suffix, maker in [("WN01", ".docx", make_word), ("XN01", ".xlsx", make_excel), ("PN01", ".pptx", make_powerpoint)]:
        path = add(cid, suffix, "整个文件损坏必须明确失败", [], maker, kind="negative", error_contains="BadZipFile")
        path.write_bytes(b"deliberately invalid OOXML, not an Office file")
    from docx import Document
    from pptx import Presentation
    add("W00", ".docx", "真正无批注文档", [], lambda p: Document().save(p))
    add("X00", ".xlsx", "真正无批注工作簿", [], lambda p: Workbook().save(p))
    add("P00", ".pptx", "真正无批注演示", [], lambda p: Presentation().save(p))
    for prefix, suffix, maker, expected, old, new in [
        ("W", ".docx", make_word, WORD, "word/comments.xml", "word/评审 notes.xml"),
        ("X", ".xlsx", make_excel, EXCEL, "xl/comments/comment1.xml", "xl/comments/评审 notes.xml"),
        ("P", ".pptx", make_powerpoint, PPT, "ppt/comments/comment1.xml", "ppt/comments/评审 notes.xml"),
    ]:
        path = add(prefix + "U01", suffix, "关系 URI 中的中文、空格与百分号转义", expected, maker)
        replace_part(path, old, new)
        with ZipFile(path) as package:
            changes = {}
            for name in package.namelist():
                if name.endswith(".rels"):
                    root = ET.fromstring(package.read(name))
                    for rel in root:
                        rel.set("Target", quote(rel.get("Target", ""), safe="/.:"))
                    changes[name] = ET.tostring(root, encoding="utf-8")
        patch_zip(path, changes)
    mc = "http://schemas.openxmlformats.org/markup-compatibility/2006"
    for cid, namespace, requires, expected_text in [("WM01", W14, "w14", "应选新版文字"), ("WM02", "urn:unsupported-future-feature", "future", "应选兼容文字")]:
        path = add(cid, ".docx", "兼容分支只能读取一次", [opinion("甲", expected_text)],
                   lambda p: custom_word(p, [("0", "甲", "placeholder", None)]))
        patch_zip(path, {"word/comments.xml": f'<w:comments xmlns:w="{W}" xmlns:mc="{mc}" xmlns:{requires}="{namespace}"><w:comment w:id="0" w:author="甲"><mc:AlternateContent><mc:Choice Requires="{requires}"><w:p><w:r><w:t>应选新版文字</w:t></w:r></w:p></mc:Choice><mc:Fallback><w:p><w:r><w:t>应选兼容文字</w:t></w:r></w:p></mc:Fallback></mc:AlternateContent></w:comment></w:comments>'})
    add("WR03", ".docx", "原文损坏时仍保留可读批注及回复", [opinion("评审人甲", WORD_TEXT, [("答复人乙", WORD_REPLY)])],
        lambda p: (make_word(p), patch_zip(p, {"word/document.xml": "<broken>"})), kind="recovery", warning_contains=("定位",))
    add("XR03", ".xlsx", "工作表内容损坏不丢批注", [opinion("评审人甲", "请核实样本数量。", location="检查表 · B2")],
        lambda p: (make_excel(p), patch_zip(p, {"xl/worksheets/sheet1.xml": "<broken>"})), kind="recovery", warning_contains=("工作表",))
    path = add("XR04", ".xlsx", "单条批注地址无效不丢文字", [opinion("评审人甲", "请核实样本数量。", location="位置未确定")], make_excel,
               kind="recovery", warning_contains=("单元格地址无效",))
    root = xml(path, "xl/comments/comment1.xml")
    next(root.iter("{" + S + "}comment")).set("ref", "???")
    patch_zip(path, {"xl/comments/comment1.xml": ET.tostring(root, encoding="utf-8")})
    path = add("WN02", ".docx", "未知兼容扩展没有回退时明确失败", [],
               lambda p: custom_word(p, [("0", "甲", "placeholder", None)]), kind="negative", error_contains="兼容内容")
    patch_zip(path, {"word/comments.xml": f'<w:comments xmlns:w="{W}" xmlns:mc="{mc}" xmlns:future="urn:unsupported"><w:comment w:id="0" w:author="甲"><mc:AlternateContent><mc:Choice Requires="future"><future:content/></mc:Choice></mc:AlternateContent></w:comment></w:comments>'})
    path = add("WM03", ".docx", "兼容分支按局部命名空间判断", [opinion("甲", "正确回退")],
               lambda p: custom_word(p, [("0", "甲", "placeholder", None)]))
    patch_zip(path, {"word/comments.xml": f'<w:comments xmlns:w="{W}" xmlns:mc="{mc}" xmlns:w14="{W14}"><w:comment w:id="0" w:author="甲"><mc:AlternateContent><mc:Choice xmlns:w14="urn:unknown-local" Requires="w14"><w:p><w:r><w:t>错误分支</w:t></w:r></w:p></mc:Choice><mc:Fallback><w:p><w:r><w:t>正确回退</w:t></w:r></w:p></mc:Fallback></mc:AlternateContent></w:comment></w:comments>'})
    long_body, long_reply = "长意见🙂" * 10000 + "OPINION-END", "长回复" * 12000 + "REPLY-END"
    add("W16", ".docx", "超长意见和回复完整导出为附件", [opinion("甲", long_body, [("乙", long_reply)])],
        lambda p: custom_word(p, [("0", "甲", long_body, None), ("1", "乙", long_reply, "0")]))
    path = add("X11", ".xlsx", "工作表及结构保护不等于文件加密", EXCEL, make_excel)
    from openpyxl import load_workbook
    protected = load_workbook(path)
    protected.active.protection.sheet = True
    protected.active.protection.set_password("fictional-test-password")
    protected.security.lockStructure = True
    protected.save(path)
    protected.close()
    return cases
