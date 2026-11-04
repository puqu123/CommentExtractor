"""Desktop presentation layer; extraction and export remain independent."""
from pathlib import Path

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QListWidget, QProgressBar, QPushButton,
    QSplitter, QTableWidget, QVBoxLayout, QWidget, QSizePolicy, QCheckBox,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QStyleOptionButton,
)

from . import __version__
from .models import HEADERS, ACCEPTANCE_COLUMN, ACCEPTANCE

ICON_PATH = Path(__file__).resolve().parent / "assets/app.ico"


def app_icon():
    return QIcon(str(ICON_PATH))


class ReviewTable(QTableWidget):
    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.rowCount():
            painter = QPainter(self.viewport())
            painter.setPen(QColor("#7890A3"))
            painter.drawText(self.viewport().rect(), Qt.AlignCenter,
                             "这里将显示提取出的评审意见\n\n在左侧添加文件，支持多种格式一起选择")


class SelectAllCheckBox(QCheckBox):
    def nextCheckState(self):
        # A partial check should become "all", not cycle through a third
        # user-selected state. Partial is only a summary of the file checkboxes.
        self.setCheckState(Qt.Unchecked if self.checkState() == Qt.Checked else Qt.Checked)

    def paintEvent(self, event):
        super().paintEvent(event)
        option = QStyleOptionButton()
        self.initStyleOption(option)
        rect = self.style().subElementRect(QStyle.SE_CheckBoxIndicator, option, self).adjusted(0, 0, -1, -1)
        painter = QPainter(self)
        paint_check(painter, rect, self.checkState())


