from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QItemSelectionModel
from PySide6.QtGui import QDesktopServices, QFont, QPainter, QColor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QInputDialog, QListWidgetItem,
    QMainWindow, QMessageBox, QTableWidgetItem, QTextEdit, QPlainTextEdit,
    QPushButton, QVBoxLayout, QHBoxLayout, QLabel,
    QStyledItemDelegate, QStyle, QStyleOptionViewItem,
)

from . import __version__
from .extract import extract_file
from .models import ACCEPTANCE, ACCEPTANCE_COLUMN, CONTEXT_COLUMN, HEADERS
from .merge import merge_results, suggest_group_name
from .ui import build_ui, app_icon
from .dialogs import choose_files, choose_directory
from .inputs import collect_files
from .models import Extraction, IMAGE_EXTENSIONS
from .developer_dialog import choose_developer_files
from .support import exception_details, support_report


def content_preview(value):
    return value[:160].rstrip() + "....." if len(value) > 160 else value


class AcceptanceDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        styled.text = ""
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, styled, painter, option.widget)
        value = index.data() or ""
        background, foreground = {
            "": ("#F0F4F8", "#7D8FA2"), "是": ("#E2F5ED", "#127759"),
            "否": ("#FCEDEA", "#B85447"),
            "重复": ("#EDEDF7", "#716B92"),
        }.get(value, ("#F0F4F8", "#7D8FA2"))
        box = option.rect.adjusted(8, 0, -8, 0)
        box.setTop(option.rect.center().y() - 14)
        box.setHeight(28)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(box, 6, 6)
        painter.setPen(QColor(foreground))
        painter.drawText(box, Qt.AlignCenter, value or "待填写")
        painter.restore()

    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        editor.addItems(ACCEPTANCE)
        return editor

    def setEditorData(self, editor, index):
        editor.setCurrentText(index.data() or "")

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText())


