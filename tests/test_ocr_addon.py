import json
from pathlib import Path
import sys
from zipfile import ZipFile

import pytest

from commentextract import __version__
from commentextract.ocr_addon import rapidocr_status, OCR_ENGINE, OCR_COMPATIBILITY
from scripts.package_windows import package_windows, is_ocr_file


def fake_bundle(root):
    bundle = root / "CommentExtractor"
    entries = {"CommentExtractor.exe": b"synthetic executable",
               "_internal/PIL/_imaging.pyd": b"base picture support",
               "_internal/cv2/cv2.pyd": b"opencv",
               "_internal/numpy.libs/blas.dll": b"numpy dll",
               "_internal/Shapely.libs/geos.dll": b"geos dll",
               "licenses/RapidOCR.txt": b"synthetic license"}
    for index in range(3):
        entries[f"_internal/rapidocr_onnxruntime/models/{index}.onnx"] = b"local model"
    for name, data in entries.items():
        path = bundle / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return bundle


def frozen(monkeypatch, root):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(root), raising=False)


def test_split_archives_overlay_restores_addon_and_base_has_no_ocr(tmp_path, monkeypatch):
    bundle = fake_bundle(tmp_path / "build")
    base, addon = package_windows(bundle, tmp_path / "downloads")
    destination = tmp_path / "fresh"
    with ZipFile(base) as archive:
        assert not any(is_ocr_file(Path(n).relative_to("CommentExtractor")) for n in archive.namelist())
        assert "CommentExtractor/_internal/PIL/_imaging.pyd" in archive.namelist()
        archive.extractall(destination)
    runtime = destination / "CommentExtractor" / "_internal"
    frozen(monkeypatch, runtime)
    ready, message = rapidocr_status()
    assert not ready and "扩展包" in message
    with ZipFile(addon) as archive:
        with ZipFile(base) as main_archive:
            assert not set(archive.namelist()).intersection(main_archive.namelist())
        assert "CommentExtractor/CommentExtractor.exe" not in archive.namelist()
        assert len([name for name in archive.namelist() if name.endswith(".onnx")]) == 3
        assert any("ocr-licenses" in name for name in archive.namelist())
        archive.extractall(destination)
    assert rapidocr_status()[0]
    (runtime / "cv2" / "cv2.pyd").write_bytes(b"short")
    assert not rapidocr_status()[0]


def test_100mb_gate_keeps_previous_archives_when_packaging_fails(tmp_path):
    bundle = fake_bundle(tmp_path / "build")
    base, addon = package_windows(bundle, tmp_path / "downloads")
    before = {p: p.read_bytes() for p in (base, addon)}
    with pytest.raises(ValueError, match="download limit"):
        package_windows(bundle, base.parent, max_bytes=1)
    assert all(p.read_bytes() == value for p, value in before.items())
    assert not list(base.parent.glob("tmp*.zip"))


@pytest.mark.parametrize("manifest", [[], {}, {"schema": 999},
    {"schema": 1, "app_version": __version__, "files": {}},
    {"schema": 1, "app_version": __version__, "files": {"../outside": 10}}])
