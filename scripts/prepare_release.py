"""Prepare source, checksums and notes for an already committed version."""
import hashlib
import json
import re
import subprocess
from pathlib import Path


def prepare_release(root):
    root = Path(root).resolve()
    version_text = (root / "commentextract/__init__.py").read_text(encoding="utf-8")
    version = re.search(r'__version__\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"', version_text).group(1)
    committed = subprocess.check_output(["git", "show", "HEAD:commentextract/__init__.py"], cwd=root).decode()
    if f'__version__ = "{version}"' not in committed:
        raise ValueError("Commit the version change before preparing a public release.")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=root).strip():
        raise ValueError("Commit or remove uncommitted changes before preparing a public release.")
    dist = root / "dist"
    dist.mkdir(exist_ok=True)
    binary = dist / f"CommentExtractor-v{version}-win64.zip"
    if not binary.is_file():
        raise ValueError("Build the Windows bundle first.")
    source = dist / f"CommentExtractor-v{version}-source.zip"
    subprocess.run(["git", "archive", "--format=zip", f"--prefix=CommentExtractor-v{version}/",
                    f"--output={source}", "HEAD"], cwd=root, check=True)
    checksums = dist / "SHA256SUMS.txt"
    checksums.write_text("".join(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n"
                                 for path in [binary, source]), encoding="utf-8")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    section = re.search(rf"^## v{re.escape(version)}\b[^\n]*\n(.*?)(?=^## |\Z)",
                        changelog, flags=re.MULTILINE | re.DOTALL)
    if not section:
        raise ValueError("Add this version's release notes to CHANGELOG.md first.")
    notes = dist / f"release-v{version}.md"
    notes.write_text(section.group(1).strip() + "\n\n"
                     "下载 Windows x64 ZIP，完整解压后运行 CommentExtractor.exe。"
                     "源代码及许可文件随版本提供，SHA256SUMS.txt 用于核对压缩包。\n", encoding="utf-8")
    return dict(version=version, binary=str(binary), source=str(source), checksums=str(checksums), notes=str(notes))


if __name__ == "__main__":
    print(json.dumps(prepare_release(Path(__file__).resolve().parents[1])))
