from dataclasses import asdict
import hashlib
import json

import pytest
from openpyxl import load_workbook

from scripts.check_compatibility import load_manifest, run_suite
from tests.compatibility_cases import CompatibilityCase, WORD
from tests.compatibility_check import check_case
from tests.samples import make_word


def real_manifest(tmp_path):
    source = make_word(tmp_path / "real.docx")
    document = {"schema_version": 1, "origin": "real", "cases": [{
        "id": "REAL_WORD", "file": source.name, "kind": "positive", "expected_issues": WORD,
        "baseline": {"confirmed": True, "application": "fixture, not a real vendor verification", "version": "test",
                     "checked_by": "test", "checked_at": "2026-11-04", "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}}]}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path, document


def test_unconfirmed_or_changed_real_baselines_cannot_pass(tmp_path):
    path, document = real_manifest(tmp_path)
    document["cases"][0]["baseline"]["confirmed"] = False
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="人工确认"):
        load_manifest(path)
    document["cases"][0]["baseline"]["confirmed"] = True
    path.write_text(json.dumps(document), encoding="utf-8")
    (tmp_path / "real.docx").write_bytes(b"changed after manual baseline")
    with pytest.raises(ValueError, match="校验不一致"):
        load_manifest(path)


def test_readable_file_with_wrong_content_is_a_failure_not_open_success(tmp_path):
    path, document = real_manifest(tmp_path)
    # Deep-copy the expected data; never mutate the module-level fixtures.
    document = json.loads(json.dumps(document))
    document["cases"][0]["expected_issues"][0]["opinion"] = "独立基线与提取结果不一致"
    path.write_text(json.dumps(document), encoding="utf-8")
    assert not run_suite(tmp_path / "results", path)
    report = json.loads((tmp_path / "results/results.json").read_text(encoding="utf-8"))
    assert report["totals"]["positive"] == {"passed": 0, "total": 1}
    assert report["totals"]["negative"]["total"] == 0
    assert not (tmp_path / "results.zip").exists()  # don't auto-bundle corporate inputs


def test_export_corruption_fails_even_when_extraction_is_correct(tmp_path, monkeypatch):
    from commentextract.export import export_result
    source = make_word(tmp_path / "word.docx")
    case = CompatibilityCase("W", source, "roundtrip", WORD)

    def broken_export(result, output):
        target = export_result(result, output)
        workbook = load_workbook(target)
        workbook["评审汇总"]["G2"] = "故意模拟导出缺字"
        workbook.save(target)
        workbook.close()
        return target
    monkeypatch.setattr("tests.compatibility_check.export_result", broken_export)
    with pytest.raises(AssertionError, match="未完整保留文字"):
        check_case(case, tmp_path / "out")
