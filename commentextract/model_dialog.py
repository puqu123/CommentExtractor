"""User configuration for an optional private OpenAI-compatible service."""
from html import escape
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout)
from .model_settings import load_settings, save_settings


class ModelsWorker(QThread):
    fetched = Signal(object)
    failed = Signal(str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings

    def run(self):
        try:
            from .model_api import list_models
            self.fetched.emit(list_models(self.settings))
        except Exception as exc:
            self.failed.emit(str(exc) if isinstance(exc, RuntimeError) else "获取模型列表失败，请检查服务配置")


class ConnectionWorker(QThread):
    checked = Signal(object)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings

    def run(self):
        try:
            from .model_api import test_connection
            self.checked.emit(test_connection(self.settings))
        except Exception:
            self.checked.emit({"text": {"ok": False, "message": "连接测试失败，请检查服务配置"},
                               "image": {"ok": False, "message": "未测试"}})


class ModelSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("模型设置")
        self.resize(700, 390)
        settings = load_settings(include_key=True)
        layout = QVBoxLayout(self)
        note = QLabel("可选：连接公司内部的 OpenAI 兼容服务，辅助定位截图。")
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.endpoint = QLineEdit(settings.get("endpoint", ""))
        self.endpoint.setPlaceholderText("例如 http://内网地址:端口/v1")
        self.model = QLineEdit(settings.get("model", ""))
        self.model.setPlaceholderText("获取列表后选择，或手动填写模型 ID")
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("已保存，留空保持不变" if settings.get("encrypted_key") else "请输入 API Key")
        if settings.get("key"):
            self.key.setText(settings["key"])
        self.vision = QCheckBox("模型支持读取图片")
        self.vision.setChecked(settings.get("vision", True))
        form.addRow("服务地址", self.endpoint)
        form.addRow("模型 ID", self.model)
        form.addRow("API Key", self.key)
        self.model_list = QComboBox()
        self.model_list.addItem("获取后选择模型", "")
        self.fetch_button = QPushButton("获取可用模型")
        self.fetch_button.clicked.connect(self.fetch_models)
        model_row = QHBoxLayout()
        model_row.addWidget(self.model_list, 1)
        model_row.addWidget(self.fetch_button)
        form.addRow("模型列表", model_row)
        self.model_list.currentIndexChanged.connect(self.model_chosen)
        form.addRow("", self.vision)
        layout.addLayout(form)
        self.test_status = QLabel('<span style="color:#738b9d">接口连接：尚未测试　图片读取：尚未测试</span>')
        self.test_status.setWordWrap(True)
        layout.addWidget(self.test_status)
        hint = QLabel("密钥由当前 Windows 账户加密保存在本机。测试只发送程序生成的测试文字和图片；启用 AI 时才发送评审截图与候选原文。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.test_button = QPushButton("测试连接")
        buttons.addButton(self.test_button, QDialogButtonBox.ActionRole)
        self.test_button.clicked.connect(self.test_current_connection)
        buttons.button(QDialogButtonBox.Save).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.buttons = buttons
        self.worker = None

    def test_current_connection(self):
        if self.worker is not None:
            return
        settings = {"endpoint": self.endpoint.text().strip().rstrip("/"),
                    "model": self.model.text().strip(), "key": self.key.text().strip(),
                    "vision": self.vision.isChecked()}
        if not settings["endpoint"] or not settings["model"] or not settings["key"]:
            QMessageBox.warning(self, "配置未完成", "请填写服务地址、模型 ID 和 API Key 后再测试。")
            return
        self.test_button.setEnabled(False)
        self.test_button.setText("正在测试…")
        self.test_status.setText('<span style="color:#738b9d">正在检查文本连接和图片读取…</span>')
        for standard_button in (QDialogButtonBox.Save, QDialogButtonBox.Cancel):
            self.buttons.button(standard_button).setEnabled(False)
        self.worker = ConnectionWorker(settings, self)
        self.worker.checked.connect(self.connection_checked)
        self.worker.finished.connect(self.connection_worker_finished)
        self.worker.start()

    def connection_checked(self, result):
        text = result.get("text", {})
        image = result.get("image", {})
        text_status = "连接成功" if text.get("ok") else "连接失败"
        image_status = "支持" if image.get("ok") else ("不支持或识别失败" if text.get("ok") else "未测试")
        text_color = "#13875e" if text.get("ok") else "#c4473a"
        image_color = "#13875e" if image.get("ok") else ("#c4473a" if text.get("ok") else "#738b9d")
        details = "；".join(item for item in (text.get("message", ""), image.get("message", "")) if item)
        self.test_status.setText(
            f'<span style="color:{text_color}">接口连接：{escape(text_status)}</span>　'
            f'<span style="color:{image_color}">图片读取：{escape(image_status)}</span>'
            + (f'<br><span style="color:#62788b">{escape(details)}</span>' if details else ""))

    def connection_worker_finished(self):
        self.test_button.setEnabled(True)
        self.test_button.setText("测试连接")
        for standard_button in (QDialogButtonBox.Save, QDialogButtonBox.Cancel):
            self.buttons.button(standard_button).setEnabled(True)
        self.worker = None

    def fetch_models(self):
        if self.worker is not None:
            return
        if self.worker is not None:
            return
        settings = {"endpoint": self.endpoint.text().strip().rstrip("/"), "key": self.key.text().strip()}
        if not settings["endpoint"] or not settings["key"]:
            QMessageBox.warning(self, "需要服务配置", "请先填写服务地址和 API Key，再获取模型列表。")
            return
        self.fetch_button.setEnabled(False)
        self.fetch_button.setText("正在获取…")
        self.test_button.setEnabled(False)
        self.buttons.button(QDialogButtonBox.Save).setEnabled(False)
        self.buttons.button(QDialogButtonBox.Cancel).setEnabled(False)
        self.worker = ModelsWorker(settings, self)
        self.worker.fetched.connect(self.models_loaded)
        self.worker.failed.connect(self.models_failed)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def model_chosen(self):
        selected = self.model_list.currentData()
        if selected:
            self.model.setText(selected)

    def models_loaded(self, models):
        self.model_list.clear()
        self.model_list.addItem("请选择模型", "")
        for name in models:
            self.model_list.addItem(name, name)
        self.model_list.setCurrentIndex(0)

    def models_failed(self, message):
        QMessageBox.warning(self, "获取模型失败", message + "。也可以手动填写模型 ID。")

    def worker_finished(self):
        self.fetch_button.setEnabled(True)
        self.fetch_button.setText("获取可用模型")
        self.test_button.setEnabled(True)
        self.buttons.button(QDialogButtonBox.Save).setEnabled(True)
        self.buttons.button(QDialogButtonBox.Cancel).setEnabled(True)
        self.worker = None

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(self, "正在获取模型", "请等待模型列表请求完成后再关闭此窗口。")
            event.ignore()
            return
        super().closeEvent(event)

    def accept(self):
        try:
            save_settings(self.endpoint.text(), self.model.text(), self.key.text(), self.vision.isChecked())
        except (ValueError, RuntimeError, OSError) as exc:
            QMessageBox.warning(self, "无法保存", str(exc))
            return
        super().accept()
