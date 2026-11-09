import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QLabel, QMessageBox

from commentextract.developer_dialog import DeveloperImportDialog


@pytest.fixture(scope="module")
def application():
    return QApplication.instance() or QApplication([])


def test_both_document_roles_are_visible_before_file_picker(application, monkeypatch):
    calls = []
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *args: calls.append(args))
    dialog = DeveloperImportDialog()
    dialog.show()
    application.processEvents()
    assert calls == []
    assert dialog.reference_edit.isVisible() and dialog.review_edit.isVisible()
    assert dialog.reference_button.isVisible() and dialog.review_button.isVisible()
    assert not dialog.start_button.isEnabled()
    assert "原手册" in dialog.reference_edit.placeholderText()
    dialog.close()


def test_native_pickers_choose_roles_and_cancel_keeps_selection(application, tmp_path, monkeypatch):
    dialog = DeveloperImportDialog()
    reviews = [str(tmp_path / "评审甲.docx"), str(tmp_path / "评审乙.docx")]
    reference = str(tmp_path / "原手册.docx")
    calls = []

    def choose_reviews(parent, title, directory, filters):
        calls.append(title)
        assert parent is dialog and filters == "Word 文档 (*.doc *.docx)"
        return (reviews if len(calls) == 1 else []), filters
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", choose_reviews)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda parent, title, directory, filters: (reference, filters))
    dialog.select_reference()  # The original may be selected first.
    assert not dialog.start_button.isEnabled()
    dialog.select_reviews()
    assert dialog.start_button.isEnabled()
    dialog.select_reviews()  # Cancel leaves the previous reviews intact.
    assert dialog.review_files == reviews
    dialog.reviewer_edit.setText("开发甲")
    dialog.ocr_check.setChecked(False)
    assert dialog.options() == {"developer": True, "reviewer": "开发甲", "reference": reference, "ocr": False}
    dialog.accept()
    assert dialog.result() == QDialog.Accepted


def test_reference_cannot_be_same_file_and_is_optional(application, tmp_path, monkeypatch):
    dialog = DeveloperImportDialog()
    source = str(tmp_path / "评审.docx")
    dialog.review_files = [source]
    dialog.reference_edit.setText(source)
    notices = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: notices.append(args[-1]))
    dialog.accept()
    assert notices and dialog.result() != QDialog.Accepted
    dialog.clear_reference_button.click()
    dialog.accept()
    assert dialog.result() == QDialog.Accepted
    assert dialog.options()["reference"] is None
