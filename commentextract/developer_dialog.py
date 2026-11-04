"""Small import form. All file browsing remains native to Windows."""
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)


def choose_developer_files(parent):
    paths, _ = QFileDialog.getOpenFileNames(parent, "选择开发编写的评审 Word", "", "Word 文档 (*.docx)")
    if not paths:
        return None
    dialog = QDialog(parent)
    dialog.setWindowTitle("导入开发评审 Word")
    dialog.resize(640, 260)
    layout = QVBoxLayout(dialog)
    hint = QLabel(f"已选 {len(paths)} 份评审。按顶层编号分条，将本条的后续文字和截图归入同一意见。")
    hint.setWordWrap(True)
    layout.addWidget(hint)
    form = QFormLayout()
    reviewer = QLineEdit()
    reviewer.setPlaceholderText("可留空；所选文件使用同一评审人")
    form.addRow("评审人", reviewer)
    reference = QLineEdit()
    reference.setPlaceholderText("可选：被评审的原始 Word，用于匹配章节和段落")
    reference.setReadOnly(True)
    browse = QPushButton("选择原文…")

    def select_reference():
        path, _ = QFileDialog.getOpenFileName(dialog, "选择被评审的原始 Word", "", "Word 文档 (*.docx)")
        if path:
            reference.setText(path)
    browse.clicked.connect(select_reference)
    reference_row = QHBoxLayout()
    reference_row.addWidget(reference, 1)
    reference_row.addWidget(browse)
    form.addRow("原始文档", reference_row)
    layout.addLayout(form)
    ocr = QCheckBox("识别截图文字并定位（Windows 离线 OCR）")
    ocr.setChecked(True)
    layout.addWidget(ocr)
    note = QLabel("优先显示页码，其次章节、图表标题或可搜索短句。截图识别和原文匹配位置需核对；无识别能力时仍导出文字和原图。")
    note.setWordWrap(True)
    layout.addWidget(note)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.button(QDialogButtonBox.Ok).setText("开始提取")
    buttons.button(QDialogButtonBox.Cancel).setText("取消")
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    if dialog.exec() != QDialog.Accepted:
        return None
    return paths, {"developer": True, "reviewer": reviewer.text().strip(),
                   "reference": reference.text() or None, "ocr": ocr.isChecked()}
