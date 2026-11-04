"""Optional offline Windows OCR; failure never discards review text/images."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def recognize_images(images, warnings):
    if not images:
        return
    if sys.platform != "win32":
        warnings.append("截图 OCR 仅支持 Windows；已保留截图，请人工核对位置。")
        return
    script = Path(__file__).with_name("assets") / "windows_ocr.ps1"
    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    with tempfile.TemporaryDirectory(prefix="CommentExtractor-ocr-") as folder:
        folder = Path(folder)
        paths = []
        for index, image in enumerate(images):
            path = folder / (str(index) + Path(image.name).suffix)
            path.write_bytes(image.data)
            paths.append(str(path))
        manifest, output = folder / "input.json", folder / "result.json"
        manifest.write_text(json.dumps(paths), encoding="utf-8")
        try:
            # Supply data through environment variables, never interpolate a
            # document path into PowerShell source or change execution policy.
            environment = os.environ.copy()
            environment["COMMENTEXTRACT_OCR_MANIFEST"] = str(manifest)
            environment["COMMENTEXTRACT_OCR_OUTPUT"] = str(output)
            command = "& {\n" + script.read_text(encoding="utf-8-sig") + "\n} -Manifest $env:COMMENTEXTRACT_OCR_MANIFEST -OutputFile $env:COMMENTEXTRACT_OCR_OUTPUT"
            subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-Command", command],
                           capture_output=True, timeout=max(45, min(300, len(images) * 15)),
                           creationflags=subprocess.CREATE_NO_WINDOW, check=True, env=environment)
            results = json.loads(output.read_text(encoding="utf-8-sig"))
            if not isinstance(results, list) or len(results) != len(images):
                raise ValueError("OCR 返回数量不匹配")
            for image, result in zip(images, results):
                image.ocr_text = result.get("text", "")
                if result.get("error") or not image.ocr_text.strip():
                    warnings.append(f"截图 {image.name} 未识别出文字：{result.get('error') or '无可读文字'}；原图已保留。")
            languages = sorted({r.get("language", "") for r in results} - {""})
            warnings.append("截图使用 Windows 离线 OCR（" + "、".join(languages) + "）；识别结果和候选位置请对照原图核对。")
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            warnings.append(f"Windows 离线 OCR 不可用（{type(exc).__name__}）；可能缺少语言包或被系统策略限制。意见和截图已保留，位置请人工核对。")
