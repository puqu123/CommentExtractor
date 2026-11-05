"""Optional offline Windows OCR; failure never discards review text/images."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

_rapid_engine = None


def recognize_images_rapid(images, warnings):
    global _rapid_engine
    if not images:
        return
    from .ocr_addon import rapidocr_status
    ready, message = rapidocr_status()
    if not ready:
        raise RuntimeError(message)
    from .progress import stage
    from rapidocr_onnxruntime import RapidOCR
    from onnxruntime import disable_telemetry_events
    # This pinned package includes local ONNX weights; no network model loader.
    if _rapid_engine is None:
        stage(35, "加载离线增强 OCR 模型")
        disable_telemetry_events()
        _rapid_engine = RapidOCR()
    for index, image in enumerate(images, 1):
        stage(40 + int(45 * (index - 1) / len(images)), f"增强 OCR 识别截图 {index}/{len(images)}")
        try:
            result, _ = _rapid_engine(image.data)
            image.ocr_text = "\n".join(line[1] for line in result or [])
            if not image.ocr_text:
                warnings.append("增强 OCR 未识别出文字，原图保留。")
        except Exception as exc:
            warnings.append(f"增强 OCR 截图识别失败（{type(exc).__name__}），原图保留。")
    warnings.append("已执行 RapidOCR 离线增强识别，请对照原图核对。")


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
            from .progress import stage
            stage(40, "识别截图文字")
            process = subprocess.Popen([str(powershell), "-NoProfile", "-NonInteractive", "-Command", command],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       creationflags=subprocess.CREATE_NO_WINDOW, env=environment)
            deadline = time.monotonic() + max(45, min(300, len(images) * 15))
            while process.poll() is None:
                if time.monotonic() > deadline:
                    process.kill()
                    process.communicate()
                    raise subprocess.TimeoutExpired("Windows OCR", 300)
                if output.exists():
                    try:
                        count = len(json.loads(output.read_text(encoding="utf-8-sig")))
                        stage(40 + int(45 * count / len(images)), f"识别截图 {count}/{len(images)}")
                    except (ValueError, OSError):
                        pass
                time.sleep(0.1)
            process.communicate()
            if process.returncode:
                raise subprocess.CalledProcessError(process.returncode, "Windows OCR")
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