def paint_check(painter, rect, state):
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#8BB5C5"), 1))
    painter.setBrush(QColor("#13876F" if state != Qt.Unchecked else "#F8FAFC"))
    painter.drawRoundedRect(rect, 2, 2)
    painter.setPen(QPen(QColor("#FFFFFF"), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    if state == Qt.Checked:
        painter.drawLine(QPointF(rect.left() + 3, rect.center().y()), QPointF(rect.left() + 6, rect.bottom() - 3))
        painter.drawLine(QPointF(rect.left() + 6, rect.bottom() - 3), QPointF(rect.right() - 2, rect.top() + 3))
    elif state == Qt.PartiallyChecked:
        painter.drawLine(QPointF(rect.left() + 3, rect.center().y()), QPointF(rect.right() - 3, rect.center().y()))
    painter.restore()


class FileCheckDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        if not styled.features & QStyleOptionViewItem.HasCheckIndicator:
            return
        # Keep Qt's native hit area and keyboard behavior; only make the
        # indicator legible against the dark file list.
        rect = option.widget.style().subElementRect(QStyle.SE_ItemViewItemCheckIndicator, styled, option.widget).adjusted(0, 0, -1, -1)
        paint_check(painter, rect, styled.checkState)


def build_ui(window, acceptance_delegate):
    window.setWindowTitle(f"CommentExtractor · 评审意见导出 · {__version__}")
    window.setWindowIcon(app_icon())
    window.resize(1520, 960)
    window.setMinimumSize(1100, 720)
    window.setAcceptDrops(True)
    root = QWidget()
    root.setObjectName("workspace")
    window.setCentralWidget(root)
    outer = QVBoxLayout(root)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    masthead = QWidget()
    masthead.setObjectName("masthead")
    brand = QHBoxLayout(masthead)
    brand.setContentsMargins(24, 15, 28, 15)
    brand.setSpacing(13)
    logo = QLabel()
    logo.setPixmap(app_icon().pixmap(44, 44))
    brand.addWidget(logo)
    name_block = QVBoxLayout()
    name_block.setSpacing(2)
    name = QLabel("CommentExtractor")
    name.setObjectName("brandName")
    name_block.addWidget(name)
    tagline = QLabel("评审意见导出")
    tagline.setObjectName("muted")
    name_block.addWidget(tagline)
    brand.addLayout(name_block)
    brand.addStretch()
    offline = QLabel("● 本地处理 · 无需联网")
    offline.setObjectName("offline")
    brand.addWidget(offline)
    outer.addWidget(masthead)

    body = QHBoxLayout()
    body.setContentsMargins(0, 0, 0, 0)
    body.setSpacing(0)
    outer.addLayout(body, 1)
    rail = QWidget()
    rail.setObjectName("sidebar")
    rail.setMinimumWidth(220)
    rail.setMaximumWidth(400)
    rail_layout = QVBoxLayout(rail)
    rail_layout.setContentsMargins(16, 18, 16, 12)
    rail_layout.setSpacing(9)
    rail_title = QHBoxLayout()
    rail_title.addWidget(QLabel("已导入评审"))
    rail_title.addStretch()
    window.file_count = QLabel("0")
    window.file_count.setObjectName("fileCount")
    rail_title.addWidget(window.file_count)
    rail_layout.addLayout(rail_title)
    standard_title = QLabel("文件自带批注")
    rail_layout.addWidget(standard_title)
    standard_hint = QLabel("Word / Excel / PPT，只需评审返回文件")
    standard_hint.setObjectName("railHint")
    standard_hint.setWordWrap(True)
    rail_layout.addWidget(standard_hint)
    add_actions = QHBoxLayout()
    add_actions.setSpacing(8)
    window.add_button = QPushButton("＋ 添加文件")
    window.add_button.setToolTip("在同一文件夹按 Ctrl / Shift 多选 Word、Excel、PPT 文件。")
    window.folder_button = QPushButton("添加文件夹")
    window.folder_button.setToolTip("导入整个文件夹及子目录中的受支持文件。")
    add_actions.addWidget(window.add_button, 3)
    add_actions.addWidget(window.folder_button, 2)
    rail_layout.addLayout(add_actions)
    developer_title = QLabel("开发写在正文中的意见")
    rail_layout.addWidget(developer_title)
    window.developer_button = QPushButton("评审 Word ＋ 原手册…")
    window.developer_button.setToolTip("打开同一个窗口，分别选择开发评审 Word 和被评审的原手册 Word。")
    rail_layout.addWidget(window.developer_button)
    developer_hint = QLabel("编号意见＋截图；原手册用于辅助定位")
    developer_hint.setObjectName("railHint")
    developer_hint.setWordWrap(True)
    rail_layout.addWidget(developer_hint)
    checks = QHBoxLayout()
    window.select_all_box = SelectAllCheckBox("全选文件")
    window.select_all_box.setTristate(True)
    window.select_all_box.setChecked(True)
    checks.addWidget(window.select_all_box)
    checks.addStretch()
    window.remove_checked_button = QPushButton("清除文件")
    window.remove_checked_button.setObjectName("removeChecked")
    window.remove_checked_button.setToolTip("从列表清除文件的文件，硬盘上的原文件不受影响。")
    checks.addWidget(window.remove_checked_button)
    rail_layout.addLayout(checks)
    window.checked_count = QLabel("已选 0 / 0")
    window.checked_count.setObjectName("railHint")
    rail_layout.addWidget(window.checked_count)
    window.file_list = QListWidget()
    window.file_list.setObjectName("files")
    window.file_list.setItemDelegate(FileCheckDelegate(window.file_list))
    window.file_list.setSelectionMode(QAbstractItemView.SingleSelection)
    window.file_list.setWordWrap(True)
    window.file_list.setSpacing(5)
    rail_layout.addWidget(window.file_list, 1)
    selection_hint = QLabel("勾选决定导出范围；点击文件查看意见。新导入文件默认勾选。")
    selection_hint.setObjectName("railHint")
    selection_hint.setWordWrap(True)
    rail_layout.addWidget(selection_hint)
    window.clear_button = QPushButton("清空列表")
    window.clear_button.setObjectName("railQuiet")
    rail_layout.addWidget(window.clear_button)
    version = QLabel(f"v{__version__}  ·  AGPL-3.0")
    version.setObjectName("railHint")
    rail_layout.addWidget(version)
    window.workspace_splitter = QSplitter(Qt.Horizontal)
    window.workspace_splitter.setChildrenCollapsible(False)
    window.workspace_splitter.setHandleWidth(6)
    window.workspace_splitter.addWidget(rail)
    body.addWidget(window.workspace_splitter)

    main_panel = QWidget()
    main = QVBoxLayout(main_panel)
    main.setContentsMargins(24, 22, 24, 18)
    main.setSpacing(16)
    stats = QHBoxLayout()
    stats.setSpacing(12)
    window.stat_values = {}
    window.stat_notes = {}
    for key, title, note in [("files", "可导出文件", "在左侧选择导出范围"),
                             ("opinions", "评审意见", "保留所有评审人的记录"),
                             ("replies", "已有回复", "从源文件直接提取"),
                             ("effective", "有效意见", "已排除 0 条重复意见")]:
        card = QFrame()
        card.setObjectName("statCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 8, 12, 8)
        card_layout.setSpacing(3)
        card_heading = QHBoxLayout()
        label = QLabel(title)
        label.setObjectName("muted")
        value = QLabel("0")
        value.setObjectName("statValue")
        footnote = QLabel(note)
        footnote.setObjectName("statNote")
        card_heading.addWidget(label)
        card_heading.addStretch()
        card_heading.addWidget(value)
        card_layout.addLayout(card_heading)
        card_layout.addWidget(footnote)
        window.stat_values[key] = value
        window.stat_notes[key] = footnote
        stats.addWidget(card, 1)
    main.addLayout(stats)

    table_card = QFrame()
    table_card.setObjectName("card")
    table_layout = QVBoxLayout(table_card)
    table_layout.setContentsMargins(16, 14, 16, 12)
    table_layout.setSpacing(11)
    table_heading = QHBoxLayout()
    label = QLabel("评审意见")
    label.setObjectName("sectionTitle")
    table_heading.addWidget(label)
    window.file_title = QLabel("等待添加文件")
    window.file_title.setObjectName("muted")
    window.file_title.setMinimumWidth(0)
    window.file_title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    table_heading.addWidget(window.file_title, 1)
    read_only = QLabel("提取字段只读")
    read_only.setObjectName("readOnly")
    table_heading.addWidget(read_only)
    table_layout.addLayout(table_heading)
    filters = QHBoxLayout()
    window.search = QLineEdit()
    window.search.setPlaceholderText("搜索文件名、意见、原文、评审人或回复…")
    window.search.setClearButtonEnabled(True)
    filters.addWidget(window.search, 1)
    window.acceptance_filter = QComboBox()
    window.acceptance_filter.addItems(["全部接受情况", "未填写", *ACCEPTANCE[1:]])
    window.acceptance_filter.setMinimumWidth(135)
    filters.addWidget(window.acceptance_filter)
    table_layout.addLayout(filters)
    window.table = ReviewTable(0, len(HEADERS))
    window.table.setHorizontalHeaderLabels(HEADERS)
    window.table.setAlternatingRowColors(True)
    window.table.setSelectionBehavior(QAbstractItemView.SelectRows)
    window.table.setSelectionMode(QAbstractItemView.SingleSelection)
    window.table.setWordWrap(True)
    window.table.setFrameShape(QFrame.NoFrame)
    window.table.setMinimumHeight(280)
    window.table.verticalHeader().setVisible(True)
    window.table.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)
    window.table.verticalHeader().setMinimumSectionSize(40)
    window.table.verticalHeader().setDefaultSectionSize(96)
    window.table.verticalHeader().setToolTip("拖动行号之间的边界调整行高。")
    window.table.setItemDelegateForColumn(ACCEPTANCE_COLUMN, acceptance_delegate(window.table))
    for index, width in enumerate([86, 200, 160, 205, 95, 255, 106, 105, 240, 110]):
        window.table.setColumnWidth(index, width)
    window.table.setColumnHidden(9, True)  # Reserved export column; Office screenshots are not produced.
    window.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    window.table.horizontalHeader().setSectionsMovable(True)
    window.table.horizontalHeader().setToolTip("拖动列边界调整宽度；拖动表头调整列顺序。")
    # Put the text people are reading inside even the smallest supported window.
    # Logical column indexes and the exported workbook schema stay unchanged.
    visual_order = ["评审人", "评审意见", "是否接受", "回复人", "回复内容",
                    "对应原文／内容", "文件名", "位置", "意见编号", "上下文截图"]
    header = window.table.horizontalHeader()
    for visual_index, name in enumerate(visual_order):
        header.moveSection(header.visualIndex(HEADERS.index(name)), visual_index)
    table_layout.addWidget(window.table, 1)
    window.message = QLabel("支持拖入文件或文件夹，可混合选择 Word / Excel / PPT。")
    window.message.setWordWrap(False)
    window.message.setMinimumWidth(0)
    window.message.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
    window.message.setObjectName("tableHint")
    table_layout.addWidget(window.message)
    reading_hint = QLabel("拖动表头／行号边界调整列宽和行高；双击内容查看全文。")
    reading_hint.setObjectName("tableHint")
    table_layout.addWidget(reading_hint)
    main.addWidget(table_card, 1)

    footer = QHBoxLayout()
    footer.setSpacing(12)
    window.status = QLabel("就绪 · 原文件只读")
    window.status.setObjectName("muted")
    window.status.setMinimumWidth(0)
    window.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    footer.addWidget(window.status, 1)
    window.open_output_button = QPushButton("打开输出目录")
    window.open_output_button.setEnabled(False)
    footer.addWidget(window.open_output_button)
    window.report_button = QPushButton("处理记录")
    window.report_button.setEnabled(False)
    footer.addWidget(window.report_button)
    window.cancel_button = QPushButton("停止处理")
    window.cancel_button.setVisible(False)
    footer.addWidget(window.cancel_button)
    window.separate_export_button = QPushButton("分别导出（0份）")
    window.separate_export_button.setMinimumHeight(42)
    window.separate_export_button.setEnabled(False)
    footer.addWidget(window.separate_export_button)
    window.summary_export_button = QPushButton("汇总导出（0份）")
    window.summary_export_button.setObjectName("primary")
    window.summary_export_button.setMinimumWidth(136)
    window.summary_export_button.setMinimumHeight(42)
    window.summary_export_button.setEnabled(False)
    footer.addWidget(window.summary_export_button)
    main.addLayout(footer)
    window.progress = QProgressBar()
    window.progress.setRange(0, 1)
    window.progress.setValue(0)
    window.progress.setTextVisible(False)
    window.progress.setMaximumHeight(3)
    main.addWidget(window.progress)
    window.workspace_splitter.addWidget(main_panel)
    window.workspace_splitter.setStretchFactor(1, 1)
    window.workspace_splitter.setSizes([260, 1260])

    window.setStyleSheet("""
        QMainWindow, #workspace { background: #F2F5F9; }
        QWidget { font-family: 'Microsoft YaHei UI'; font-size: 13px; color: #243C50; }
        QLabel { background: transparent; }
        #masthead { background: white; border-bottom: 1px solid #E3EAF1; }
        #brandName { font-size: 20px; font-weight: 700; color: #17324B; }
        #pageTitle { font-size: 23px; font-weight: 700; color: #17324B; }
        #muted { color: #718397; }
        #offline { color: #12826A; background: #E6F5F0; padding: 8px 13px; border-radius: 14px; }
        #sidebar { background: #152C43; }
        #sidebar QLabel { color: #DFE9F2; }
        #sidebar #railHint { color: #90A7BB; font-size: 11px; }
        #sidebar #fileCount { color: #B8D9EA; background: #25445E; padding: 3px 9px; border-radius: 9px; }
        #sidebar QCheckBox { color: #DFE9F2; }
        #sidebar QCheckBox::indicator { width: 16px; height: 16px; }
        #sidebar QPushButton#removeChecked { padding: 4px 7px; }
        #files { border: none; background: transparent; color: #D1E1ED; outline: none; }
        #files::item { padding: 14px 10px; border-radius: 7px; color: #D1E1ED; }
        #files::item:selected { background: #2C526E; color: white; }
        #files::item:hover { background: #213F58; }
        #files::indicator { width: 16px; height: 16px; }
        QPushButton { background: white; border: 1px solid #D9E3EC; border-radius: 6px; padding: 9px 12px; }
        QPushButton:hover { background: #F0F6FB; border-color: #A8BDCF; }
        QPushButton:disabled { background: #F2F5F8; color: #A2AFBD; border-color: #E2E8EF; }
        #sidebar QPushButton { color: #DAE8F3; background: #24445D; border-color: #34556E; }
        #sidebar QPushButton:hover { background: #315671; }
        #sidebar QPushButton:disabled { color: #6B869B; background: #1C354C; border-color: #29465E; }
        #sidebar #railQuiet { background: transparent; border: none; color: #9DB1C4; }
        QPushButton#primary { background: #13876F; border-color: #13876F; color: white; font-weight: 600; }
        QPushButton#primary:hover { background: #0E7460; }
        QPushButton#primary:disabled { background: #ABCCC4; border-color: #ABCCC4; color: #F5FAF8; }
        #smallButton { padding: 4px 9px; font-size: 11px; }
        #statCard, #card { background: white; border: 1px solid #E2E9F0; border-radius: 9px; }
        #statValue { font-size: 23px; font-weight: 700; color: #1B3D55; }
        #statNote { font-size: 11px; color: #8394A5; }
        #sectionTitle { font-size: 14px; font-weight: 600; color: #213C53; }
        #readOnly { font-size: 11px; color: #688299; background: #F1F5F9; padding: 4px 9px; border-radius: 4px; }
        QLineEdit, QComboBox { background: #F8FAFC; border: 1px solid #E0E7EF; border-radius: 6px; padding: 9px 11px; }
        QLineEdit:focus, QComboBox:focus { border-color: #65AB9B; }
        QComboBox QAbstractItemView { background: white; selection-background-color: #E1F3ED; color: #243C50; }
        QTableWidget { background: white; alternate-background-color: #FAFCFE; gridline-color: #EEF2F6; selection-background-color: #E7F3F8; selection-color: #163D57; outline: none; }
        QTableWidget::item { padding: 7px 6px; }
        QHeaderView::section { background: #F2F6FA; color: #587087; border: none; border-right: 1px solid #E8EEF4; padding: 11px 7px; font-weight: 500; }
        #tableHint { color: #7A8FA2; font-size: 11px; }
        QScrollArea { background: #F2F6FA; border: 1px solid #E8EEF3; border-radius: 5px; }
        QProgressBar { border: none; background: #E4ECEF; }
        QProgressBar::chunk { background: #26A88C; }
        QSplitter::handle { background: #DCE5ED; }
        QSplitter::handle:hover { background: #8DB9C7; }
    """)