def test_invalid_or_mismatched_addon_does_not_crash(tmp_path, monkeypatch, manifest):
    frozen(monkeypatch, tmp_path)
    (tmp_path / "ocr-addon.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert not rapidocr_status()[0]


def test_compatible_addon_survives_new_app_version_and_incompatible_is_rejected(tmp_path, monkeypatch):
    bundle = fake_bundle(tmp_path / "build")
    _, addon = package_windows(bundle, tmp_path / "downloads")
    with ZipFile(addon) as archive:
        archive.extractall(tmp_path / "app")
    runtime = tmp_path / "app" / "CommentExtractor" / "_internal"
    frozen(monkeypatch, runtime)
    marker = runtime / "ocr-addon.json"
    manifest = json.loads(marker.read_text(encoding="utf-8"))
    manifest["app_version"] = "0.2.11"
    marker.write_text(json.dumps(manifest), encoding="utf-8")
    assert rapidocr_status()[0]
    manifest["compatibility"] = OCR_COMPATIBILITY + "-incompatible"
    marker.write_text(json.dumps(manifest), encoding="utf-8")
    assert not rapidocr_status()[0]
    manifest["compatibility"] = OCR_COMPATIBILITY
    manifest["engine"] = OCR_ENGINE + "-different"
    marker.write_text(json.dumps(manifest), encoding="utf-8")
    assert not rapidocr_status()[0]


def test_legacy_v011_manifest_is_recognized_with_all_files(tmp_path, monkeypatch):
    import hashlib
    from commentextract import ocr_addon
    runtime = tmp_path / "_internal"
    file = runtime / "cv2" / "cv2.pyd"
    file.parent.mkdir(parents=True)
    file.write_bytes(b"legacy")
    files = {"cv2/cv2.pyd": 6}
    canonical = json.dumps(files, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()
    monkeypatch.setattr(ocr_addon, "LEGACY_FILES_DIGEST", hashlib.sha256(canonical).hexdigest())
    frozen(monkeypatch, runtime)
    marker = runtime / "ocr-addon.json"
    marker.write_text(json.dumps({"schema": 1, "app_version": "0.2.11", "engine": OCR_ENGINE, "files": files}), encoding="utf-8")
    assert rapidocr_status()[0]
    file.unlink()
    assert not rapidocr_status()[0]


def test_missing_addon_disables_only_enhanced_choice(tmp_path, monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from commentextract.developer_dialog import DeveloperImportDialog
    app = QApplication.instance() or QApplication([])
    frozen(monkeypatch, tmp_path)
    dialog = DeveloperImportDialog()
    assert dialog.ocr_backend.currentData() == "windows"
    assert dialog.ocr_backend.model().item(0).isEnabled()
    assert not dialog.ocr_backend.model().item(1).isEnabled()
    assert "扩展包" in dialog.addon_note.text()
    dialog.close()

def test_dialog_content_choice():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from commentextract.developer_dialog import DeveloperImportDialog
    app = QApplication.instance() or QApplication([])
    dialog = DeveloperImportDialog()
    dialog.content_mode.setCurrentIndex(2)
    assert dialog.options()["content_mode"] == "images"
    dialog.close()


def test_mixed_developer_export_options_survive_summary(tmp_path):
    from commentextract.models import Comment, Screenshot, Issue, Extraction
    from commentextract.merge import merge_results
    from commentextract.export import export_result
    from openpyxl import load_workbook
    from .test_v028 import png
    img = Screenshot("a.png", png("red"))
    one = Extraction(tmp_path / "one.docx", [Issue("R1", Comment("1", "A", "意见1", context="文字1", screenshots=[img], export_mode="text"))])
    two = Extraction(tmp_path / "two.docx", [Issue("R2", Comment("2", "B", "意见2", context="文字2", screenshots=[img], export_mode="images"))])
    result = merge_results([one, two], "汇总")
    wb = load_workbook(export_result(result, tmp_path / "out"))
    sheet = wb["评审汇总"]
    assert sheet["D2"].value == "文字1" and sheet["E2"].value is None
    assert sheet["D3"].value is None and sheet["E3"].hyperlink
    assert sheet["G2"].value == "意见1" and sheet["G3"].value == "意见2"
    wb.close()


def test_gui_import_enables_pages_and_keeps_content_choice(tmp_path, monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from commentextract.app import MainWindow
    from .test_developer_word import make_review
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    captured = []
    monkeypatch.setattr(window, "start_worker", captured.append)
    window.add_files([make_review(tmp_path / "review.docx")], options={"developer": True, "content_mode": "images"})
    assert captured[0].options["word_pages"] is True
    assert captured[0].import_content_mode == "images"
    assert not hasattr(window, "word_pages_box") and not hasattr(window, "content_mode")
    window.close()
