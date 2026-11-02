from xml.etree import ElementTree as ET
from zipfile import ZipFile

from docx import Document
from docx.oxml.ns import qn
from openpyxl import load_workbook

from commentextract.extract import extract_file
from commentextract.export import export_result
from .samples import W, W14, W15, append_relationship, add_types, patch_zip


def test_two_reviewers_one_responder_keep_separate_opinions(tmp_path):
    source = tmp_path / "三人评审.docx"
    document = Document()
    roots = []
    for index, reviewer in enumerate(("评审人甲", "评审人乙")):
        paragraph = document.add_paragraph()
        run = paragraph.add_run(f"第 {index + 1} 项设计要求")
        comment = document.add_comment(run, f"意见 {index + 1}：请补充说明。", reviewer)
        para_id = f"{index + 1:08X}"
        comment._element.findall(qn("w:p"))[-1].set("{" + W14 + "}paraId", para_id)
        roots.append(para_id)
    document.save(source)
    with ZipFile(source) as package:
        comments = ET.fromstring(package.read("word/comments.xml"))
        extended = ET.Element("{" + W15 + "}commentsEx")
        for index, root_id in enumerate(roots):
            reply_id = f"{index + 3:08X}"
            ET.SubElement(extended, "{" + W15 + "}commentEx", {"{" + W15 + "}paraId": root_id})
            ET.SubElement(extended, "{" + W15 + "}commentEx", {
                "{" + W15 + "}paraId": reply_id, "{" + W15 + "}paraIdParent": root_id})
            reply = ET.SubElement(comments, "{" + W + "}comment", {
                "{" + W + "}id": str(index + 2), "{" + W + "}author": "被评审人丙"})
            paragraph = ET.SubElement(reply, "{" + W + "}p", {"{" + W14 + "}paraId": reply_id})
            ET.SubElement(ET.SubElement(paragraph, "{" + W + "}r"), "{" + W + "}t").text = f"针对意见 {index + 1} 的回答。"
        rels = append_relationship(package.read("word/_rels/document.xml.rels"), "rIdThread",
                                   "http://schemas.microsoft.com/office/2011/relationships/commentsExtended", "commentsExtended.xml")
        types = add_types(package.read("[Content_Types].xml"), {
            "word/commentsExtended.xml": "application/vnd.ms-word.commentsExtended+xml"})
    patch_zip(source, {"word/comments.xml": ET.tostring(comments, encoding="utf-8"),
                       "word/commentsExtended.xml": ET.tostring(extended, encoding="utf-8"),
                       "word/_rels/document.xml.rels": rels, "[Content_Types].xml": types})
    result = extract_file(source)
    assert not result.error
    assert len(result.issues) == 2
    for index, issue in enumerate(result.issues):
        assert issue.root.author == ("评审人甲", "评审人乙")[index]
        assert issue.root.context == f"第 {index + 1} 项设计要求"
        assert len(issue.replies) == 1
        assert issue.replies[0].author == "被评审人丙"
        assert issue.replies[0].text == f"针对意见 {index + 1} 的回答。"
    workbook = load_workbook(export_result(result, tmp_path / "out"))
    sheet = workbook["评审汇总"]
    assert sheet.max_row == 3
    assert sheet["D2"].value == "评审人甲"
    assert sheet["D3"].value == "评审人乙"
    assert sheet["G2"].value == sheet["G3"].value == "被评审人丙"
    assert "意见 1" in sheet["H2"].value and "意见 2" not in sheet["H2"].value
    assert "意见 2" in sheet["H3"].value and "意见 1" not in sheet["H3"].value
    workbook.close()
