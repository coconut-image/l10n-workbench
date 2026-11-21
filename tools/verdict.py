# -*- coding: utf-8 -*-
"""阈值判定：对评审 JSON 做段级+稿级判定，产出绑定 rubric-hash、交付物 hash 与评审证书的判定报告。

用法：
  python verdict.py wk/review.json --rubric assets/rubric-v1.md \
                  --cert wk/cert_<reviewer>.json \
                  [--sample wk/sample.json] \
                  [--docx report_EN_v2.docx | --doc-words N] \
                  [--diff wk/changed_idx.txt] [--out wk/verdict.json]
  python verdict.py --hash assets/rubric-v1.md        # 只算 rubric 指纹

判据（rubric 定版）：稿级通过 = critical 0 处 且 major <= 2 处/千词（minor 不计）。
段级通过 = 四维 F/L/T/S 齐全且均 >= 3 且无 critical/major。

fail-closed 原则（对抗审查 R0-1/2/3/5/6 修复）：
- 输入不完整/畸形（空评审、抽样缺段>5%、缺维度、未知 severity）从严或拒绝，绝不静默放行
- 未知 severity 一律计 major（宁严勿纵）
- 判定绑定交付 docx 的 sha256（--docx），防 PASS 判定移植到别的稿子
- --cert 校验评审者已上岗且 rubric 版本一致，防未校准评审混入
- 增量场景 --diff：改动段必须全部覆盖评审，缺一段即 FAIL
"""
import sys, json, hashlib, argparse, zipfile, re
from xml.etree import ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
PASS_LINE = 3
DENSITY_MAX = 2.0
DIMS = ("F", "L", "T", "S")
SEV_NORM = {"critical", "major", "minor"}


def rubric_hash(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]


def docx_info(path):
    """返回 (sha256[:16], 全文字数)。docx 正文 w:t 拼接后按空白切词。"""
    h = hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    text = " ".join(t.text or "" for t in root.iter(W + "t"))
    return h, len(text.split())


def norm_errors(seg):
    """severity 归一 + 未知值从严计 major。返回 (errors, unknown_n)。"""
    out, unknown = [], 0
    for e in seg.get("errors", []):
        sev = str(e.get("severity", "")).strip().lower()
        if sev not in SEV_NORM:
            sev, unknown = "major", unknown + 1     # 未知 severity 宁严勿纵
        ne = dict(e)
        ne["severity"] = sev
        out.append(ne)
    return out, unknown


def check_seg(seg):
    """返回 (seg_pass, malformed_reason)。四维必须齐全且为 0-4 整数。"""
    s = seg.get("scores", {})
    for d in DIMS:
        v = s.get(d)
        if not isinstance(v, int) or not (0 <= v <= 4):
            return False, f"维度 {d} 缺失或非 0-4 整数"
    errors, _ = norm_errors(seg)
    if any(v < PASS_LINE for v in (s[d] for d in DIMS)):
        return False, ""
    if any(e["severity"] in ("critical", "major") for e in errors):
        return False, ""
    return True, ""


