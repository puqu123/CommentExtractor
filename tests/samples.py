"""Synthetic review fixtures. Never use customer documents in committed tests."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree import ElementTree as ET

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
W15 = "http://schemas.microsoft.com/office/word/2012/wordml"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
OREL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
TC = "http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
PC = "http://schemas.microsoft.com/office/powerpoint/2018/8/main"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"


def patch_zip(path, additions):
    with ZipFile(path) as source:
        contents = {name: source.read(name) for name in source.namelist()}
    contents.update({name: value.encode("utf-8") if isinstance(value, str) else value
                     for name, value in additions.items()})
    with ZipFile(path, "w", ZIP_DEFLATED) as target:
        for name, value in contents.items():
            target.writestr(name, value)


def append_relationship(data, rid, kind, target):
    root = ET.fromstring(data)
    ET.SubElement(root, "{" + REL + "}Relationship", Id=rid, Type=kind, Target=target)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def add_types(data, mapping):
    root = ET.fromstring(data)
    for name, content_type in mapping.items():
        ET.SubElement(root, "{" + CT + "}Override", PartName="/" + name, ContentType=content_type)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def make_word(path):
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    document = Document()
    document.add_heading("评审测试文档（虚构数据）", 0)
    paragraph = document.add_paragraph()
    paragraph.add_run("设计要求：")
    selected = paragraph.add_run("接口响应时间不超过 2 秒")
    paragraph.add_run("，并记录处理结果。")
    comment = document.add_comment(selected, text="请说明响应时间的测量条件。", author="评审人甲", initials="甲")
    last = comment._element.findall(qn("w:p"))[-1]
    last.set("{" + W14 + "}paraId", "11111111")
    document.add_paragraph("此段不在批注选区中。")
    document.save(path)
    with ZipFile(path) as package:
        comments = ET.fromstring(package.read("word/comments.xml"))
        reply = ET.SubElement(comments, "{" + W + "}comment", {
            "{" + W + "}id": "1", "{" + W + "}author": "答复人乙"})
        p = ET.SubElement(reply, "{" + W + "}p", {"{" + W14 + "}paraId": "22222222"})
        ET.SubElement(ET.SubElement(p, "{" + W + "}r"), "{" + W + "}t").text = "接受，将补充测试环境和并发数量。"
        rels = append_relationship(package.read("word/_rels/document.xml.rels"), "rIdThread",
                                   "http://schemas.microsoft.com/office/2011/relationships/commentsExtended", "commentsExtended.xml")
        types = add_types(package.read("[Content_Types].xml"), {
            "word/commentsExtended.xml": "application/vnd.ms-word.commentsExtended+xml"})
    patch_zip(path, {"word/comments.xml": ET.tostring(comments, encoding="utf-8"),
                     "word/commentsExtended.xml": f'<w15:commentsEx xmlns:w15="{W15}"><w15:commentEx w15:paraId="11111111"/><w15:commentEx w15:paraId="22222222" w15:paraIdParent="11111111"/></w15:commentsEx>',
                     "word/_rels/document.xml.rels": rels, "[Content_Types].xml": types})
    return path


def make_excel(path, threaded=False):
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    wb = Workbook()
    sheet = wb.active
    sheet.title = "检查表"
    sheet.append(["检查项目", "检查值"])
    sheet.append(["样本数量", 100])
    sheet["B2"].comment = Comment("[Threaded comment]\n兼容占位" if threaded else "请核实样本数量。", "评审人甲")
    wb.save(path)
    if threaded:
        with ZipFile(path) as package:
            rels = append_relationship(package.read("xl/worksheets/_rels/sheet1.xml.rels"), "rIdThread",
                                       "http://schemas.microsoft.com/office/2017/10/relationships/threadedComment",
                                       "../threadedComments/threadedComment1.xml")
            workbook_rels = append_relationship(package.read("xl/_rels/workbook.xml.rels"), "rIdPersons",
                                                "http://schemas.microsoft.com/office/2017/10/relationships/person", "persons/person.xml")
            types = add_types(package.read("[Content_Types].xml"), {
                "xl/threadedComments/threadedComment1.xml": "application/vnd.ms-excel.threadedcomments+xml",
                "xl/persons/person.xml": "application/vnd.ms-excel.person+xml"})
        patch_zip(path, {"xl/worksheets/_rels/sheet1.xml.rels": rels,
                         "xl/_rels/workbook.xml.rels": workbook_rels,
                         "[Content_Types].xml": types,
                         "xl/persons/person.xml": f'<personList xmlns="{TC}"><person id="person1" displayName="评审人甲"/><person id="person2" displayName="答复人乙"/></personList>',
                         "xl/threadedComments/threadedComment1.xml": f'<ThreadedComments xmlns="{TC}"><threadedComment ref="B2" id="root" personId="person1"><text>请核实样本数量。</text></threadedComment><threadedComment id="reply" parentId="root" personId="person2"><text>已核实，数量为 100。</text></threadedComment></ThreadedComments>'})
    return path


def make_powerpoint(path, modern=False):
    from pptx import Presentation
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    slide.shapes.title.text = "评审测试幻灯片（虚构数据）"
    slide.placeholders[1].text = "检查这张图表的数据单位。"
    presentation.save(path)
    authors_part = "ppt/authors.xml" if modern else "ppt/commentAuthors.xml"
    comments_part = "ppt/comments/modernComment1.xml" if modern else "ppt/comments/comment1.xml"
    kind = "http://schemas.microsoft.com/office/2018/10/relationships/comment" if modern else OREL + "/comments"
    author_kind = "http://schemas.microsoft.com/office/2018/10/relationships/authors" if modern else OREL + "/commentAuthors"
    with ZipFile(path) as package:
        slide_rels = append_relationship(package.read("ppt/slides/_rels/slide1.xml.rels"), "rIdComments", kind,
                                         "../comments/" + comments_part.rsplit("/", 1)[-1])
        pres_rels = append_relationship(package.read("ppt/_rels/presentation.xml.rels"), "rIdAuthors", author_kind,
                                        authors_part.rsplit("/", 1)[-1])
        types = add_types(package.read("[Content_Types].xml"), {
            authors_part: "application/vnd.ms-powerpoint.authors+xml" if modern else "application/vnd.openxmlformats-officedocument.presentationml.commentAuthors+xml",
            comments_part: "application/vnd.ms-powerpoint.comments+xml" if modern else "application/vnd.openxmlformats-officedocument.presentationml.comments+xml"})
    if modern:
        authors = f'<p:authorLst xmlns:p="{PC}"><p:author id="author1" name="评审人甲"/><p:author id="author2" name="答复人乙"/></p:authorLst>'
        comments = f'<p:cmLst xmlns:p="{PC}" xmlns:a="{A}"><p:cm id="root" authorId="author1"><p:unknownAnchor/><p:replyLst><p:reply id="reply" authorId="author2"><p:txBody><a:p><a:r><a:t>将补充单位。</a:t></a:r></a:p></p:txBody></p:reply></p:replyLst><p:txBody><a:p><a:r><a:t>图表缺少单位。</a:t></a:r></a:p></p:txBody></p:cm></p:cmLst>'
    else:
        authors = f'<p:cmAuthorLst xmlns:p="{P}"><p:cmAuthor id="0" name="评审人甲" initials="甲" lastIdx="1" clrIdx="0"/></p:cmAuthorLst>'
        comments = f'<p:cmLst xmlns:p="{P}"><p:cm authorId="0" idx="1"><p:pos x="100" y="100"/><p:text>图表缺少单位。</p:text></p:cm></p:cmLst>'
    patch_zip(path, {authors_part: authors, comments_part: comments,
                     "ppt/slides/_rels/slide1.xml.rels": slide_rels,
                     "ppt/_rels/presentation.xml.rels": pres_rels, "[Content_Types].xml": types})
    return path


def create_samples(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    make_word(directory / "01_Word评审.docx")
    make_excel(directory / "02_Excel便笺.xlsx")
    make_excel(directory / "03_Excel评论.xlsx", threaded=True)
    make_word(directory / "04_Word第二位评审.docx")
    make_powerpoint(directory / "05_PPT传统批注.pptx")
    make_powerpoint(directory / "06_PPT现代批注.pptx", modern=True)
