from __future__ import annotations

import io

import fitz
from PIL import Image, ImageDraw

from .models import Comment


def read_pdf(path, warnings):
    comments = []
    with fitz.open(path) as document:
        if document.needs_pass:
            raise ValueError("PDF 已加密，请先使用有权限的阅读器另存为可读取版本。")
        for page_number, page in enumerate(document):
            text_layout = None
            for annot in page.annots() or ():
                if annot.type[0] in {fitz.PDF_ANNOT_POPUP, fitz.PDF_ANNOT_LINK, fitz.PDF_ANNOT_WIDGET}:
                    continue
                info = annot.info
                content = info.get("content", "")
                if not content:
                    # Keep markups without textual comments; don't silently drop review marks.
                    content = f"〔{annot.type[1]} 标记，无文字批注〕"
                context = ""
                if annot.type[0] in {fitz.PDF_ANNOT_HIGHLIGHT, fitz.PDF_ANNOT_UNDERLINE,
                                    fitz.PDF_ANNOT_STRIKE_OUT, fitz.PDF_ANNOT_SQUIGGLY}:
                    vertices = annot.vertices or []
                    quads = [fitz.Quad(vertices[i:i + 4]) for i in range(0, len(vertices) - 3, 4)]
                    if text_layout is None:
                        text_layout = page.get_text("rawdict", sort=True)
                    selected_lines = []
                    for block in text_layout["blocks"]:
                        for line in block.get("lines", []):
                            chars = []
                            for span in line["spans"]:
                                for char in span["chars"]:
                                    x0, y0, x1, y1 = char["bbox"]
                                    center = fitz.Point((x0 + x1) / 2, (y0 + y1) / 2)
                                    if any(center in quad for quad in quads):
                                        chars.append(char["c"])
                            if chars:
                                selected_lines.append("".join(chars).strip())
                    context = "\n".join(selected_lines)
                parent = annot.irt_xref
                comments.append(Comment(str(annot.xref), info.get("title", ""), content,
                                        str(parent) if parent else None, f"第 {page_number + 1} 页",
                                        context, page_number, tuple(annot.rect)))
    if not comments:
        warnings.append("未发现可读取的 PDF 批注对象；已压平的意见、扫描图片和普通页面文字不会作为批注提取。")
    return comments


def render_context(source, comment, scale=1.4):
    """Render a page with a red frame at the annotation; source is never edited."""
    if comment.page is None:
        return None
    with fitz.open(source) as document:
        page = document[comment.page]
        # Limit preview dimensions even for unusually large engineering drawings.
        scale = min(scale, 2200 / max(page.rect.width, page.rect.height))
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False, annots=True)
        image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        if comment.rect:
            rect = fitz.Rect(comment.rect) * page.rotation_matrix
            box = [(rect.x0 - page.rect.x0) * scale, (rect.y0 - page.rect.y0) * scale,
                   (rect.x1 - page.rect.x0) * scale, (rect.y1 - page.rect.y0) * scale]
            ImageDraw.Draw(image).rectangle(box, outline="#dc2626", width=3)
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()
