from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QItemSelectionModel
from PySide6.QtGui import QDesktopServices, QFont, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QSplitter, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
    QAbstractItemView, QStyledItemDelegate,
)

from . import __version__
from .extract import SUPPORTED, extract_file
from .models import ACCEPTANCE, HEADERS
from .merge import merge_results, suggest_group_name


class AcceptanceDelegate(QStyledItemDelegate):
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
        self.setWindowTitle(f"评审意见提取 · CommentExtract {__version__}")
        self.resize(1480, 880)
        self.setMinimumSize(1060, 680)
        self.setAcceptDrops(True)
        self.results = []
        self.worker = None
        self.output_paths = []
        self.failures = []
        self.loading = False
        self.last_output = None
        self.preview_cache = {}
        self.preview_data = None
        self.dirty = False
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(22, 18, 22, 16)
        layout.setSpacing(14)
        titlebar = QHBoxLayout()
        title = QLabel("评审意见提取")
        title.setObjectName("title")
        titlebar.addWidget(title)
        subtitle = QLabel("Word · Excel · PDF · PowerPoint")
        subtitle.setObjectName("subtitle")
        titlebar.addWidget(subtitle)
        titlebar.addStretch()
        badge = QLabel("● 本地离线")
        badge.setObjectName("badge")
        titlebar.addWidget(badge)
        layout.addLayout(titlebar)
        hint = QLabel("可一次添加多种格式的文件，批量导出对应 Excel。提取内容只读，“是否接受”可选填。")
        hint.setObjectName("subtitle")
        layout.addWidget(hint)
        toolbar = QHBoxLayout()
        self.add_button = QPushButton("添加文件（可多选）")
        self.folder_button = QPushButton("添加文件夹")
        self.clear_button = QPushButton("清空列表")
        self.merge_button = QPushButton("合并所选评审文件")
        self.merge_button.setToolTip("在左侧按 Ctrl 或 Shift 选中同一文档的多个评审返回文件，再合并为一份 Excel。")
        self.export_button = QPushButton("批量导出 Excel")
        self.export_button.setObjectName("primary")
        self.cancel_button = QPushButton("停止")
        self.cancel_button.setEnabled(False)
        self.shots = QCheckBox("导出 PDF 截图")
        self.shots.setChecked(True)
        for button in [self.add_button, self.folder_button, self.merge_button, self.clear_button]:
            toolbar.addWidget(button)
        toolbar.addStretch()
        toolbar.addWidget(self.shots)
        toolbar.addWidget(self.cancel_button)
        toolbar.addWidget(self.export_button)
        layout.addLayout(toolbar)
        splitter = QSplitter()
        layout.addWidget(splitter, 1)
        files_panel = QWidget()
        files_layout = QVBoxLayout(files_panel)
        files_layout.setContentsMargins(0, 0, 10, 0)
        files_layout.addWidget(QLabel("评审文件"))
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.file_list.setWordWrap(True)
        self.file_list.setSpacing(4)
        files_layout.addWidget(self.file_list)
        self.file_count = QLabel("尚未添加文件")
        files_layout.addWidget(self.file_count)
        splitter.addWidget(files_panel)
        main_panel = QWidget()
        main_layout = QVBoxLayout(main_panel)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("筛选当前文件的意见、评审人、回复或位置…")
        main_layout.addWidget(self.search)
        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setWordWrap(True)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(82)
        self.table.setItemDelegateForColumn(5, AcceptanceDelegate(self.table))
        widths = [90, 155, 230, 100, 270, 100, 130, 280, 110]
        for index, width in enumerate(widths):
            self.table.setColumnWidth(index, width)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        main_layout.addWidget(self.table, 1)
        self.message = QLabel("点击“添加文件”，或将文件拖入窗口。")
        self.message.setWordWrap(True)
        self.message.setObjectName("subtitle")
        main_layout.addWidget(self.message)
        splitter.addWidget(main_panel)
        detail_panel = QWidget()
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(10, 0, 0, 0)
        detail_bar = QHBoxLayout()
        detail_bar.addWidget(QLabel("意见详情"))
        detail_bar.addStretch()
        detail_layout.addLayout(detail_bar)
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setPlaceholderText("选择一条意见查看原文、评审意见和已有回复。\n\n提取内容只读；仅“是否接受”可选填。")
        detail_layout.addWidget(self.detail, 1)
        self.preview_label = QLabel("PDF 上下文预览")
        preview_bar = QHBoxLayout()
        preview_bar.addWidget(self.preview_label)
        preview_bar.addStretch()
        self.zoom_button = QPushButton("查看大图")
        self.zoom_button.setEnabled(False)
        preview_bar.addWidget(self.zoom_button)
        detail_layout.addLayout(preview_bar)
        self.preview = QLabel("选择 PDF 意见后显示所在页面\n红框标出批注位置")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setObjectName("preview")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.preview)
        detail_layout.addWidget(scroll, 2)
        splitter.addWidget(detail_panel)
        splitter.setSizes([220, 850, 360])
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(5)
        layout.addWidget(self.progress)
        footer = QHBoxLayout()
        self.status = QLabel("就绪 · 支持 .docx / .xlsx / .pdf / .pptx")
        footer.addWidget(self.status, 1)
        self.open_output_button = QPushButton("打开输出目录")
        self.open_output_button.setEnabled(False)
        footer.addWidget(self.open_output_button)
        layout.addLayout(footer)
        self.add_button.clicked.connect(self.choose_files)
        self.folder_button.clicked.connect(self.choose_folder)
        self.clear_button.clicked.connect(self.clear_files)
        self.merge_button.clicked.connect(self.merge_files)
        self.export_button.clicked.connect(self.export)
        self.cancel_button.clicked.connect(self.cancel)
        self.file_list.currentRowChanged.connect(self.show_result)
        self.table.itemSelectionChanged.connect(self.show_detail)
        self.table.itemChanged.connect(self.item_changed)
        self.search.textChanged.connect(self.filter_rows)
        self.zoom_button.clicked.connect(self.open_preview)
        self.open_output_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_output))))
        self.setStyleSheet("""
            QMainWindow { background: #f5f7fb; }
            QWidget { font-family: 'Microsoft YaHei UI'; font-size: 12px; color: #243447; }
            QLabel#title { font-size: 25px; font-weight: 700; color: #193652; }
            QLabel#subtitle { color: #63758a; }
            QLabel#badge { color: #147d64; background: #e2f3ed; padding: 7px 12px; border-radius: 12px; }
            QPushButton { background: white; border: 1px solid #ccd7e4; border-radius: 6px; padding: 8px 12px; }
            QPushButton:hover { background: #eaf2fa; }
            QPushButton:disabled { color: #9aa8b6; background: #f2f4f7; }
            QPushButton#primary { background: #216bb5; color: white; border-color: #216bb5; }
            QPushButton#primary:disabled { background: #a8bdd5; border-color: #a8bdd5; }
            QLineEdit, QTextEdit, QListWidget, QTableWidget, QScrollArea { background: white; border: 1px solid #dbe3ed; border-radius: 6px; }
            QLineEdit { padding: 10px; }
            QTableWidget { gridline-color: #e4eaf2; alternate-background-color: #f5f9fd; }
            QHeaderView::section { background: #e8eff7; color: #193652; padding: 10px 6px; border: 0; border-right: 1px solid #dbe3ed; font-weight: 600; }
            QListWidget::item { padding: 12px 8px; border-radius: 5px; }
            QListWidget::item:selected { background: #dcebf9; color: #163e66; }
            QLabel#preview { color: #6b7d90; background: #edf1f6; padding: 8px; }
            QProgressBar { border: none; background: #e2e9f1; }
            QProgressBar::chunk { background: #2c83c6; }
        """)

    def busy(self):
        return self.worker is not None and self.worker.isRunning()

    def set_busy(self, busy):
        for widget in [self.add_button, self.folder_button, self.clear_button, self.merge_button,
                       self.export_button, self.table, self.shots]:
            widget.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)

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
        self.file_count.setText(f"{len(self.results)} 个文件")
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
        for row in range(self.table.rowCount()):
            content = " ".join(self.table.item(row, col).text() for col in range(self.table.columnCount()))
            self.table.setRowHidden(row, query not in content.casefold())

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
        self.file_count.setText("尚未添加文件")
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
        self.file_count.setText(f"{len(self.results)} 个文件／评审组")
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
    application = QApplication(sys.argv)
    application.setApplicationName("CommentExtract")
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
