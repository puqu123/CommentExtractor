"""Allowlisted diagnostics: never serialize exception messages or document data."""
from collections import Counter
from contextvars import ContextVar
from pathlib import Path
import platform
import re
import sys
import traceback
import hashlib

from . import __version__

ERRORS = {
    "CE-E101": "源文件不存在", "CE-E102": "文件或输出位置无法访问",
    "CE-E201": "无法作为 Office 压缩包读取（可能损坏、加密或格式不符）",
    "CE-E202": "XML 结构无法解析", "CE-E203": "压缩包部件缺失",
    "CE-E204": "单个部件超过大小限制", "CE-E205": "文件关系路径无效",
    "CE-E206": "存在尚不支持且没有可用回退的扩展",
    "CE-E207": "PPT 未恢复到可读取批注，请核对未读部件",
    "CE-E208": "Microsoft Word 转换或页码读取不可用",
    "CE-E301": "不支持的文件格式或导入模式", "CE-E302": "未识别到开发评审编号",
    "CE-E401": "处理超时", "CE-E900": "尚未分类的内部异常",
}
MESSAGES = {
    "CE-W201": "部分批注部件无法读取", "CE-W202": "可选信息无法读取",
    "CE-W203": "使用兼容回退，需核对完整性", "CE-W301": "回复关系不确定，独立保留",
    "CE-W302": "作者信息缺失或无效", "CE-W303": "单元格内容信息缺失或无效",
    "CE-W304": "位置缺失或无效", "CE-W305": "批注编号异常或重复",
    "CE-W401": "截图 OCR 不可用或识别失败", "CE-W402": "图片读取或预览受限",
    "CE-W900": "其他提取提示（原始提示未包含在诊断中）",
    "CE-I201": "PPT 对象原文与截图未支持", "CE-I202": "开发评审按编号归组",
    "CE-I203": "存在首条编号前的说明", "CE-I204": "已执行离线 OCR，候选位置需核对",
}
APP_FILES = {name + ".py" for name in ("app", "extract", "word", "word_locations", "excel", "powerpoint",
             "ooxml", "models", "export", "merge", "inputs", "developer_word", "ocr", "support", "cli",
             "developer_dialog", "ui", "diagnostics", "word_layout", "progress", "ocr_addon", "model_api", "model_settings", "model_dialog", "__init__")}
KINDS = {"word_comments", "word_reply_links", "excel_comments", "excel_threads", "ppt_comments",
         "people", "document", "workbook", "presentation", "styles", "relationships", "other_xml"}
NODE_NAMES = {"comment": "comment", "threadedComment": "threaded_comment", "cm": "ppt_comment",
              "reply": "ppt_reply", "commentEx": "word_reply_link"}
SAFE_TYPES = {"FileNotFoundError", "PermissionError", "BadZipFile", "LargeZipFile", "ParseError", "KeyError",
              "IndexError", "ValueError", "TypeError", "OSError", "RuntimeError", "RecursionError",
              "TimeoutExpired", "TimeoutError", "UnicodeEncodeError", "UnicodeDecodeError",
              "EntitiesForbidden", "DTDForbidden", "ExternalReferenceForbidden"}
_collector = ContextVar("commentextract_support", default=None)


def exception_details(exc):
    name = type(exc).__name__
    code = {"FileNotFoundError": "CE-E101", "PermissionError": "CE-E102", "BadZipFile": "CE-E201",
            "LargeZipFile": "CE-E204", "ParseError": "CE-E202", "KeyError": "CE-E203",
            "TimeoutExpired": "CE-E401", "TimeoutError": "CE-E401"}.get(name, "CE-E900")
    # Only match our fixed messages. The original exception text is never kept.
    if isinstance(exc, ValueError):
        value = str(exc)
        for fragment, candidate in [("超过 128 MB 的单个部件", "CE-E204"), ("文件关系路径无效", "CE-E205"),
                                    ("没有可用的回退分支", "CE-E206"), ("未找到编号意见", "CE-E302"),
                                    ("PPT 无法恢复可读取的批注", "CE-E207"),
                                    (".xls/.ppt 请先", "CE-E301"), ("旧版 Office 文件请先", "CE-E301"), ("模式仅支持 .docx", "CE-E301")]:
            if fragment in value:
                code = candidate
                break
    if isinstance(exc, RuntimeError) and "转换或页码读取未完成" in str(exc):
        code = "CE-E208"
    sites = []
    for frame in traceback.extract_tb(exc.__traceback__):
        filename = Path(frame.filename).name
        if filename in APP_FILES and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,60}", frame.name):
            sites.append(f"{filename}:{frame.lineno}/{frame.name}")
    return {"code": code, "type": name if name in SAFE_TYPES else "OtherException", "sites": sites[-4:]}


