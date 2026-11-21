#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""反馈包导出器：白名单 + 脱敏，替代裸 zip 打包工作区（对抗审查 R0-7 泄密风险修复件）。

为什么存在：
  对抗审查发现（R0-7）：此前交付文档教用户用裸 zip 命令打包整个工作区 wk/，
  会把客户中文原文片段一并带出去——review.json 的 zh/en 正文、verdict.json 的
  critical_detail/major_detail（内含英文 span 原文与中文注记）、notes.md 自由文本。
  本工具用「白名单 + 脱敏」取代裸 zip：只打包数字台账与判定结论，所有 zh/en
  正文文本在打包前剥离，中文术语换成不可逆指纹，其余文件只列名不进包。

用法：
  python export_feedback.py wk/ --out feedback_20261121.zip [--notes wk/notes.md]

白名单与脱敏规则（逐文件）：
  verdict.json       只保留判定数字与 rubric 指纹：verdict / sampled / seg_passed /
                     seg_pass_rate / critical / major / minor / words_basis /
                     major_per_1000 / rubric_version / rubric_hash / doc_sha256(如有) /
                     seed(如有) / threshold / dim_stats。
                     必须剥离 critical_detail、major_detail（内含英文 span 原文与
                     中文注记）以及任何含 zh/en 正文文本的字段（白名单外一律剥）。
  decisions.json     每条只保留 {kind, date, reason, term_hash}，其中
                     term_hash = sha256(term_zh.encode()) 前 12 位（中文术语 →
                     不可逆指纹）；term_zh / chosen / rejected 原文一律丢弃
                     （chosen 是译法用词，一并脱敏）。
  calib_report.json  只保留 matched / total_anchors / agreement_rate /
                     critical_recall / verdict / fail_reasons(如有)，以及
                     disagree_segments 中的 idx、human_pass/machine_pass 布尔值与
                     human/machine 分数字典——disagree 里的 seg 等文本一律丢弃。
  defect_log.db      SQLite 数字台账，无正文，原样打包。
  notes.md           默认拒绝打包并警告（自由文本可能含客户内容）；人工脱敏后
                     用 --notes 显式传入才打包，包内清单标注「未脱敏自担」。
  其他一切文件       （overrides/、batch/、glossary/、review.json 等工作区内容）
                     一律不打包，仅在 MANIFEST.json 列「已排除」。

输出：zip 内含 MANIFEST.json（导出时间、各文件来源与脱敏规则摘要、排除清单）
      + 上述白名单文件（脱敏后的 JSON 重写，键名不变）。

健壮性：读入一律 utf-8-sig；坏文件给可读错误（哪个文件哪个问题）并跳过，
        不让整个导出崩。工作区缺某白名单文件则跳过并在清单注明。