def load_json(path, what):
    try:
        return json.load(open(path, encoding="utf-8-sig"))
    except FileNotFoundError:
        raise SystemExit(f"[输入错误] {what} 不存在：{path}")
    except (json.JSONDecodeError, UnicodeDecodeError) as ex:
        raise SystemExit(f"[输入错误] {what} 不是合法 JSON：{path}（{ex}）")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("review", nargs="?", help="评审 JSON")
    ap.add_argument("--rubric", default="", help="rubric 文件（必填，hash 附进报告）")
    ap.add_argument("--cert", default="", help="评审上岗证书（calibrate.py 产出）")
    ap.add_argument("--sample", default="", help="抽样清单（只判抽样段，并校验覆盖）")
    ap.add_argument("--docx", default="", help="交付英文 docx（算 sha256+实算词数，绑定判定）")
    ap.add_argument("--doc-words", type=int, default=0, help="全稿词数（有 --docx 时作交叉校验）")
    ap.add_argument("--diff", default="", help="增量改动段 idx 清单（每行一个，必须全部覆盖评审）")
    ap.add_argument("--out", default="")
    ap.add_argument("--hash", dest="hash_only", default="", help="只输出文件的 sha256 指纹")
    a = ap.parse_args()

    if a.hash_only:
        print(rubric_hash(a.hash_only))
        return 0
    if not a.review:
        ap.error("需要 review.json 或 --hash")
    if not a.rubric:
        ap.error("--rubric 必填：无 rubric 指纹的判定不得入台账（对抗审查 R0-6）")
    if a.sample and not (a.docx or a.doc_words):
        ap.error("抽检模式必须给 --docx 或 --doc-words（抽样段词数不是全稿密度口径）")
    if a.docx and a.doc_words:
        pass  # 两者都给：下面做偏差校验

    data = load_json(a.review, "评审 JSON")
    rh = rubric_hash(a.rubric)
    reviewer = data.get("reviewer", "")
    fail_reasons = []

    # --- 证书链校验（R0-5）---
    cert_info = None
    if a.cert:
        cert = load_json(a.cert, "上岗证书")
        if cert.get("verdict") != "PASS":
            raise SystemExit(f"[输入错误] 证书不是 PASS（评审者未上岗）：{a.cert}")
        if cert.get("rubric_hash") != rh:
            raise SystemExit(f"[输入错误] 证书 rubric_hash 与当前 rubric 不符——rubric 已改版，须重校准")
        if reviewer and cert.get("reviewer") != reviewer:
            raise SystemExit(f"[输入错误] 证书属于 {cert.get('reviewer')}，评审 JSON 署名 {reviewer}")
        cert_info = {k: cert.get(k) for k in ("reviewer", "rubric_hash", "date", "demo")}
    else:
        fail_reasons.append("未提供上岗证书（--cert）——本判定不可用于签发")

    # --- 覆盖校验（R0-1/R0-3）---
    segs = data.get("segments", [])
    if not segs:
        raise SystemExit("[输入错误] 评审 JSON 无 segments——空判定无效，拒绝出分")
    by_idx = {s.get("idx"): s for s in segs}
    sample_info = None
    if a.sample:
        sm = load_json(a.sample, "抽样清单")
        req = [x["idx"] for x in sm["segments"]]
        missing = [i for i in req if i not in by_idx]
        sample_info = {"requested": len(req), "matched": len(req) - len(missing),
                       "seed": sm.get("seed"), "rate": sm.get("rate"),
                       "total_universe": sm.get("total_universe")}
        if missing:
            sample_info["missing_idx"] = missing[:30]
            if len(missing) > len(req) * 0.05:
                fail_reasons.append(f"抽样覆盖不足：缺 {len(missing)}/{len(req)} 段")
        segs = [by_idx[i] for i in req if i in by_idx]
    if a.diff:
        want = [int(x) for x in open(a.diff, encoding="utf-8-sig").read().split() if x.strip()]
        miss = [i for i in want if i not in by_idx]
        if miss:
            fail_reasons.append(f"增量改动段未全审：缺 {len(miss)} 段（如 {miss[:10]}）")

    # --- 词数口径（R0-2）---
    doc_sha = ""
    words = a.doc_words
    if a.docx:
        try:
            doc_sha, real_words = docx_info(a.docx)
        except (zipfile.BadZipFile, KeyError, ET.ParseError):
            raise SystemExit(f"[输入错误] --docx 不是有效 docx：{a.docx}")
        if words and abs(words - real_words) / real_words > 0.20:
            raise SystemExit(f"[输入错误] --doc-words={words} 与 docx 实算 {real_words} 偏差>20%——拒绝出分")
        words = real_words
    if not words:
        words = sum(len(str(s.get("en", "")).split()) for s in segs)
        if a.sample:
            fail_reasons.append("词数按抽样段估算（非全稿口径），本判定仅供参考")

    # --- 段级统计 ---
    n = len(segs)
    passed = malformed = unknown_sev = 0
    malformed_list = []
    crit = major = minor = 0
    crit_detail, major_detail = [], []
    for s in segs:
        ok, why = check_seg(s)
        if why:
            malformed += 1
            malformed_list.append({"idx": s.get("idx"), "reason": why})
        errors, unk = norm_errors(s)
        unknown_sev += unk
        for e in errors:
            sev = e["severity"]
            if sev == "critical":
                crit += 1
                crit_detail.append(e)
            elif sev == "major":
                major += 1
                major_detail.append(e)
            else:
                minor += 1
        if ok:
            passed += 1
    if malformed:
        fail_reasons.append(f"畸形段 {malformed} 个（缺维度/非法分值，已按不通过处理）")
    if unknown_sev:
        fail_reasons.append(f"未知 severity {unknown_sev} 个，已从严计 major")

    density = major * 1000.0 / max(1, words)
    if crit == 0 and density <= DENSITY_MAX and not fail_reasons:
        verdict = "PASS"
    else:
        verdict = "FAIL"
        if crit:
            fail_reasons.append(f"critical {crit} 处（一票否决）")
        if density > DENSITY_MAX:
            fail_reasons.append(f"major 密度 {density:.2f}/千词 > {DENSITY_MAX}")

    dims = {}
    for d in DIMS:
        vals = [s.get("scores", {}).get(d) for s in segs if isinstance(s.get("scores", {}).get(d), int)]
        dims[d] = {"min": min(vals) if vals else None,
                   "avg": round(sum(vals) / len(vals), 2) if vals else None}

    report = {"verdict": verdict, "fail_reasons": fail_reasons,
              "sampled": n, "seg_passed": passed,
              "seg_pass_rate": round(passed / max(1, n), 4),
              "critical": crit, "major": major, "minor": minor,
              "words_basis": words, "major_per_1000": round(density, 3),
              "threshold": {"critical": 0, "major_per_1000_max": DENSITY_MAX},
              "dim_stats": dims,
              "malformed_segments": malformed_list[:20],
              "critical_detail": crit_detail[:20], "major_detail": major_detail[:20],
              "sample_coverage": sample_info,
              "doc_sha256": doc_sha,
              "reviewer": reviewer, "cert": cert_info,
              "rubric_version": data.get("rubric_version", "?"),
              "rubric_hash": rh}

    body = json.dumps(report, ensure_ascii=False, indent=1)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(body)
        print(f"判定 {verdict} | 抽样 {n} 段通过 {passed} | critical {crit} | "
              f"major {major} ({density:.2f}/千词) | doc {doc_sha or 'N/A'} -> {a.out}")
    else:
        print(body)
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
