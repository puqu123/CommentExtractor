"""Show both document roles before opening any native file picker."""
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QMessageBox, QComboBox, QFrame,
)


class DeveloperImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("developerImportDialog")
        self.setWindowTitle("开发评审导入 · 评审 Word 与原手册")
        self.resize(700, 520)
        self.setStyleSheet("""
            QDialog#developerImportDialog { background: #f3f7fa; }
            QLabel, QCheckBox { color: #193652; }
            QLabel#title { font-size: 20px; font-weight: 700; }
            QLabel#subtitle { color: #738b9d; font-size: 12px; }
            QLabel#section { font-size: 14px; font-weight: 600; }
            QLabel#hint { color: #7990a0; font-size: 11px; }
            QFrame#card { background: white; border: 1px solid #e0eaf0; border-radius: 12px; }
            QFrame#card QLabel, QFrame#card QCheckBox { border: none; background: transparent; }
            QLineEdit, QComboBox { background: #f8fafc; border: 1px solid #dce7ee;
                border-radius: 6px; padding: 7px 10px; color: #193652; }
            QPushButton { background: white; border: 1px solid #cbdce8;
                border-radius: 6px; padding: 7px 14px; color: #193652; }
            QPushButton:hover { background: #e8f4f3; }
            QPushButton#startImport { background: #168875; color: white; border: none; }
            QPushButton#startImport:disabled { background: #d6e2e5; color: #83969c; }
        """)
        self.review_files = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 20)
        layout.setSpacing(12)
        heading = QLabel("导入开发评审")
        heading.setObjectName("title")
        layout.addWidget(heading)
        subtitle = QLabel("选择评审文件和原手册，整理意见并定位原文")
        subtitle.setObjectName("subtitle")
        layout.addWidget(subtitle)

        def card(title):
            frame = QFrame()
            frame.setObjectName("card")
            box = QVBoxLayout(frame)
            box.setContentsMargins(16, 14, 16, 14)
            box.setSpacing(9)
            label = QLabel(title)
            label.setObjectName("section")
            box.addWidget(label)
            layout.addWidget(frame)
            return box

        files = card("01   选择文件")
        self.review_edit = QLineEdit()
        self.review_edit.setObjectName("developerReviewFiles")
        self.review_edit.setReadOnly(True)
        self.review_edit.setPlaceholderText("评审 Word · 必选，可多选")
        self.review_edit.setToolTip("选择包含编号意见和截图的开发评审 Word。")
        self.review_button = QPushButton("选择评审文件")
        self.review_button.clicked.connect(self.select_reviews)
        row = QHBoxLayout(); row.addWidget(QLabel("评审文件")); row.addWidget(self.review_edit, 1); row.addWidget(self.review_button)
        files.addLayout(row)
        self.reference_edit = QLineEdit()
        self.reference_edit.setObjectName("developerReference")
        self.reference_edit.setReadOnly(True)
        self.reference_edit.setPlaceholderText("原手册 Word · 用于定位，可选")
        self.reference_edit.setToolTip("选择被评审的原手册，帮助定位原文和页码。")
        self.reference_button = QPushButton("选择原手册")
        self.reference_button.clicked.connect(self.select_reference)
        self.clear_reference_button = QPushButton("清除")
        self.clear_reference_button.clicked.connect(self.reference_edit.clear)
        row = QHBoxLayout(); row.addWidget(QLabel("原手册　")); row.addWidget(self.reference_edit, 1); row.addWidget(self.reference_button); row.addWidget(self.clear_reference_button)
        files.addLayout(row)
        self.reviewer_edit = QLineEdit()
        self.reviewer_edit.setPlaceholderText("评审人 · 可留空")
        self.reviewer_edit.setToolTip("本次选择的评审文件共用同一评审人。")
        row = QHBoxLayout(); row.addWidget(QLabel("评审人　")); row.addWidget(self.reviewer_edit, 1)
        files.addLayout(row)

        settings = card("02   截图处理")
        self.ocr_check = QCheckBox("识别截图文字，辅助定位")
        self.ocr_check.setChecked(True)
        settings.addWidget(self.ocr_check)
        self.ocr_backend = QComboBox()
        self.ocr_backend.addItem("Windows 离线识别", "windows")
        self.ocr_backend.addItem("增强离线识别（RapidOCR）", "rapidocr")
        from .ocr_addon import rapidocr_status
        ready, addon_message = rapidocr_status()
        self.ocr_backend.setToolTip(addon_message)
        if not ready:
            self.ocr_backend.setItemText(1, "增强离线识别（需扩展包）")
            self.ocr_backend.model().item(1).setEnabled(False)
        self.ocr_check.toggled.connect(self.ocr_backend.setEnabled)
        self.content_mode = QComboBox()
        self.content_mode.addItem("导出：文字 + 截图", "both")
        self.content_mode.addItem("导出：仅文字", "text")
        self.content_mode.addItem("导出：仅截图", "images")
        self.content_mode.setToolTip("适用于本次导入的文件，评审意见和回复正文始终保留。")
        row = QHBoxLayout(); row.addWidget(self.ocr_backend, 1); row.addWidget(self.content_mode, 1)
        settings.addLayout(row)
        self.addon_note = QLabel("增强识别已就绪" if ready else "增强识别需要扩展包")
        self.addon_note.setObjectName("hint")
        self.addon_note.setToolTip(addon_message)
        settings.addWidget(self.addon_note)
        layout.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.start_button = buttons.button(QDialogButtonBox.Ok)
        self.start_button.setObjectName("startImport")
        self.start_button.setText("开始提取")
        self.start_button.setEnabled(False)
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def select_reviews(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择开发编写的评审 Word（可多选）", "", "Word 文档 (*.docx)")
        if files:
            self.review_files = files
            self.review_edit.setText("；".join(Path(path).name for path in files))
            self.review_edit.setToolTip("\n".join(files))
            self.start_button.setEnabled(True)

    def select_reference(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择被评审的原手册 Word", "", "Word 文档 (*.docx)")
        if path:
            self.reference_edit.setText(path)
            self.reference_edit.setToolTip(path)

    def accept(self):
        if not self.review_files:
            return
        reference = self.reference_edit.text()
        if reference and Path(reference).resolve() in {Path(path).resolve() for path in self.review_files}:
            QMessageBox.warning(self, "请分别选择两类文件", "原手册不能与开发评审文件是同一份。请选择被评审的原手册，或清除原手册后继续。")
            return
        super().accept()

    def options(self):
        options = {"developer": True, "reviewer": self.reviewer_edit.text().strip(),
                   "reference": self.reference_edit.text() or None, "ocr": self.ocr_check.isChecked()}
        if self.ocr_backend.currentData() != "windows":
            options["ocr_backend"] = self.ocr_backend.currentData()
        if self.content_mode.currentData() != "both":
            options["content_mode"] = self.content_mode.currentData()
        return options


def choose_developer_files(parent):
    dialog = DeveloperImportDialog(parent)
    if dialog.exec() != QDialog.Accepted:
        return None
    return dialog.review_files, dialog.options()
