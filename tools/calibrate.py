# -*- coding: utf-8 -*-
"""评审校准：计算评审者对锚点集的人工一致率与 critical 召回，判定能否上岗并签发证书。

用法：
  python calibrate.py assets/anchor-set.json wk/review_anchor.json \
                  --rubric assets/rubric-v1.md --cert-out wk/cert_<reviewer>.json \
                  [--min-anchors 20] [--out wk/calib_report.json]

判据（rubric 定版）：段级二分类（过/不过）一致率 >= 80% 且 critical 召回 100%。
fail-closed（对抗审查 R0-4/R0-5 修复）：
- 锚点集规模 >= --min-anchors（默认 20；显式调低时证书标 demo，不得用于正式签发）
- 评审必须覆盖全部锚点段（matched == total_anchors），挑段提交直接 FAIL
- 低分理由绑定：任一维 <=2 的段 errors 必须非空，否则该段作废并告警
- PASS 时产出证书（reviewer + rubric_hash + 锚点集 hash），供 verdict.py --cert 校验
"""
import sys, json, hashlib, argparse, datetime

sys.stdout.reconfigure(encoding="utf-8")
PASS_LINE = 3
BAD = ("critical", "major")
PASS_RATE_MIN = 0.80
DIMS = ("F", "L", "T", "S")


def load_json(path, what):
    try:
        return json.load(open(path, encoding="utf-8-sig"))
    except FileNotFoundError:
        raise SystemExit(f"[输入错误] {what} 不存在：{path}")
    except (json.JSONDecodeError, UnicodeDecodeError) as ex:
        raise SystemExit(f"[输入错误] {what} 不是合法 JSON：{path}（{ex}）")


def norm_sev(errors):
    return [str(e.get("severity", "")).strip().lower() for e in errors]


def seg_pass(scores, errors):
    if any(not isinstance(scores.get(d), int) for d in DIMS):
        return False                                   # 缺维即不通过（fail-closed）
    if any(scores[d] < PASS_LINE for d in DIMS):
        return False
    return not any(s in BAD for s in norm_sev(errors))


def has_low_without_reason(scores, errors):
    """任一维 <=2 且 errors 为空 = 无理由低分，该段作废。"""
    low = any(isinstance(scores.get(d), int) and scores[d] <= 2 for d in DIMS)
    return low and not errors


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("anchors", help="anchor-set.json（人工标注）")
    ap.add_argument("review", help="评审 JSON（模型盲评锚点段）")
    ap.add_argument("--rubric", required=True, help="rubric 文件（hash 进证书）")
    ap.add_argument("--cert-out", default="", help="PASS 时写出的上岗证书 JSON 路径")
    ap.add_argument("--min-anchors", type=int, default=20,
                    help="锚点规模下限（默认 20；显式调低会标 demo）")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    adata = load_json(a.anchors, "锚点集")
    rdata = load_json(a.review, "评审 JSON")
    anchors = {x["idx"]: x for x in adata["anchors"]}
    review = {x["idx"]: x for x in rdata["segments"]}

    if adata.get("rubric_version") != rdata.get("rubric_version"):
        raise SystemExit(f"[输入错误] rubric_version 不一致：锚点集 {adata.get('rubric_version')}"
                         f" vs 评审 {rdata.get('rubric_version')}——跨版本校准无效")

    demo = a.min_anchors < 20
    fail_reasons = []
    if len(anchors) < a.min_anchors:
        fail_reasons.append(f"锚点集仅 {len(anchors)} 段 < 下限 {a.min_anchors}（规范 20-30，好中差三层）")

    matched = agree = 0
    missing = sorted(set(anchors) - set(review))
    if missing:
        fail_reasons.append(f"评审未覆盖全部锚点：缺 {len(missing)} 段 {missing[:10]}——挑段提交无效")
    disagree, voided = [], []
    human_crit = machine_crit_hit = 0
    for idx, h in anchors.items():
        m = review.get(idx)
        if m is None:
            continue
        # 低分理由绑定：双侧任一出现无理由低分，该段作废
        if has_low_without_reason(m.get("scores", {}), m.get("errors", [])) or \
           has_low_without_reason(h.get("human_scores", {}), h.get("human_errors", [])):
            voided.append(idx)
            continue
        matched += 1
        hp = seg_pass(h.get("human_scores", {}), h.get("human_errors", []))
        mp = seg_pass(m.get("scores", {}), m.get("errors", []))
        if hp == mp:
            agree += 1
        else:
            disagree.append({"idx": idx, "human_pass": hp, "machine_pass": mp,
                             "human": h.get("human_scores"), "machine": m.get("scores")})
        if "critical" in norm_sev(h.get("human_errors", [])):
            human_crit += 1
            if "critical" in norm_sev(m.get("errors", [])):
                machine_crit_hit += 1

    if voided:
        fail_reasons.append(f"无理由低分段 {len(voided)} 个已作废（低分必须附 span 级理由）")
    rate = agree / matched if matched else 0.0
    if human_crit:
        recall = machine_crit_hit / human_crit
        recall_ok = recall == 1.0
        recall_txt = f"{recall:.0%}（{machine_crit_hit}/{human_crit}）"
    else:
        recall_ok = False
        recall_txt = "未验证（锚点集缺 critical 样本——按规范至少 2 段）"
        fail_reasons.append("锚点集无 critical 样本，召回门不可判定")

    if not fail_reasons and rate >= PASS_RATE_MIN and recall_ok and matched == len(anchors):
        verdict = "PASS"
    else:
        verdict = "FAIL"
        if rate < PASS_RATE_MIN:
            fail_reasons.append(f"一致率 {rate:.0%} < {PASS_RATE_MIN:.0%}")

    rh = hashlib.sha256(open(a.rubric, "rb").read()).hexdigest()[:16]
    ah = hashlib.sha256(open(a.anchors, "rb").read()).hexdigest()[:16]
    report = {"verdict": verdict, "fail_reasons": fail_reasons,
              "matched": matched, "total_anchors": len(anchors),
              "missing_anchor_idx": missing[:30],
              "agree": agree, "agreement_rate": round(rate, 4),
              "pass_rate_min": PASS_RATE_MIN,
              "critical_recall": recall_txt,
              "voided_no_reason_idx": voided[:20],
              "disagree_segments": [{"idx": d["idx"], "human_pass": d["human_pass"],
                                     "machine_pass": d["machine_pass"]} for d in disagree[:10]],
              "reviewer": rdata.get("reviewer", ""),
              "rubric_version": adata.get("rubric_version", "?"),
              "rubric_hash": rh, "anchors_hash": ah, "demo": demo}

    body = json.dumps(report, ensure_ascii=False, indent=1)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(body)
        print(f"一致率 {rate:.0%} | critical 召回 {recall_txt} | 判定 {verdict}"
              + ("（demo 演练规模）" if demo else "") + f" -> {a.out}")
    else:
        print(body)

    if verdict == "PASS" and a.cert_out:
        cert = {"verdict": "PASS", "reviewer": rdata.get("reviewer", ""),
                "rubric_version": adata.get("rubric_version", "?"),
                "rubric_hash": rh, "anchors_hash": ah,
                "agreement_rate": round(rate, 4), "date": datetime.date.today().isoformat(),
                "demo": demo}
        if demo:
            cert["note"] = "demo 证书：锚点规模低于正式规范，不得用于正式签发"
        json.dump(cert, open(a.cert_out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"上岗证书 -> {a.cert_out}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
