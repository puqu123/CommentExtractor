from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

HEADERS = ["意见编号", "文件名", "位置", "对应原文／内容", "评审人", "评审意见", "是否接受", "回复人", "回复内容", "上下文截图"]
ACCEPTANCE_COLUMN = HEADERS.index("是否接受")
CONTEXT_COLUMN = HEADERS.index("对应原文／内容")
ACCEPTANCE = ("", "是", "否", "部分接受", "重复")


@dataclass
class Comment:
    id: str
    author: str
    text: str
    parent_id: Optional[str] = None
    location: str = ""
    context: str = ""


@dataclass
class Issue:
    id: str
    root: Comment
    replies: List[Comment] = field(default_factory=list)
    acceptance: str = ""
    source: Optional[Path] = None

    def values(self, filename: str = "") -> list:
        authors = list(dict.fromkeys(c.author or "未署名" for c in self.replies))
        replies = "\n\n".join(f"{i}. {c.author or '未署名'}：{c.text}" for i, c in enumerate(self.replies, 1))
        return [self.id, self.source.name if self.source else filename,
                self.root.location, self.root.context, self.root.author,
                self.root.text, self.acceptance, "、".join(authors), replies, ""]


@dataclass
class Extraction:
    source: Path
    issues: List[Issue] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error: str = ""
    sources: List[Path] = field(default_factory=list)

    @property
    def comment_count(self) -> int:
        return sum(1 + len(i.replies) for i in self.issues)


def group_comments(comments: List[Comment], warnings: List[str]) -> List[Issue]:
    """Group only explicit parent links; preserve XML/page order within threads."""
    by_id = {}
    for comment in comments:
        if comment.id in by_id:
            raise ValueError(f"批注编号重复，无法可靠关联：{comment.id}")
        by_id[comment.id] = comment
    roots = {}
    for comment in comments:
        current = comment
        seen = set()
        while current.parent_id:
            if current.id in seen:
                warnings.append("发现循环回复关系，相关批注按独立意见保留。")
                current = comment
                break
            seen.add(current.id)
            parent = by_id.get(current.parent_id)
            if parent is None:
                warnings.append(f"有回复找不到原批注，已独立保留：{current.id}")
                break
            current = parent
        roots[comment.id] = current.id
    groups = {}
    for comment in comments:
        root_id = roots[comment.id]
        if root_id not in groups:
            groups[root_id] = Issue(f"R{len(groups) + 1:04d}", by_id[root_id])
        if comment.id != root_id:
            groups[root_id].replies.append(comment)
    return list(groups.values())
