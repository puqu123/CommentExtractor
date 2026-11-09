import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from commentextract.models import Screenshot
from commentextract import model_api, model_settings


@pytest.fixture
def service(monkeypatch):
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, self.headers.get("Authorization"), payload))
            message = json.dumps({"choices": [{"message": {"content": self.server.answer}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(message)))
            self.end_headers()
            self.wfile.write(message)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.answer = '{"ids":[2,1,2]}'
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(model_api.time, "sleep", lambda _: None)
    yield {"endpoint": f"http://127.0.0.1:{server.server_port}/v1", "model": "private-qwen", "key": "dummy", "vision": True}, server, requests
    server.shutdown()
    server.server_close()
    thread.join()


def test_image_request_and_only_original_candidate_ids(service):
    settings, server, requests = service
    image = Screenshot("picture.png", b"imagebytes", "测试安装包校验步骤")
    records = [("测试安装包校验步骤", "6.1 校验", None), ("测试安装包校验步骤", "7.1 复用", None), ("无关内容示例", "8.1 其他", None)]
    selected = model_api.select_candidates(settings, image, image.ocr_text, records)
    assert selected == [records[1], records[0]]
    path, auth, body = requests[0]
    assert path == "/v1/chat/completions" and auth == "Bearer dummy"
    assert body["model"] == "private-qwen"
    content = body["messages"][0]["content"]
    assert base64.b64decode(content[1]["image_url"]["url"].split(",", 1)[1]) == image.data
    assert "无关内容示例" not in content[0]["text"]
    server.answer = '{"ids":[999]}'
    with pytest.raises(RuntimeError, match="格式"):
        model_api.select_candidates(settings, image, image.ocr_text, records)


def test_model_can_read_image_when_local_ocr_is_empty(service):
    settings, server, requests = service
    server.answer = "截图中的文字"
    assert model_api.recognize_image(settings, Screenshot("a.png", b"x")) == "截图中的文字"
    assert len(requests[0][2]["messages"][0]["content"]) == 2
    settings["vision"] = False
    assert model_api.recognize_image(settings, Screenshot("a.png", b"x")) == ""


def test_no_candidate_means_no_request(service):
    settings, server, requests = service
    assert model_api.select_candidates(settings, Screenshot("a.png", b"x"), "", [("候选原文", "标题", None)]) is None
    assert not requests


def test_settings_key_is_protected_and_retained(tmp_path, monkeypatch):
    monkeypatch.setattr(model_settings, "settings_path", lambda: tmp_path / "model.json")
    model_settings.save_settings("http://127.0.0.1:8000/v1", "qwen", "secret-sample")
    raw = (tmp_path / "model.json").read_text(encoding="utf-8")
    assert "secret-sample" not in raw
    assert model_settings.load_settings(True)["key"] == "secret-sample"
    model_settings.save_settings("http://127.0.0.1:8000/v1", "qwen2", "", False)
    assert model_settings.load_settings(True)["key"] == "secret-sample"
    assert not model_settings.load_settings()["vision"]


def test_model_failure_preserves_comments_and_local_result(tmp_path, monkeypatch):
    from docx import Document
    from .test_developer_word import make_review
    from commentextract.extract import extract_file
    manual = Document()
    manual.add_heading("1.2 接口", level=1)
    manual.add_paragraph("接口响应时间不超过两秒。")
    reference = tmp_path / "manual.docx"
    manual.save(reference)
    review = make_review(tmp_path / "review.docx")
    monkeypatch.setattr("commentextract.model_settings.load_settings", lambda **kwargs: {"key": "dummy"})
    def ocr(images, warnings):
        for image in images:
            image.ocr_text = "接口响应时间不超过两秒。"
    monkeypatch.setattr("commentextract.ocr.recognize_images", ocr)
    def fail(*args):
        raise RuntimeError("模型服务返回 HTTP 429")
    monkeypatch.setattr("commentextract.model_api.select_candidates", fail)
    result = extract_file(review, developer=True, reference=reference, ai=True)
    assert not result.error and len(result.issues) == 3
    assert "接口" in result.issues[0].root.location
    assert len(result.issues[0].root.screenshots) == 2
    assert any("HTTP 429" in item for item in result.warnings)


def test_model_selected_text_keeps_all_reused_sections(tmp_path, monkeypatch):
    from docx import Document
    from .test_developer_word import make_review
    from commentextract.extract import extract_file
    manual = Document()
    for title in ("1.1 接口", "2.1 复用"):
        manual.add_heading(title, level=1)
        manual.add_paragraph("接口响应时间不超过两秒。")
    reference = tmp_path / "manual.docx"
    manual.save(reference)
    review = make_review(tmp_path / "review.docx")
    monkeypatch.setattr("commentextract.model_settings.load_settings", lambda **kwargs: {"key": "dummy"})
    def ocr(images, warnings):
        for image in images:
            image.ocr_text = "接口响应时间不超过两秒。"
    monkeypatch.setattr("commentextract.ocr.recognize_images", ocr)
    monkeypatch.setattr("commentextract.model_api.select_candidates", lambda settings, image, query, records: [records[1]])
    result = extract_file(review, developer=True, reference=reference, ai=True)
    assert not result.error
    assert "1.1 接口" in result.issues[0].root.location
    assert "2.1 复用" in result.issues[0].root.location