"""
import sys
import os
import json
import hashlib
import zipfile
import argparse
import datetime

sys.stdout.reconfigure(encoding="utf-8")

TOOL = "export_feedback.py"

# verdict.json 白名单键：判定数字 + rubric 指纹；白名单外一律剥（含 critical_detail/major_detail）
VERDICT_KEEP = ("verdict", "sampled", "seg_passed", "seg_pass_rate", "critical", "major",
                "minor", "words_basis", "major_per_1000", "rubric_version", "rubric_hash",
                "doc_sha256", "seed", "threshold", "dim_stats")

# calib_report.json 白名单键
CALIB_KEEP = ("matched", "total_anchors", "agreement_rate", "critical_recall",
              "verdict", "fail_reasons")
# disagree_segments 条目内允许保留的键（human/machine 为分数字典，含段文本的键一律剥）
CALIB_DISAGREE_KEEP = ("idx", "human_pass", "machine_pass", "human", "machine")

WHITELIST_FILES = ("verdict.json", "decisions.json", "calib_report.json", "defect_log.db")

VERDICT_RULE = ("只保留判定数字与 rubric 指纹（白名单 15 键）；critical_detail / major_detail"
                "（内含英文 span 原文与中文注记）及任何含 zh/en 正文文本的字段一律剥离")
DECISIONS_RULE = ("每条只保留 {kind, date, reason, term_hash}；term_zh 换 sha256 前 12 位不可逆"
                  "指纹；chosen / rejected 译法原文一并丢弃")
CALIB_RULE = ("只保留 matched / total_anchors / agreement_rate / critical_recall / verdict / "
              "fail_reasons；disagree_segments 只留 idx、human_pass/machine_pass 布尔值与 "
              "human/machine 分数字典，seg 等段文本一律丢弃")
DB_RULE = "SQLite 数字台账，无正文，原样打包"
NOTES_EXPLICIT_RULE = "用户显式 --notes 传入；自由文本未脱敏自担（可能含客户内容）"
NOTES_REFUSE_REASON = "notes.md 为自由文本，可能含客户内容——请人工脱敏后用 --notes 显式传入"


def load_json(path):
    """utf-8-sig 读入 JSON；失败抛带上下文的异常，由调用方接住跳过。"""
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def sanitize_verdict(data):
    if not isinstance(data, dict):
        raise ValueError("verdict.json 顶层应为 JSON 对象，实际为 " + type(data).__name__)
    out = {k: data[k] for k in VERDICT_KEEP if k in data}
    stripped = sorted(k for k in data if k not in VERDICT_KEEP)
    stats = {"保留键数": len(out), "剥离键": stripped}
    return out, stats


def sanitize_decisions(data):
    entries = data.get("decisions") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise ValueError('decisions.json 应为 {"decisions":[...]} 或条目数组')
    out_entries = []
    n_hashed = n_dropped = 0
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            raise ValueError(f"decisions 第 {i + 1} 条不是 JSON 对象")
        ne = {k: e[k] for k in ("kind", "date", "reason") if k in e}
        if "term_zh" in e:
            ne["term_hash"] = hashlib.sha256(
                str(e["term_zh"]).encode("utf-8")).hexdigest()[:12]
            n_hashed += 1
        n_dropped += sum(1 for k in e if k not in ("kind", "date", "reason", "term_zh"))
        out_entries.append(ne)
    stats = {"保留条数": len(out_entries), "术语指纹化条数": n_hashed,
             "剥离原文键数(term_zh/chosen/rejected 等)": n_dropped}
    return {"decisions": out_entries}, stats


def sanitize_calib(data):
    if not isinstance(data, dict):
        raise ValueError("calib_report.json 顶层应为 JSON 对象，实际为 " + type(data).__name__)
    out = {k: data[k] for k in CALIB_KEEP if k in data}
    n_seg_dropped = 0
    if isinstance(data.get("disagree_segments"), list):
        ds = []
        for d in data["disagree_segments"]:
            if not isinstance(d, dict):
                continue
            nd = {k: d[k] for k in CALIB_DISAGREE_KEEP
                  if k in d and k != "human" and k != "machine"}
            for k in ("human", "machine"):  # 分数字典浅拷贝，防共享引用
                if isinstance(d.get(k), dict):
                    nd[k] = dict(d[k])
            n_seg_dropped += sum(1 for k in d if k not in CALIB_DISAGREE_KEEP)
            ds.append(nd)
        out["disagree_segments"] = ds
    stripped_top = sorted(k for k in data
                          if k not in CALIB_KEEP and k != "disagree_segments")
    stats = {"保留键": sorted(out), "剥离顶层键": stripped_top,
             "disagree 段数": len(out.get("disagree_segments", [])),
             "disagree 剥离键数(seg 等文本)": n_seg_dropped}
    return out, stats


def build_manifest(wk, packed, skipped, missing, excluded, out_path):
    return {
        "tool": TOOL,
        "purpose": "中译英反馈包（白名单+脱敏）——替代裸 zip 打包工作区，"
                   "防客户中文原文外泄（对抗审查 R0-7 修复件）",
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "source_workspace": os.path.abspath(wk),
        "output_zip": os.path.abspath(out_path),
        "packing_policy": {
            "whitelist": list(WHITELIST_FILES) + ["notes.md（仅 --notes 显式传入才打包）"],
            "notes_rule": "默认拒绝打包；显式传入时标注「未脱敏自担」",
            "non_whitelist": "一律排除，仅在本清单列名",
        },
        "packed": packed,
        "skipped": skipped,
        "missing": missing,
        "excluded": excluded,
    }


def main():
    ap = argparse.ArgumentParser(
        description="中译英反馈包导出器：白名单+脱敏，防客户中文原文外泄（R0-7 修复件）",
        epilog="示例：python export_feedback.py wk/ --out feedback_20261121.zip "
               "[--notes wk/notes.md]",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workspace",
                    help="项目工作区目录（含 verdict.json / decisions.json / "
                         "calib_report.json / defect_log.db，缺哪样跳过哪样并在清单注明）")
    ap.add_argument("--out", required=True, help="输出 zip 路径")
    ap.add_argument("--notes", default="",
                    help="备注文件（如 wk/notes.md）；自由文本默认拒绝打包，"
                         "人工脱敏后显式传入才收，包内标注「未脱敏自担」")
    a = ap.parse_args()

    wk = a.workspace
    if not os.path.isdir(wk):
        print(f"[错误] 工作区目录不存在：{wk}")
        return 2

    packed, skipped, missing, excluded = [], [], [], []
    zf_payloads = {}  # arcname -> str/bytes，按固定顺序写入

    # ---- 白名单 JSON 文件（逐个 try/except，坏文件跳过不崩）----
    for name, sanitizer, rule in (
            ("verdict.json", sanitize_verdict, VERDICT_RULE),
            ("decisions.json", sanitize_decisions, DECISIONS_RULE),
            ("calib_report.json", sanitize_calib, CALIB_RULE)):
        path = os.path.join(wk, name)
        if not os.path.exists(path):
            missing.append({"name": name, "reason": "工作区无此文件，已跳过"})
            continue
        try:
            clean, stats = sanitizer(load_json(path))
            zf_payloads[name] = json.dumps(clean, ensure_ascii=False, indent=1)
            packed.append({"name": name, "source": os.path.abspath(path),
                           "rule": rule, "sanitized": stats})
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError, OSError) as ex:
            skipped.append({"name": name, "error": f"{type(ex).__name__}: {ex}"})
            print(f"[错误] {name} 读取/脱敏失败，已跳过：{ex}")

    # ---- defect_log.db：原样打包 ----
    db_path = os.path.join(wk, "defect_log.db")
    if not os.path.exists(db_path):
        missing.append({"name": "defect_log.db", "reason": "工作区无此文件，已跳过"})
    else:
        try:
            with open(db_path, "rb") as f:
                blob = f.read()
            if not blob.startswith(b"SQLite format 3\x00"):
                print("[警告] defect_log.db 不是标准 SQLite 文件头，仍按原样打包")
            zf_payloads["defect_log.db"] = blob
            packed.append({"name": "defect_log.db", "source": os.path.abspath(db_path),
                           "rule": DB_RULE, "sanitized": {"无需脱敏": True, "字节": len(blob)}})
        except OSError as ex:
            skipped.append({"name": "defect_log.db", "error": f"{type(ex).__name__}: {ex}"})
            print(f"[错误] defect_log.db 读取失败，已跳过：{ex}")

    # ---- notes.md：默认拒绝，--notes 显式传入才打包 ----
    notes_src_abs = ""
    if a.notes:
        if not os.path.exists(a.notes):
            skipped.append({"name": "notes.md（--notes）", "error": f"文件不存在：{a.notes}"})
            print(f"[错误] --notes 指向的文件不存在，未打包：{a.notes}")
        else:
            try:
                with open(a.notes, encoding="utf-8-sig") as f:
                    text = f.read()
                zf_payloads["notes.md"] = text
                notes_src_abs = os.path.abspath(a.notes)
                packed.append({"name": "notes.md", "source": notes_src_abs,
                               "rule": NOTES_EXPLICIT_RULE,
                               "sanitized": {"未脱敏自担": True, "字符": len(text)}})
            except (UnicodeDecodeError, OSError) as ex:
                skipped.append({"name": "notes.md（--notes）",
                                "error": f"{type(ex).__name__}: {ex}"})
                print(f"[错误] --notes 读取失败（需 UTF-8 文本），未打包：{a.notes}（{ex}）")
    elif os.path.exists(os.path.join(wk, "notes.md")):
        print(f"[拒绝] {NOTES_REFUSE_REASON}（本次未打包）")

    # ---- 白名单外的一切文件：列「已排除」 ----
    for root, dirs, files in os.walk(wk):
        dirs.sort()
        for fn in sorted(files):
            full = os.path.join(root, fn)
            if os.path.abspath(full) == notes_src_abs:
                continue
            rel = os.path.relpath(full, wk).replace(os.sep, "/")
            if root == os.path.abspath(wk) and fn in WHITELIST_FILES:
                continue  # 白名单文件：已按 packed / skipped / missing 记账
            if root == os.path.abspath(wk) and fn == "notes.md" and not a.notes:
                excluded.append({"path": rel, "reason": NOTES_REFUSE_REASON})
            else:
                excluded.append({"path": rel, "reason": "不在白名单（工作区内容不进反馈包）"})

    if not packed:
        print("[中止] 工作区内没有任何可打包的白名单文件（连 --notes 也没有）——"
              "请确认目录是否正确；不产出空反馈包")
        return 1

    manifest = build_manifest(wk, packed, skipped, missing, excluded, a.out)
    out_dir = os.path.dirname(os.path.abspath(a.out))
    os.makedirs(out_dir, exist_ok=True)
    with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=1))
        for name, payload in zf_payloads.items():
            zf.writestr(name, payload)

    # ---- 终端打包清单与脱敏摘要 ----
    print("=" * 64)
    print(f"反馈包导出完成 -> {os.path.abspath(a.out)}")
    print("打包清单：")
    for p in packed:
        tag = "打包·脱敏" if p["name"] != "defect_log.db" else "打包·原样"
        print(f"  [{tag}] {p['name']:<18} <- {p['source']}")
        print(f"      规则: {p['rule']}")
        if p["name"] != "defect_log.db":
            print(f"      摘要: " + "；".join(f"{k} {v}" for k, v in p["sanitized"].items()))
        else:
            print(f"      摘要: 无正文不需脱敏（{p['sanitized']['字节']} 字节）")
    if missing:
        print("缺失（已跳过并在清单注明）：")
        for m in missing:
            print(f"  [缺失] {m['name']}  {m['reason']}")
    if skipped:
        print("坏文件（已跳过，导出未中断）：")
        for s in skipped:
            print(f"  [跳过] {s['name']}  {s['error']}")
    if excluded:
        print(f"已排除 {len(excluded)} 项（不进包，仅列名）：")
        for e in excluded:
            print(f"  [排除] {e['path']}  {e['reason']}")
    print(f"合计：打包 {len(packed)} | 缺失 {len(missing)} | 跳过 {len(skipped)} "
          f"| 排除 {len(excluded)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
