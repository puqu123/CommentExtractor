from commentextract.extract import extract_file
from commentextract.models import Comment, group_comments
from .samples import A, P, PC, make_powerpoint, patch_zip


def test_classic_same_index_different_authors_is_valid(tmp_path):
    path = make_powerpoint(tmp_path / "two-authors.pptx")
    comments = f'<p:cmLst xmlns:p="{P}"><p:cm authorId="0" idx="1"><p:text>意见甲</p:text></p:cm><p:cm authorId="1" idx="1"><p:text>意见乙</p:text></p:cm></p:cmLst>'
    authors = f'<p:cmAuthorLst xmlns:p="{P}"><p:cmAuthor id="0" name="评审甲"/><p:cmAuthor id="1" name="评审乙"/></p:cmAuthorLst>'
    patch_zip(path, {"ppt/comments/comment1.xml": comments, "ppt/commentAuthors.xml": authors})
    result = extract_file(path)
    assert not result.error
    assert len(result.issues) == 2
    assert [i.root.author for i in result.issues] == ["评审甲", "评审乙"]
    assert [i.root.text for i in result.issues] == ["意见甲", "意见乙"]
    assert not any("重复批注编号" in w for w in result.warnings)


def test_invalid_duplicate_modern_ids_preserve_all_and_detach_ambiguous_replies(tmp_path):
    path = make_powerpoint(tmp_path / "duplicate.pptx", modern=True)
    body = lambda value: f'<p:txBody><a:p><a:r><a:t>{value}</a:t></a:r></a:p></p:txBody>'
    comments = f'<p:cmLst xmlns:p="{PC}" xmlns:a="{A}"><p:cm id="same" authorId="author1">{body("甲")}<p:replyLst><p:reply id="reply" authorId="author2">{body("答复")}</p:reply></p:replyLst></p:cm><p:cm id="same" authorId="author1">{body("乙")}</p:cm></p:cmLst>'
    patch_zip(path, {"ppt/comments/modernComment1.xml": comments})
    result = extract_file(path)
    assert not result.error
    assert result.comment_count == 3
    assert len(result.issues) == 3
    assert {i.root.text for i in result.issues} == {"甲", "乙", "答复"}
    assert any("重复批注编号" in w for w in result.warnings)
    assert any("独立意见" in w for w in result.warnings)


def test_bad_part_does_not_discard_readable_comments_and_orphans_survive(tmp_path):
    path = make_powerpoint(tmp_path / "partial.pptx")
    patch_zip(path, {"ppt/comments/broken.xml": "<unclosed>",
                     "ppt/comments/orphan.xml": f'<p:cmLst xmlns:p="{P}"><p:cm authorId="0" idx="2"><p:text>游离意见</p:text></p:cm></p:cmLst>'})
    result = extract_file(path)
    assert not result.error
    assert len(result.issues) == 2
    assert result.issues[1].root.text == "游离意见"
    assert result.issues[1].root.location == "幻灯片位置未确定"
    assert any("部分提取" in w and "broken.xml" in w for w in result.warnings)
    assert any("未关联" in w for w in result.warnings)


def test_all_parts_bad_is_failure_not_empty_success(tmp_path):
    path = make_powerpoint(tmp_path / "broken.pptx")
    patch_zip(path, {"ppt/comments/comment1.xml": "<broken>"})
    result = extract_file(path)
    assert result.error and "无法恢复" in result.error


def test_broken_author_table_preserves_text(tmp_path):
    path = make_powerpoint(tmp_path / "author.pptx")
    patch_zip(path, {"ppt/commentAuthors.xml": "<broken>"})
    result = extract_file(path)
    assert not result.error
    assert result.issues[0].root.text == "图表缺少单位。"
    assert result.issues[0].root.author == ""
    assert any("作者表无法读取" in w for w in result.warnings)


def test_generic_duplicate_recovery_never_mutates_inputs_or_discards_comments():
    comments = [Comment("same", "甲", "一"), Comment("same", "乙", "二"), Comment("reply", "丙", "答", "same")]
    warnings = []
    result = group_comments(comments, warnings)
    assert sum(1 + len(i.replies) for i in result) == 3
    assert [c.id for c in comments] == ["same", "same", "reply"]
    assert comments[-1].parent_id == "same"
