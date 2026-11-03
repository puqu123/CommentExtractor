"""Use the platform's standard file and directory pickers (Windows native)."""
from PySide6.QtWidgets import QFileDialog


def choose_files(parent):
    files, _ = QFileDialog.getOpenFileNames(
        parent, "选择评审文件", "", "评审文件 (*.docx *.xlsx *.pptx)")
    return files


def choose_directory(parent, title):
    return QFileDialog.getExistingDirectory(parent, title, "", QFileDialog.ShowDirsOnly)
