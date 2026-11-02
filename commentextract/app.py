from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QItemSelectionModel
from PySide6.QtGui import QDesktopServices, QFont, QPixmap, QPainter, QColor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QSplitter, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
    QAbstractItemView, QStyledItemDelegate, QStyle, QStyleOptionViewItem,
)

from . import __version__
from .extract import SUPPORTED, extract_file
from .models import ACCEPTANCE, HEADERS
from .merge import merge_results, suggest_group_name
from .ui import build_ui, app_icon


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
            "否": ("#FCEDEA", "#B85447"), "部分接受": ("#FFF3D9", "#98701C"),
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

    def __init__(self, items, output=None, screenshots=True, parent=None):
        super().__init__(parent)
        self.items = list(items)
        self.output = output
        self.screenshots = screenshots

    def run(self):
        for index, item in enumerate(self.items):
            if self.isInterruptionRequested():
                break
            name = (item.source.stem if item.sources else item.source.name) if self.output else Path(item).name
            self.progress.emit(index, len(self.items), name)
            try:
                if self.output:
                    from .export import export_result
                    self.exported.emit(str(export_result(item, self.output, self.screenshots)))
                else:
                    self.item_ready.emit(extract_file(item))
            except Exception as exc:
                self.failure.emit(f"{name}：{exc}")
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
        self.preview_cache = {}
        self.preview_data = None
        self.dirty = False
        build_ui(self, AcceptanceDelegate)
        self.add_button.clicked.connect(self.choose_files)
        self.folder_button.clicked.connect(self.choose_folder)
        self.clear_button.clicked.connect(self.clear_files)
        self.merge_button.clicked.connect(self.merge_files)
        self.export_button.clicked.connect(self.export)
        self.cancel_button.clicked.connect(self.cancel)
        self.file_list.currentRowChanged.connect(self.show_result)
        self.file_list.itemSelectionChanged.connect(self.update_counts)
        self.table.itemSelectionChanged.connect(self.show_detail)
        self.table.itemChanged.connect(self.item_changed)
        self.search.textChanged.connect(self.filter_rows)
        self.acceptance_filter.currentTextChanged.connect(self.filter_rows)
        self.zoom_button.clicked.connect(self.open_preview)
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
        self.export_button.setText(f"导出 {exports} 份 Excel" if exports else "批量导出 Excel")
        self.export_button.setEnabled(exports > 0 and not self.busy())
        self.merge_button.setEnabled(len(self.file_list.selectedIndexes()) >= 2 and not self.busy())

    def set_busy(self, busy):
        for widget in [self.add_button, self.folder_button, self.clear_button, self.merge_button,
                       self.export_button, self.table, self.shots]:
            widget.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.cancel_button.setVisible(busy)
        self.update_counts()

    def choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择评审文件", "", "评审文件 (*.docx *.xlsx *.pdf *.pptx)")
        if files:
            self.add_files(files)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择评审文件夹（包含子目录）")
        if folder:
            self.add_files([folder])

    def add_files(self, paths):
        if self.busy():
            return
        files = []
        for value in paths:
            path = Path(value)
            files.extend(sorted(path.rglob("*")) if path.is_dir() else [path])
        existing = {source for result in self.results for source in (result.sources or [result.source])}
        files = list(dict.fromkeys(p.resolve() for p in files if p.is_file()
                                   and p.suffix.lower() in SUPPORTED and not p.name.startswith("~$")
                                   and "_评审意见" not in p.stem and p.resolve() not in existing))
        if not files:
            QMessageBox.information(self, "没有新文件", "未找到新的受支持文件。临时文件和本工具的导出表会自动跳过。")
            return
        self.start_worker(Worker(files, parent=self))

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
        self.worker = None
        worker.deleteLater()
        self.set_busy(False)
        self.show_detail()
        if is_export:
            # Only acceptance choices require protection against accidental loss.
            # Clear the dirty flag after a complete, successful batch export.
            if not interrupted and not self.failures:
                self.dirty = False
            self.open_output_button.setEnabled(bool(self.output_paths))
            text = f"{'已停止' if interrupted else '导出完成'}：{len(self.output_paths)} 个 Excel"
            if self.failures:
                QMessageBox.warning(self, "部分文件导出失败", "\n".join(self.failures))
            elif self.output_paths:
                QMessageBox.information(self, "导出完成", text + "。\n截图和长文本附件请与 Excel 一起保留。")
        else:
            failed = sum(bool(r.error) for r in self.results)
            text = f"{'已停止' if interrupted else '提取完成'} · {len(self.results)} 个文件 · {failed} 个失败"
            if self.failures:
                QMessageBox.warning(self, "处理异常", "\n".join(self.failures))
        self.status.setText(text)

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
        self.detail.clear()
        self.preview.clear()
        self.preview_data = None
        self.zoom_button.setEnabled(False)
        self.preview.setText("选择 PDF 意见查看上下文")
        result = self.current_result()
        self.file_title.setText((result.source.stem if result.sources else result.source.name) if result else "等待添加文件")
        self.file_title.setToolTip(str(result.source) if result else "")
        if result:
            self.table.setRowCount(len(result.issues))
            for row, issue in enumerate(result.issues):
                for column, value in enumerate(issue.values("可预览" if issue.root.page is not None else "")):
                    item = QTableWidgetItem(str(value))
                    item.setToolTip(str(value))
                    if column != 5:
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    self.table.setItem(row, column, item)
            notices = [result.error] if result.error else result.warnings
            self.message.setText("\n".join(notices) if notices else (
                "未发现批注。" if not result.issues else "提取内容只读。“是否接受”可选是、否、部分接受或重复；重复行保留，统计时只计一次。"))
        self.loading = False
        self.filter_rows()
        if result and result.issues:
            self.table.selectRow(0)

    def filter_rows(self):
        query = self.search.text().strip().casefold()
        acceptance = self.acceptance_filter.currentText()
        for row in range(self.table.rowCount()):
            content = " ".join(self.table.item(row, col).text() for col in range(self.table.columnCount()))
            value = self.table.item(row, 5).text()
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
        if item.column() != 5:
            # Also reject programmatic writes/paste paths, rather than relying
            # solely on the view's read-only flags.
            self.loading = True
            item.setText(str(issue.values("可预览" if issue.root.page is not None else "")[item.column()]))
            self.loading = False
            return
        if item.column() == 5:
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
        self.show_detail()

    def show_detail(self):
        issue = self.selected_issue()
        if not issue:
            return
        self.detail.setPlainText(
            f"{issue.id} · {issue.root.location}\n\n对应内容\n{issue.root.context or '未记录明确对应原文'}"
            f"\n\n评审人：{issue.root.author or '未署名'}\n{issue.root.text}"
            f"\n\n是否接受：{issue.acceptance or '待填写'}\n\n回复\n{issue.values()[7] or '暂无回复'}")
        self.preview.clear()
        self.preview_data = None
        self.zoom_button.setEnabled(False)
        if self.busy():
            # MuPDF must not render in the GUI while the worker reads/renders
            # PDF documents. Resume previews only after that worker has ended.
            self.preview.setText("当前任务完成后显示上下文预览。")
            return
        if issue.root.page is None:
            result = self.current_result()
            source = issue.source or result.source
            self.preview.setText("PPT 截图暂未支持，请按幻灯片编号查看原文件。" if source.suffix.lower() == ".pptx"
                                 else "可依据原文及位置查看原文件。")
            return
        try:
            result = self.current_result()
            source = issue.source or result.source
            key = (str(source), issue.id)
            data = self.preview_cache.get(key)
            if data is None:
                from .pdf import render_context
                data = render_context(source, issue.root)
                if len(self.preview_cache) >= 8:
                    self.preview_cache.pop(next(iter(self.preview_cache)))
                self.preview_cache[key] = data
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            self.preview_data = data
            self.zoom_button.setEnabled(True)
            self.preview.setPixmap(pixmap.scaledToWidth(360, Qt.SmoothTransformation))
        except Exception as exc:
            self.preview.setText(f"预览不可用：{exc}")

    def open_preview(self):
        if not self.preview_data:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("PDF 上下文 · 红框为批注位置")
        dialog.resize(1000, 800)
        layout = QVBoxLayout(dialog)
        scroll = QScrollArea()
        label = QLabel()
        pixmap = QPixmap()
        pixmap.loadFromData(self.preview_data)
        label.setPixmap(pixmap)
        scroll.setWidget(label)
        layout.addWidget(scroll)
        dialog.exec()

    def export(self):
        results = [r for r in self.results if not r.error]
        if not results:
            QMessageBox.information(self, "没有可导出数据", "请先添加并提取文件；提取失败的文件不会导出为空表。")
            return
        folder = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if folder:
            self.last_output = Path(folder)
            self.start_worker(Worker(results, folder, self.shots.isChecked(), self))

    def confirm_discard(self):
        return not self.dirty or QMessageBox.question(
            self, "接受情况尚未导出", "已填写的“是否接受”尚未导出到 Excel。确定放弃这些选择？",
            QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel) == QMessageBox.Discard

    def clear_files(self):
        if not self.confirm_discard():
            return
        self.results = []
        self.preview_cache.clear()
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
        self.preview_cache.clear()
        self.file_list.clear()
        for result in self.results:
            self.append_file_item(result)
        self.file_list.setCurrentRow(len(self.results) - 1, QItemSelectionModel.ClearAndSelect)
        self.update_counts()
        self.status.setText(f"已合并 {len(merged.sources)} 份评审。相同意见请人工将后出现的行标记为“重复”。")

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
    window.show()
    paths = [arg for arg in sys.argv[1:] if Path(arg).is_file() or Path(arg).is_dir()]
    if paths:
        window.add_files(paths)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
