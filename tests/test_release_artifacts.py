import hashlib
from pathlib import Path
import subprocess

import pytest

from scripts.prepare_release import prepare_release


def repository(root):
    (root / "commentextract").mkdir()
    (root / "commentextract" / "__init__.py").write_text('__version__ = "0.2.8"\n', encoding="utf-8")
    (root / "CHANGELOG.md").write_text("## v0.2.8\n\nSynthetic release notes.\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                    "commit", "-qm", "fixture"], cwd=root, check=True)
    # Real repository ignores dist; keep this fixture equivalent.
    (root / ".git" / "info" / "exclude").write_text("dist/\n", encoding="utf-8")
    (root / "dist").mkdir()
    base = root / "dist" / "CommentExtractor-v0.2.8-win64.zip"
    addon = root / "dist" / "CommentExtractor-v0.2.8-ocr-addon-win64.zip"
    base.write_bytes(b"main archive")
    addon.write_bytes(b"optional OCR archive")
    return base, addon


def test_release_contains_both_downloads_and_source_checksums(tmp_path):
    base, addon = repository(tmp_path)
    artifacts = prepare_release(tmp_path)
    assert Path(artifacts["addon"]) == addon
    checksums = Path(artifacts["checksums"]).read_text(encoding="utf-8")
    for path in [base, addon, Path(artifacts["source"])]:
        assert hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name in checksums
    assert "ocr-addon-win64.zip" in Path(artifacts["notes"]).read_text(encoding="utf-8")


def test_release_refuses_missing_addon(tmp_path):
    _, addon = repository(tmp_path)
    addon.unlink()
    with pytest.raises(ValueError, match="OCR addon"):
        prepare_release(tmp_path)