class Worker(QThread):
    item_ready = Signal(object)
    progress = Signal(int, int, str)
    exported = Signal(str)
    failure = Signal(str)

    def __init__(self, items, output=None, parent=None, options=None):
        super().__init__(parent)
        self.items = list(items)
        self.output = output
        self.records = []
        self.skipped = []
        self.options = options or {}
        self.diagnostic_events = []

    def run(self):
        for index, item in enumerate(self.items):
            if self.isInterruptionRequested():
                break
            name = (item.source.stem if item.sources else item.source.name) if self.output else Path(item).name
            self.progress.emit(index, len(self.items), name)
            try:
                if self.output:
                    from .export import export_result
                    target = str(export_result(item, self.output))
                    self.exported.emit(target)
                    self.records.append(f"导出成功：{item.source}\n  → {target}")
                else:
                    result = extract_file(item, **self.options)
                    self.item_ready.emit(result)
                    status = '提取失败' if result.error else ('提取完成（有提示，请核对）' if result.warnings else '提取成功')
                    self.records.append(f"{status}：{result.source}\n  {result.error or str(len(result.issues)) + ' 条意见'}")
            except Exception as exc:
                detail = exception_details(exc)
                self.diagnostic_events.append({"phase": "export" if self.output else "extract", "error": detail})
                self.failure.emit(f"[{detail['code']}] {name}：{exc}")
                self.records.append(f"处理失败：{name}\n{traceback.format_exc()}")
                if not self.output:
                    self.item_ready.emit(Extraction(Path(item), error=f"[{detail['code']}] {type(exc).__name__}：{exc}", diagnostics={"error": detail}))
            self.progress.emit(index + 1, len(self.items), name)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.results = []
        self.worker = None
        self.output_paths = []
        self.failures = []
        self.loading = False
        self.last_output = None
        self.batch_history = []
        self.dirty = False
        self.diagnostic_events = []
        build_ui(self, AcceptanceDelegate)
        self.add_button.clicked.connect(self.choose_files)
        self.folder_button.clicked.connect(self.choose_folder)
        self.developer_button.clicked.connect(self.choose_developer)
        self.clear_button.clicked.connect(self.clear_files)
        self.merge_button.clicked.connect(self.merge_files)
        self.export_button.clicked.connect(self.export)
        self.cancel_button.clicked.connect(self.cancel)
        self.file_list.currentRowChanged.connect(self.show_result)
        self.file_list.itemSelectionChanged.connect(self.update_counts)
        self.table.cellDoubleClicked.connect(self.open_cell_text)
        self.table.itemChanged.connect(self.item_changed)
        self.search.textChanged.connect(self.filter_rows)
        self.acceptance_filter.currentTextChanged.connect(self.filter_rows)
        self.report_button.clicked.connect(self.show_report)
        self.open_output_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_output))))
        self.update_counts()

    def busy(self):
        return self.worker is not None

    def update_counts(self):
        issues = [issue for result in self.results if not result.error for issue in result.issues]
        duplicates = sum(issue.acceptance == "重复" for issue in issues)
        exports = sum(not result.error for result in self.results)
        values = {"files": exports, "opinions": len(issues),
                  "replies": sum(len(issue.replies) for issue in issues), "effective": len(issues) - duplicates}
        for key, value in values.items():
            self.stat_values[key].setText(str(value))
        self.stat_notes["effective"].setText(f"已排除 {duplicates} 条重复意见")
        self.file_count.setText(str(len(self.results)))
        source_count = sum(len(r.sources) if r.sources else 1 for r in self.results)
        failed = sum(bool(r.error) for r in self.results)
        self.stat_notes["files"].setText(f"{source_count} 份源文件 · {failed} 份提取失败")
        self.export_button.setText(f"导出 {exports} 份 Excel" if exports else "批量导出 Excel")
        self.export_button.setEnabled(exports > 0 and not self.busy())
        self.merge_button.setEnabled(len(self.file_list.selectedIndexes()) >= 2 and not self.busy())

    def set_busy(self, busy):
        for widget in [self.add_button, self.folder_button, self.developer_button, self.clear_button, self.merge_button,
                       self.export_button, self.table]:
            widget.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.cancel_button.setVisible(busy)
        self.update_counts()

    def choose_files(self):
        files = choose_files(self)
        if files:
            self.add_files(files)

    def choose_folder(self):
        folder = choose_directory(self, "选择评审文件夹（包含子目录）")
        if folder:
            self.add_files([folder])

    def choose_developer(self):
        chosen = choose_developer_files(self)
        if chosen:
            paths, options = chosen
            self.add_files(paths, options=options)

    def add_files(self, paths, options=None):
        if self.busy():
            return
        existing = {source for result in self.results for source in (result.sources or [result.source])}
        files, skipped = collect_files(paths, existing)
        self.batch_history.extend(f"跳过：{path}\n  {reason}" for path, reason in skipped)
        self.report_button.setEnabled(True)
        if not files:
            QMessageBox.information(self, "没有新文件", "未找到新的受支持文件。\n" + "\n".join(f"{p.name}：{r}" for p, r in skipped))
            return
        worker = Worker(files, parent=self, options=options)
        worker.skipped = skipped
        self.start_worker(worker)

    def start_worker(self, worker):
        self.worker = worker
        self.output_paths = []
        self.failures = []
        worker.item_ready.connect(self.add_result)
        worker.progress.connect(self.update_progress)
        worker.exported.connect(self.output_paths.append)
        worker.failure.connect(self.failures.append)
        worker.finished.connect(self.work_finished)
        self.set_busy(True)
        worker.start()

    def add_result(self, result):
        self.results.append(result)
        self.append_file_item(result)
        self.update_counts()
        self.file_list.setCurrentRow(len(self.results) - 1, QItemSelectionModel.ClearAndSelect)

    def append_file_item(self, result):
        status = "提取失败" if result.error else f"{len(result.issues)} 条意见 · {result.comment_count - len(result.issues)} 条回复"
        if not result.error and any(w.startswith("部分提取：") for w in result.warnings):
            status += " · 部分提取，需核对"
        label = f"{result.source.stem}（{len(result.sources)} 份评审）" if result.sources else result.source.name
        item = QListWidgetItem(label + "\n" + status)
        paths = "\n".join(str(path) for path in result.sources) if result.sources else str(result.source)
        item.setToolTip(paths + "\n" + (result.error or "\n".join(result.warnings)))
        self.file_list.addItem(item)

    def update_progress(self, done, total, name):
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.status.setText(f"{done}/{total} · {name}")

    def cancel(self):
        if self.worker:
            self.worker.requestInterruption()
            self.status.setText("将在当前文件处理完成后停止…")

    def work_finished(self):
        worker = self.worker
        interrupted = worker.isInterruptionRequested()
        is_export = bool(worker.output)
        self.batch_history.extend(worker.records)
        self.diagnostic_events.extend(worker.diagnostic_events)
        self.worker = None
        worker.deleteLater()
        self.set_busy(False)
        if is_export:
            # Only acceptance choices require protection against accidental loss.
            # Clear the dirty flag after a complete, successful batch export.
            if not interrupted and not self.failures:
                self.dirty = False
            self.open_output_button.setEnabled(bool(self.output_paths))
            excluded = [r for r in self.results if r.error]
            remaining = len(worker.items) - len(worker.records)
            text = (f"{'已停止' if interrupted else '导出完成'}：计划 {len(worker.items)} 份，"
                    f"成功 {len(self.output_paths)} 份，导出失败 {len(self.failures)} 份，未处理 {remaining} 份；"
                    f"另有 {len(excluded)} 份源文件提取失败，未导出。")
            self.batch_history.append(text)
            report_note = ""
            try:
                report = Path(worker.output) / ("批量导出结果_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:6] + ".txt")
                report.write_text(self.report_text(), encoding="utf-8-sig")
                report_note = f"\n逐文件结果：{report}"
            except OSError as exc:
                report_note = f"\n结果报告无法保存：{exc}。可点击“处理记录”查看。"
            if self.failures or excluded or interrupted:
                errors = self.failures + [f"{r.source.name}：{r.error}" for r in excluded]
                QMessageBox.warning(self, "批量导出结果", text + "\n" + "\n".join(errors) + report_note)
            else:
                QMessageBox.information(self, "导出完成", text + report_note + "\n如有长文本附件，请与 Excel 一起保留。")
        else:
            failed = [r for r in self.results if r.error]
            text = f"{'已停止' if interrupted else '提取完成'} · 本批处理 {len(worker.records)}/{len(worker.items)} 份 · 跳过 {len(worker.skipped)} 份 · 列表中 {len(failed)} 份失败"
            self.batch_history.append(text)
            if failed or worker.skipped or self.failures:
                details = [f"{r.source.name}：{r.error}" for r in failed]
                details.extend(f"跳过 {p.name}：{r}" for p, r in worker.skipped)
                QMessageBox.warning(self, "文件处理结果", text + "\n\n" + "\n".join(details + self.failures))
        self.status.setText(text)

    def report_text(self):
        lines = [f"CommentExtractor {__version__} · 逐文件处理记录", *self.batch_history, "当前列表："]
        for result in self.results:
            sources = result.sources or [result.source]
            lines.append(f"{result.source.name}：{result.error or str(len(result.issues)) + ' 条意见'}")
            lines.extend("  来源：" + str(p) for p in sources)
            lines.extend("  提示：" + warning for warning in dict.fromkeys(result.warnings))
        return "\n\n".join(lines)

    def show_report(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("逐文件处理记录")
        dialog.resize(900, 600)
        layout = QVBoxLayout(dialog)
        note = QLabel("本地处理记录可能包含文件名、路径或原文；对外反馈请使用下方“脱敏诊断”。")
        note.setWordWrap(True)
        layout.addWidget(note)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(self.report_text())
        layout.addWidget(text)
        support = QPushButton("脱敏诊断（可复制）")
        support.clicked.connect(lambda: self.show_support_report(dialog))
        layout.addWidget(support)
        dialog.exec()

    def show_support_report(self, parent=None):
        selected = self.current_result()
        results = [selected] if selected is not None else self.results
        report = support_report(results, self.diagnostic_events)
        phase = "正在导出" if self.worker and self.worker.output else ("正在提取" if self.worker else "空闲")
        report += f"\n界面阶段：{phase}；最近批次进度：{self.progress.value()}/{self.progress.maximum()}。"
        if selected is not None:
            report += f"\n当前选中：左侧列表第 {self.file_list.currentRow() + 1} 项（未复制文件名）。"
        dialog = QDialog(parent or self)
        dialog.setObjectName("supportReportDialog")
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.setWindowTitle("脱敏诊断 · 预览并复制")
        dialog.resize(850, 650)
        layout = QVBoxLayout(dialog)
        note = QLabel("请先预览，按公司规定确认可以传递的技术信息，再复制；程序不会自动发送或上传。")
        note.setWordWrap(True)
        layout.addWidget(note)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(report)
        layout.addWidget(text)
        actions = QHBoxLayout()
        feedback = QLabel("")
        actions.addWidget(feedback, 1)
        copy = QPushButton("复制诊断报告")
        copy.setObjectName("copySupportReport")

        def copy_report():
            QApplication.clipboard().setText(report)
            feedback.setText("已复制，可粘贴为文字。")
        copy.clicked.connect(copy_report)
        actions.addWidget(copy)
        close = QPushButton("关闭")
        close.clicked.connect(dialog.close)
        actions.addWidget(close)
        layout.addLayout(actions)
        dialog.open()

    def current_result(self):
        index = self.file_list.currentRow()
        return self.results[index] if 0 <= index < len(self.results) else None

    def selected_issue(self):
        result = self.current_result()
        row = self.table.currentRow()
        return result.issues[row] if result and 0 <= row < len(result.issues) else None

    def show_result(self, _index=None):
        self.loading = True
        self.table.setRowCount(0)
        result = self.current_result()
        self.file_title.setText((result.source.stem if result.sources else result.source.name) if result else "等待添加文件")
        self.file_title.setToolTip(str(result.source) if result else "")
        if result:
            self.table.setColumnHidden(9, not any(issue.root.screenshots for issue in result.issues))
            self.table.setRowCount(len(result.issues))
            for row, issue in enumerate(result.issues):
                for column, value in enumerate(issue.values(result.source.name)):
                    item = QTableWidgetItem(content_preview(str(value)) if column == CONTEXT_COLUMN else str(value))
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignTop)
                    item.setToolTip(str(value))
                    if column != ACCEPTANCE_COLUMN:
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    self.table.setItem(row, column, item)
            notices = [result.error] if result.error else list(dict.fromkeys(result.warnings))
            if result.error:
                message = "提取失败，具体原因见“处理记录”。"
            elif notices:
                message = f"本文件／合并组有 {len(notices)} 项提取提示，完整说明见“处理记录”。"
            else:
                message = "未发现批注。" if not result.issues else "提取字段只读；“是否接受”可填写，也可以留空导出。"
            self.message.setText(message)
            self.message.setToolTip("\n".join(notices))
        self.loading = False
        self.filter_rows()
        if result and result.issues:
            self.table.selectRow(0)

    def filter_rows(self):
        query = self.search.text().strip().casefold()
        acceptance = self.acceptance_filter.currentText()
        for row in range(self.table.rowCount()):
            result = self.current_result()
            content = " ".join(str(v) for v in result.issues[row].values(result.source.name))
            value = self.table.item(row, ACCEPTANCE_COLUMN).text()
            matches = acceptance == "全部接受情况" or value == ("" if acceptance == "未填写" else acceptance)
            self.table.setRowHidden(row, query not in content.casefold() or not matches)

    def item_changed(self, item):
        if self.loading:
            return
        result = self.current_result()
        if not result:
            return
        issue = result.issues[item.row()]
        value = item.text()
        if item.column() != ACCEPTANCE_COLUMN:
            # Also reject programmatic writes/paste paths, rather than relying
            # solely on the view's read-only flags.
            self.loading = True
            original = str(issue.values(result.source.name)[item.column()])
            item.setText(content_preview(original) if item.column() == CONTEXT_COLUMN else original)
            self.loading = False
            return
        if item.column() == ACCEPTANCE_COLUMN:
            if value not in ACCEPTANCE:
                self.loading = True
                item.setText(issue.acceptance)
                self.loading = False
                return
            issue.acceptance = value
        self.dirty = True
        item.setToolTip(value)
        self.update_counts()
        self.filter_rows()

    def open_cell_text(self, row, column):
        result = self.current_result()
        if not result or not 0 <= row < len(result.issues) or column == ACCEPTANCE_COLUMN:
            return
        if not 0 <= column < len(HEADERS):
            return
        issue = result.issues[row]
        dialog = QDialog(self)
        dialog.setObjectName("cellTextDialog")
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.setWindowTitle(f"{HEADERS[column]} · {issue.id} · {(issue.source or result.source).name}")
        dialog.resize(820, 520)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(str(issue.values(result.source.name)[column]))
        layout.addWidget(text)
        if column == HEADERS.index("上下文截图") and issue.root.screenshots:
            from PySide6.QtCore import QTemporaryDir
            from PySide6.QtGui import QPixmap
            from PySide6.QtWidgets import QLabel, QScrollArea, QWidget
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            panel = QWidget()
            images_layout = QVBoxLayout(panel)
            temp = QTemporaryDir()
            dialog.screenshot_temp = temp
            for index, image in enumerate(issue.root.screenshots, 1):
                pixmap = QPixmap()
                pixmap.loadFromData(image.data)
                label = QLabel(image.name)
                images_layout.addWidget(label)
                if not pixmap.isNull():
                    preview = QLabel()
                    preview.setPixmap(pixmap.scaledToWidth(720, Qt.SmoothTransformation) if pixmap.width() > 720 else pixmap)
                    images_layout.addWidget(preview)
                path = Path(temp.path()) / (str(index) + Path(image.name).suffix)
                path.write_bytes(image.data)
                open_image = QPushButton("打开原图 " + str(index))
                open_image.setEnabled(path.suffix.lower() in IMAGE_EXTENSIONS)
                open_image.clicked.connect(lambda _checked=False, p=path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(p))))
                images_layout.addWidget(open_image)
            scroll.setWidget(panel)
            layout.addWidget(scroll, 3)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(dialog.close)
        layout.addWidget(close_button, alignment=Qt.AlignRight)
        dialog.open()

    def export(self):
        results = [r for r in self.results if not r.error]
        if not results:
            QMessageBox.information(self, "没有可导出数据", "请先添加并提取文件；提取失败的文件不会导出为空表。")
            return
        folder = choose_directory(self, "选择输出目录")
        if folder:
            self.last_output = Path(folder)
            self.start_worker(Worker(results, folder, parent=self))

    def confirm_discard(self):
        return not self.dirty or QMessageBox.question(
            self, "接受情况尚未导出", "已填写的“是否接受”尚未导出到 Excel。确定放弃这些选择？",
            QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel) == QMessageBox.Discard

    def clear_files(self):
        if not self.confirm_discard():
            return
        self.results = []
        self.batch_history = []
        self.diagnostic_events = []
        self.report_button.setEnabled(False)
        self.file_list.clear()
        self.update_counts()
        self.message.setText("点击“添加文件”，或将文件拖入窗口。")
        self.dirty = False

    def merge_files(self):
        rows = sorted(index.row() for index in self.file_list.selectedIndexes())
        if len(rows) < 2:
            QMessageBox.information(self, "请选择多个评审文件", "在左侧按 Ctrl 或 Shift 选中同一文档的两个或更多评审返回文件。")
            return
        selected = [self.results[row] for row in rows]
        name, accepted = QInputDialog.getText(self, "合并同一文档的评审", "被评审文档名称（用于导出文件名）", text=suggest_group_name(selected))
        if not accepted:
            return
        try:
            merged = merge_results(selected, name)
        except ValueError as exc:
            QMessageBox.warning(self, "无法合并", str(exc))
            return
        # Rebuild the list only after the merge is complete. Human acceptance
        # choices are copied and remain dirty until a successful export.
        selected_rows = set(rows)
        self.results = [result for row, result in enumerate(self.results) if row not in selected_rows] + [merged]
        self.file_list.clear()
        for result in self.results:
            self.append_file_item(result)
        self.file_list.setCurrentRow(len(self.results) - 1, QItemSelectionModel.ClearAndSelect)
        self.update_counts()
        note = f"已合并 {len(merged.sources)} 份评审为 {merged.source.stem}，导出时生成 1 份 Excel。"
        self.batch_history.append(note)
        self.status.setText(note + "相同意见请人工将后出现的行标记为“重复”。")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.busy():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.add_files([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
        event.acceptProposedAction()

    def closeEvent(self, event):
        if self.busy():
            self.cancel()
            event.ignore()
        elif self.confirm_discard():
            event.accept()
        else:
            event.ignore()


def main():
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CommentExtractor.Desktop")
    application = QApplication(sys.argv)
    application.setApplicationName("CommentExtractor")
    application.setWindowIcon(app_icon())
    application.setStyle("Fusion")
    application.setFont(QFont("Microsoft YaHei UI", 10))
    window = MainWindow()
    from .diagnostics import install_exception_handler
    install_exception_handler(window)
    window.show()
    paths = [arg for arg in sys.argv[1:] if Path(arg).is_file() or Path(arg).is_dir()]
    if paths:
        window.add_files(paths)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