def warning_codes(warnings):
    counts = Counter()
    for value in warnings:
        if "首条编号前的说明" in value:
            code = "CE-I203"  # Everything after the prefix can be private prose.
        elif "PPT 当前提供幻灯片编号" in value:
            code = "CE-I201"
        elif "开发评审按顶层编号归组" in value:
            code = "CE-I202"
        elif "截图使用 Windows 离线 OCR" in value:
            code = "CE-I204"
        elif "部分提取：" in value:
            code = "CE-W201"
        elif "兼容回退分支" in value or "兼容恢复：" in value:
            code = "CE-W203"
        elif "重复批注编号" in value or "重复的批注编号" in value:
            code = "CE-W305"
        elif any(word in value for word in ("回复关系", "循环回复", "找不到原批注")):
            code = "CE-W301"
        elif any(word in value for word in ("作者", "姓名", "评审人")):
            code = "CE-W302"
        elif "共享字符串" in value or "工作表内容无法读取" in value:
            code = "CE-W303"
        elif any(word in value for word in ("OCR 不可用", "未识别出文字", "截图识别失败")):
            code = "CE-W401"
        elif "样式信息无法读取" in value:
            code = "CE-W202"
        elif any(word in value for word in ("定位", "位置", "单元格地址", "未关联的批注")):
            code = "CE-W304"
        elif "图片" in value:
            code = "CE-W402"
        elif "无法读取" in value:
            code = "CE-W202"
        else:
            code = "CE-W900"
        counts[code] += 1
    return dict(counts)


def part_kind(part, root=None):
    name = part.rsplit("/", 1)[-1]
    if part.endswith(".rels"):
        return "relationships"
    if root is not None:
        tag = root.tag.rsplit("}", 1)[-1]
        if tag == "comments":
            return "excel_comments" if part.startswith("xl/") else "word_comments"
        if tag in {"ThreadedComments", "threadedComments"}:
            return "excel_threads"
        return {"commentsEx": "word_reply_links", "cmLst": "ppt_comments", "personList": "people",
                "authorLst": "people", "cmAuthorLst": "people", "document": "document",
                "workbook": "workbook", "presentation": "presentation", "styles": "styles"}.get(tag, "other_xml")
    if "commentsExtended" in name:
        return "word_reply_links"
    if "threadedComment" in part:
        return "excel_threads"
    if "comments" in part.lower():
        return {"word": "word_comments", "xl": "excel_comments", "ppt": "ppt_comments"}.get(part.split("/")[0], "other_xml")
    return {"document.xml": "document", "workbook.xml": "workbook", "presentation.xml": "presentation",
            "styles.xml": "styles"}.get(name, "other_xml")


class Collector:
    def __init__(self, source, mode):
        self.source = source
        self.mode = mode
        self.packages = {}
        self.seen = set()
        self.failed = set()
        self.failures = Counter()
        self.nodes = Counter()
        self.parts = Counter()
        self.word_layout = {}
        self.error = {}
        self.token = _collector.set(self)

    def finish(self, result):
        try:
            return {"mode": self.mode, "error": self.error, "messages": warning_codes(result.warnings),
                    "packages": list(self.packages.values()), "parts": dict(self.parts), "nodes": dict(self.nodes),
                    "read_failures": len(self.failed), "failed_parts": dict(self.failures),
                    "word_layout": dict(self.word_layout)}
        finally:
            _collector.reset(self.token)


def note_package(package, path):
    collector = _collector.get()
    if collector is not None:
        package._support_index = len(collector.packages)
        collector.packages[package._support_index] = {
            "role": "source" if Path(path).resolve() == collector.source else "reference",
            "entries": len(package.names), "xml_parts": sum(n.endswith(".xml") for n in package.names)}


def note_xml(package, part, root=None, failed=False):
    collector = _collector.get()
    if collector is None:
        return
    key = (getattr(package, "_support_index", -1), part)
    if failed:
        if key not in collector.failed:
            collector.failed.add(key)
            collector.failures[part_kind(part)] += 1
    elif key not in collector.seen:
        collector.seen.add(key)
        collector.parts[part_kind(part, root)] += 1
        for node in root.iter():
            tag = node.tag.rsplit("}", 1)[-1]
            if tag in NODE_NAMES:
                collector.nodes[NODE_NAMES[tag]] += 1


def _count(value):
    return value if type(value) is int and value >= 0 else 0


def _error_lines(error):
    code = error.get("code")
    code = code if code in ERRORS else "CE-E900"
    name = error.get("type")
    lines = [f"  {code}：{ERRORS[code]}；异常类型：{name if name in SAFE_TYPES else 'OtherException'}"]
    for site in error.get("sites", []):
        if isinstance(site, str) and re.fullmatch(r"[a-z_]+\.py:[0-9]+/[A-Za-z_][A-Za-z_0-9]{0,60}", site) and site.split(":")[0] in APP_FILES:
            lines.append("  代码位置：" + site)
    return lines


