from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from collections import Counter
from dataclasses import replace
from typing import List, Optional

HEADERS = ["意见编号", "文件名", "位置", "对应原文／内容", "评审人", "评审意见", "是否接受", "回复人", "回复内容", "上下文截图"]
ACCEPTANCE_COLUMN = HEADERS.index("是否接受")
CONTEXT_COLUMN = HEADERS.index("对应原文／内容")
ACCEPTANCE = ("", "是", "否", "重复")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".emf", ".wmf", ".ico"}


@dataclass
class Screenshot:
    name: str
    data: bytes
    ocr_text: str = ""


@dataclass
class Comment:
    id: str
    author: str
    text: str
    parent_id: Optional[str] = None
    location: str = ""
    context: str = ""
    screenshots: List[Screenshot] = field(default_factory=list)


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
                self.root.text, self.acceptance, "、".join(authors), replies,
                "\n".join(image.name for image in self.root.screenshots)]


@dataclass
class Extraction:
    source: Path
    issues: List[Issue] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error: str = ""
    sources: List[Path] = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)

    @property
    def comment_count(self) -> int:
        return sum(1 + len(i.replies) for i in self.issues)


def group_comments(comments: List[Comment], warnings: List[str]) -> List[Issue]:
    """Group only explicit parent links; preserve XML/page order within threads."""
    # Invalid IDs must not discard a whole file or silently attach replies to
    # whichever duplicate happened to appear last. Preserve every occurrence.
    counts = Counter(c.id for c in comments)
    ambiguous = {cid for cid, count in counts.items() if count > 1}
    reserved = set(counts)
    normalized = []
    for index, comment in enumerate(comments, 1):
        cid, parent = comment.id, comment.parent_id
        if cid in ambiguous:
            candidate = f"{cid}#recovered-{index}"
            while candidate in reserved:
                candidate += "_"
            reserved.add(candidate)
            cid = candidate
        if parent in ambiguous:
            parent = None
            warnings.append("回复指向重复的批注编号，无法确定所属意见，已作为独立意见保留。")
        normalized.append(replace(comment, id=cid, parent_id=parent))
    if ambiguous:
        warnings.append(f"发现 {len(ambiguous)} 组重复批注编号，已重新编号并保留全部内容；请核对回复关系。")
    comments = normalized
    by_id = {comment.id: comment for comment in comments}
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
