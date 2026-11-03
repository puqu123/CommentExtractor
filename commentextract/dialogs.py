"""Qt file browser without Windows shell extensions or custom icon lookups."""
from PySide6.QtCore import QFileInfo
from PySide6.QtWidgets import QApplication, QFileDialog, QFileIconProvider, QStyle


class BasicFileIcons(QFileIconProvider):
    def icon(self, value):
        if isinstance(value, QFileInfo):
            kind = QStyle.SP_DriveHDIcon if value.isRoot() else (
                QStyle.SP_DirIcon if value.isDir() else QStyle.SP_FileIcon)
        else:
            kind = {QFileIconProvider.Folder: QStyle.SP_DirIcon,
                    QFileIconProvider.Drive: QStyle.SP_DriveHDIcon,
                    QFileIconProvider.Computer: QStyle.SP_ComputerIcon}.get(value, QStyle.SP_FileIcon)
        return QApplication.style().standardIcon(kind)


def file_dialog(parent, title, directory=False):
    dialog = QFileDialog(parent, title)
    dialog.setOption(QFileDialog.DontUseNativeDialog, True)
    dialog.setOption(QFileDialog.DontUseCustomDirectoryIcons, True)
    dialog.basic_icons = BasicFileIcons()  # Qt does not own the provider.
    dialog.setIconProvider(dialog.basic_icons)
    dialog.setFileMode(QFileDialog.Directory if directory else QFileDialog.ExistingFiles)
    if directory:
        dialog.setOption(QFileDialog.ShowDirsOnly, True)
    else:
        dialog.setNameFilter("评审文件 (*.docx *.xlsx *.pptx)")
    dialog.resize(900, 600)
    return dialog


def choose_files(parent):
    dialog = file_dialog(parent, "选择评审文件")
    return dialog.selectedFiles() if dialog.exec() else []


def choose_directory(parent, title):
    dialog = file_dialog(parent, title, directory=True)
    return dialog.selectedFiles()[0] if dialog.exec() else ""
