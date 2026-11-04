"""Run independent baselines against extraction AND exported workbooks.

Default: create synthetic files, manifest, per-file results, manual checklist,
and a ZIP. --manifest runs a separately human-verified real Office/WPS corpus.
No documents, reports or baselines are uploaded anywhere.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import re
import sys
import os
import subprocess
import time
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.compatibility_cases import CompatibilityCase, build_compatibility_cases
from tests.compatibility_check import check_case


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(path):
    path = Path(path).resolve()
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    if document.get("schema_version") != 1 or document.get("origin") not in {"real", "synthetic"}:
        raise ValueError("清单必须声明 schema_version=1、origin=real 或 synthetic。")
    cases = []
    ids = set()
    for record in document.get("cases", []):
        cid = record["id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", cid) or cid in ids:
            raise ValueError("用例编号只能含字母、数字、下划线和连字符，且不能重复。")
        ids.add(cid)
        source = (path.parent / record["file"]).resolve()
        if not source.is_file():
            raise ValueError(f"找不到用例文件：{source}")
        if document["origin"] == "real":
            baseline = record.get("baseline", {})
            if baseline.get("confirmed") is not True or not all(baseline.get(k) for k in ("application", "version", "checked_by", "checked_at")):
                raise ValueError(f"{cid} 缺少人工确认及 Office/WPS 版本信息；不能算作真实兼容性验证。")
            expected_hash = baseline.get("sha256", "")
        else:
            expected_hash = record.get("sha256", "")
        if expected_hash != digest(source):
            raise ValueError(f"{cid} 文件校验不一致：确认基线后文件被修改，或 SHA256 未填写。请重新人工核对。")
        kind = record.get("kind", "positive")
        if kind not in {"positive", "recovery", "negative"}:
            raise ValueError(f"{cid} 用例类别无效")
        expected = record["expected_issues"]
        if not isinstance(expected, list) or any(not all(key in issue for key in ("reviewer", "opinion", "replies")) for issue in expected):
            raise ValueError(f"{cid} 必须提供人工核对的主意见、作者及全部回复，不能只填数量。")
        if kind == "negative" and not record.get("error_contains"):
            raise ValueError(f"{cid} 失败控制用例需要指定预期错误")
        options = dict(record.get("options", {}))
        if options.get("reference"):
            options["reference"] = str((path.parent / options["reference"]).resolve())
        cases.append(CompatibilityCase(cid, source, record.get("description", cid), expected,
                                       kind, tuple(record.get("warning_contains", [])),
                                       record.get("error_contains", ""), options))
    if not cases:
        raise ValueError("清单没有用例；空清单不能算测试通过。")
    return document, cases


def write_template(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    template = {
        "schema_version": 1, "origin": "real",
        "instructions": "从 Office/WPS 人工核对后填写，禁止使用本工具的提取结果自动作为预期。可为每种软件及交叉保存路径增加一条用例。",
        "cases": [{"id": "OFFICE_WORD_01", "file": "请替换为真实文件名.docx", "kind": "positive",
                   "description": "Office 保存的多作者批注及回复",
                   "baseline": {"confirmed": False, "application": "Microsoft Word", "version": "请填写实际版本和构建号", "checked_by": "", "checked_at": "", "sha256": ""},
                   "expected_issues": [{"reviewer": "评审甲", "opinion": "在软件里人工核对的完整意见", "replies": [["答复乙", "完整回复"]]}]}]}
    with path.open("x", encoding="utf-8") as output:
        json.dump(template, output, ensure_ascii=False, indent=2)
    return path


def run_suite(output, manifest=None, executable=None):
    output = Path(output).resolve()
    if executable:
        executable = Path(executable).resolve()
        if not executable.is_file():
            raise ValueError("找不到打包程序：" + str(executable))
    # Validate human baselines before creating output, not after claiming passes.
    if manifest:
        document, cases = load_manifest(manifest)
    output.mkdir(parents=True, exist_ok=False)
    guide = Path(__file__).resolve().parents[1] / "COMPATIBILITY.md"
    if guide.is_file():
        (output / guide.name).write_bytes(guide.read_bytes())
    write_template(output / "真实文件基线模板.json")
    if not manifest:
        cases = build_compatibility_cases(output / "inputs")
        document = {"schema_version": 1, "origin": "synthetic",
                    "producer": "Python 生成及 OOXML 部件构造；未经过 Office/WPS 人工打开验证", "cases": []}
        for case in cases:
            record = asdict(case)
            record["file"] = case.source.relative_to(output).as_posix()
            record.pop("source")
            record["expected_issues"] = record.pop("expected")
            record["sha256"] = digest(case.source)
            document["cases"].append(record)
        (output / "manifest.json").write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        # A local snapshot preserves what was actually verified, including the
        # original baseline/provenance; relative paths refer to the original.
        (output / "manifest-used.json").write_text(json.dumps({"manifest_source": str(Path(manifest).resolve()), "manifest": document}, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = []

    def run_bundle(case, directory):
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.pop("PYTHONHOME", None)
        command = [str(executable), "--cli", str(case.source), "-o", str(directory)]
        if case.options.get("developer"):
            command.append("--developer-word")
            if case.options.get("reference"):
                command.extend(["--reference", str(case.options["reference"])])
            if case.options.get("reviewer"):
                command.extend(["--reviewer", case.options["reviewer"]])
            if not case.options.get("ocr", True):
                command.append("--no-ocr")
        logs = output / "bundle-logs"
        logs.mkdir(exist_ok=True)
        timing = {"case": case.id, "command": command, "timeout_seconds": 120}
        (logs / (case.id + ".json")).write_text(json.dumps(timing, ensure_ascii=False, indent=2), encoding="utf-8")
        start = time.monotonic()
        try:
            completed = subprocess.run(command, cwd=str(output), env=environment, capture_output=True, timeout=120)
            timing.update(seconds=round(time.monotonic() - start, 3), returncode=completed.returncode, timed_out=False)
            (logs / (case.id + ".stdout.log")).write_bytes(completed.stdout or b"")
            (logs / (case.id + ".stderr.log")).write_bytes(completed.stderr or b"")
            return completed.returncode
        except subprocess.TimeoutExpired as exc:
            timing.update(seconds=round(time.monotonic() - start, 3), timed_out=True)
            (logs / (case.id + ".stdout.log")).write_bytes(exc.stdout or b"")
            (logs / (case.id + ".stderr.log")).write_bytes(exc.stderr or b"")
            raise
        finally:
            record["bundle_run"] = timing
            (logs / (case.id + ".json")).write_text(json.dumps(timing, ensure_ascii=False, indent=2), encoding="utf-8")

    for case in cases:
        record = {"id": case.id, "description": case.description, "kind": case.kind,
                  "source": str(case.source), "sha256": digest(case.source),
                  "expected_opinions": len(case.expected),
                  "expected_replies": sum(len(issue.get("replies", [])) for issue in case.expected)}
        try:
            directory = output / "exports" / case.id
            exporter = None
            if executable:
                def exporter(_result, dest):
                    code = run_bundle(case, dest)
                    assert code == 0, f"打包程序退出码 {code}，详见输入文件及源码模式诊断"
                    workbooks = list(Path(dest).glob("*.xlsx"))
                    assert len(workbooks) == 1, "打包程序没有生成唯一输出"
                    return workbooks[0]
            result, target = check_case(case, directory, exporter)
            if executable and case.kind == "negative":
                assert run_bundle(case, directory) != 0, "失败控制用例被打包程序误报为成功"
                assert not list(directory.glob("*.xlsx")), "失败控制用例被导出为假空表"
            record.update(passed=True, actual_opinions=len(result.issues),
                          actual_replies=result.comment_count - len(result.issues),
                          warnings=result.warnings, error=result.error,
                          workbook=str(target) if target else "")
        except Exception as exc:
            record.update(passed=False, failure=f"{type(exc).__name__}：{exc}")
            print(f"FAIL {case.id}：{exc}")
        rows.append(record)
    totals = {kind: {"passed": sum(row["passed"] for row in rows if row["kind"] == kind),
                     "total": sum(row["kind"] == kind for row in rows)} for kind in ("positive", "recovery", "negative")}
    report = {"origin": document["origin"], "executable": str(executable) if executable else "source",
              "executable_sha256": digest(executable) if executable else "", "totals": totals, "results": rows}
    (output / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    labels = {"positive": "正向／内容完整性", "recovery": "异常恢复控制", "negative": "明确失败控制"}
    lines = ["# 批注提取兼容性检查", "", f"来源：**{document['origin']}**。",
             "构造测试通过不代表 Office/WPS 已验证；恢复和预期失败不会计入完整提取成功率。", ""]
    for kind, counts in totals.items():
        lines.append(f"- {labels[kind]}：{counts['passed']}/{counts['total']} 按预期通过。")
    lines += ["", "逐条核对作者、意见、回复、指定原文／定位、Excel 输出和源文件未被修改。", "",
              "| 编号 | 类别 | 场景 | 预期主意见／回复 | 检查结果 |", "|---|---|---|---|---|"]
    for row in rows:
        result = "通过" if row["passed"] else "失败：" + row["failure"].replace("\n", " ").replace("|", "／")
        lines.append(f"| {row['id']} | {labels[row['kind']]} | {row['description']} | {row['expected_opinions']}／{row['expected_replies']} | {result} |")
    lines += ["", "真实文件下一步：按仓库 COMPATIBILITY.md 的 Office/WPS 交叉保存清单核对，使用独立人工基线运行 --manifest。",
              "真实文件、清单和报告应留在 local_data，不提交公司资料。"]
    (output / "测试结果.md").write_text("\n".join(lines), encoding="utf-8")
    manual = ["编号,类别,场景,软件及版本,打开是否正常,主意见数,回复数,作者及全文是否一致,导出是否一致,检查人,结论"]
    import csv
    from io import StringIO
    buffer = StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(manual[0].split(","))
    for case in cases:
        writer.writerow([case.id, labels[case.kind], case.description, "", "", len(case.expected), sum(len(i.get("replies", [])) for i in case.expected), "", "", "", "未人工验证"])
    (output / "人工核对清单.csv").write_text(buffer.getvalue(), encoding="utf-8-sig")
    if not manifest:
        # Never bundle a real corporate corpus automatically.
        archive = Path(str(output) + ".zip")
        with ZipFile(archive, "x", ZIP_DEFLATED) as package:
            for path in sorted(output.rglob("*")):
                if path.is_file():
                    package.write(path, path.relative_to(output.parent))
    print("；".join(f"{labels[k]} {v['passed']}/{v['total']}" for k, v in totals.items()))
    print(output / "测试结果.md")
    return all(row["passed"] for row in rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest", type=Path, help="独立人工核对过的真实文件或构造用例清单")
    parser.add_argument("--executable", type=Path, help="同时通过打包 EXE 实际导出并校验")
    parser.add_argument("--write-template", type=Path, help="生成真实文件人工基线模板，不执行检查")
    args = parser.parse_args()
    if args.write_template:
        print(write_template(args.write_template))
        return 0
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d_%H%M%S")
    output = args.output or Path("local_data") / ("兼容性测试_" + stamp + "_" + uuid4().hex[:4])
    try:
        return 0 if run_suite(output, args.manifest, args.executable) else 1
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
