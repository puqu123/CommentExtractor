"""Show both document roles before opening any native file picker."""
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QMessageBox,
)


class DeveloperImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("developerImportDialog")
        self.setWindowTitle("开发评审导入 · 评审 Word 与原手册")
        self.resize(760, 440)
        self.review_files = []
        layout = QVBoxLayout(self)
        heading = QLabel("选择评审意见，再选择它所评审的原手册")
        heading.setStyleSheet("font-size: 17px; font-weight: 600;")
        layout.addWidget(heading)
        hint = QLabel("适用于开发在正文中写“1、意见＋截图”的 Word。两类文件的用途不同：")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addWidget(QLabel("① 开发评审 Word · 提取这里的编号意见和截图"))
        self.review_edit = QLineEdit()
        self.review_edit.setObjectName("developerReviewFiles")
        self.review_edit.setReadOnly(True)
        self.review_edit.setPlaceholderText("尚未选择，可多选同一本手册的评审文件")
        self.review_button = QPushButton("选择评审 Word…")
        self.review_button.clicked.connect(self.select_reviews)
        row = QHBoxLayout()
        row.addWidget(self.review_edit, 1)
        row.addWidget(self.review_button)
        layout.addLayout(row)

        layout.addWidget(QLabel("② 原手册 Word · 辅助定位章节和原文，不作为评审意见导入"))
        self.reference_edit = QLineEdit()
        self.reference_edit.setObjectName("developerReference")
        self.reference_edit.setReadOnly(True)
        self.reference_edit.setPlaceholderText("建议选择对应的原手册（.docx）")
        self.reference_button = QPushButton("选择原手册…")
        self.reference_button.clicked.connect(self.select_reference)
        self.clear_reference_button = QPushButton("清除")
        self.clear_reference_button.clicked.connect(self.reference_edit.clear)
        row = QHBoxLayout()
        row.addWidget(self.reference_edit, 1)
        row.addWidget(self.reference_button)
        row.addWidget(self.clear_reference_button)
        layout.addLayout(row)
        note = QLabel("原手册可放在任意文件夹，无需通过主界面另行添加。留空时仅依据截图可见信息定位。")
        note.setWordWrap(True)
        layout.addWidget(note)

        form = QFormLayout()
        self.reviewer_edit = QLineEdit()
        self.reviewer_edit.setPlaceholderText("可留空；本次所选文件共用这一评审人")
        form.addRow("评审人（可选）", self.reviewer_edit)
        layout.addLayout(form)
        self.ocr_check = QCheckBox("识别截图文字并定位（Windows 离线 OCR）")
        self.ocr_check.setChecked(True)
        layout.addWidget(self.ocr_check)
        note = QLabel("不同手册或不同评审人请分批添加。定位优先使用页码、章节、图表标题或搜索短句，识别结果需核对。")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.start_button = buttons.button(QDialogButtonBox.Ok)
        self.start_button.setText("开始提取评审意见")
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
        return {"developer": True, "reviewer": self.reviewer_edit.text().strip(),
                "reference": self.reference_edit.text() or None, "ocr": self.ocr_check.isChecked()}


def choose_developer_files(parent):
    dialog = DeveloperImportDialog(parent)
    if dialog.exec() != QDialog.Accepted:
        return None
    return dialog.review_files, dialog.options()