def build_id():
    """Fingerprint app code only, never a source document or its path."""
    try:
        digest = hashlib.sha256()
        if getattr(sys, "frozen", False):
            with open(sys.executable, "rb") as executable:
                for block in iter(lambda: executable.read(1024 * 1024), b""):
                    digest.update(block)
        else:
            for name in sorted(APP_FILES):
                path = Path(__file__).with_name(name)
                if path.is_file():
                    digest.update(name.encode("ascii"))
                    digest.update(path.read_bytes())
        return digest.hexdigest()[:16]
    except OSError:
        return "unavailable"


def support_report(results, events=()):
    """Render only explicitly allowed fields, never dump models or raw errors."""
    build = str(sys.getwindowsversion().build) if sys.platform == "win32" else "非 Windows"
    lines = [f"CommentExtractor 脱敏诊断 CE-D1 / v{__version__}",
             "程序构建标识：" + build_id(),
             f"环境：Windows build {build}；Python {platform.python_version()}；免安装程序：{'是' if getattr(sys, 'frozen', False) else '否'}",
             "仅含错误类别、代码位置和结构计数；不含文件名、路径、署名、意见、正文、标题及截图。",
             "结构计数仅反映已成功解析的 XML，含兼容占位，不等同于 Office/WPS 界面显示的线程数。", ""]
    for index, result in enumerate(results, 1):
        extension = result.source.suffix.lower()
        extension = extension if extension in {".docx", ".xlsx", ".pptx", ".review"} else "其他"
        data = result.diagnostics
        mode = "开发评审正文" if data.get("mode") == "developer_word" else "标准批注"
        status = "提取失败" if result.error else ("提取完成，有提示待核对" if result.warnings else "提取完成")
        lines += [f"文件 {index}：{extension}；{mode}；{status}",
                  f"  主意见：{len(result.issues)}；回复：{result.comment_count - len(result.issues)}；原始提示：{len(result.warnings)}"]
        if result.error:
            lines.extend(_error_lines(data.get("error", {})))
        for code, count in sorted(warning_codes(result.warnings).items()):
            if code in MESSAGES:
                lines.append(f"  {code}：{MESSAGES[code]}（{_count(count)} 项）")
        word_layout = data.get("word_layout", {})
        if isinstance(word_layout, dict) and word_layout:
            if word_layout.get("status") == "ok":
                lines.append("  Word 页码诊断：返回段落 " + str(_count(word_layout.get("layout_rows"))) +
                             "；含页码 " + str(_count(word_layout.get("layout_pages"))) +
                             "；截图锚点 " + str(_count(word_layout.get("anchors"))) +
                             "；匹配段落 " + str(_count(word_layout.get("matched"))) +
                             "；关联到页码 " + str(_count(word_layout.get("with_page"))))
            elif word_layout.get("status") == "failed":
                lines.append("  Word 页码诊断：读取失败")
            elif word_layout.get("status") == "no_reference":
                lines.append("  Word 页码诊断：未选择原手册")
        for number, package in enumerate(data.get("packages", []), 1):
            role = "源文件" if package.get("role") == "source" else "参考文件"
            lines.append(f"  包 {number}（{role}）：部件 {_count(package.get('entries'))}；XML {_count(package.get('xml_parts'))}")
        for key, count in sorted(data.get("parts", {}).items()):
            if key in KINDS:
                lines.append(f"  已读部件 {key}：{_count(count)}")
        for key, count in sorted(data.get("nodes", {}).items()):
            if key in NODE_NAMES.values():
                lines.append(f"  标准节点 {key}：{_count(count)}")
        lines.append(f"  未读成功的 XML 部件：{_count(data.get('read_failures'))}")
        for key, count in sorted(data.get("failed_parts", {}).items()):
            if key in KINDS:
                lines.append(f"  未读部件类别 {key}：{_count(count)}")
        if result.sources:
            lines.append(f"  合并组来源数：{len(result.sources)}；请合并前获取各文件的诊断，或清空后重新导入。")
        lines.append("")
    for index, event in enumerate(events, 1):
        lines.append(f"历史操作异常 {index}：" + ("导出" if event.get("phase") == "export" else "处理"))
        lines.extend(_error_lines(event.get("error", {})))
    lines += ["人工补充（请勿填写文档内容）：", "软件及版本：Office / WPS，版本____", "操作：添加文件 / 拖放 / 合并 / 导出____",
              "现象：报错 / 卡住 / 无批注 / 少意见 / 少回复 / 作者不对____", "人工可见主意见数____，回复数____；是否每次发生____"]
    return "\n".join(lines)
