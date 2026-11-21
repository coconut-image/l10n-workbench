#!/usr/bin/env bash
# 端到端演练：freq_scan → 校准（好/坏评审，含证书链）→ 抽样 → 判定（FAIL/PASS + 攻击演示）→ 台账 → 回填
# 可重复执行（每次清空 e2e_out）。全部使用合成样例，无客户数据。
# 演练口径说明：锚点集为 8 段缩减演示集，正式校准须 20-30 段（--min-anchors 8 显式声明，证书标 demo）。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLS="$ROOT/tools"; S="$ROOT/samples"; OUT="$S/e2e_out"; WK="$OUT/wk"
RUBRIC="$ROOT/assets/rubric-v1.md"
rm -rf "$OUT"; mkdir -p "$WK/glossary"

echo "===[0/7] 造 mini 中文 docx（freq_scan 用）==="
python3 - <<PY
import zipfile, os
paras = (["本區漏損情況嚴重，漏損率持續偏高。"] * 6
         + ["壓力測點數據整體完整，壓力測點覆蓋全區。"] * 6
         + ["夜間最小流量法是主要手段。"] * 5)
body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paras)
xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
       f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
       f'<w:body>{body}</w:body></w:document>')
os.makedirs("$OUT", exist_ok=True)
with zipfile.ZipFile("$OUT/mini_zh.docx", "w") as z:
    z.writestr("word/document.xml", xml)
print("mini_zh.docx：漏損×6（已收录）、壓力測點×6（未收录）、夜間最小流量×5（未收录）")
PY

echo; echo "===[1/7] freq_scan 高频词扫描（术语表只收「漏損」）==="
printf '# 10_行业\n\n| 中文 | 英文 | 依据 |\n|---|---|---|\n| 漏損 | leakage | S |\n' > "$WK/glossary/10_行业.md"
python3 "$TOOLS/freq_scan.py" "$OUT/mini_zh.docx" --glossary "$WK/glossary" --min 5 --out "$OUT/freq_scan.md"
echo "（期望：壓力測點、夜間最小流量级别候选；不应出现 漏損 与 滑窗碎片）"

echo; echo "===[2/7] 校准门（8 段缩减演示集，--min-anchors 8 → 证书标 demo）==="
if python3 "$TOOLS/calibrate.py" "$S/anchor-set.json" "$S/review_anchor_good.json" \
      --rubric "$RUBRIC" --cert-out "$WK/cert_reviewer-A.json" \
      --min-anchors 8 --out "$OUT/calib_good.json"; then
  echo "[互锁] reviewer-A 上岗 PASS，证书已产出 -> $WK/cert_reviewer-A.json"
else
  echo "!! 好评审应 PASS，却 FAIL——演练失败"; exit 1
fi
if python3 "$TOOLS/calibrate.py" "$S/anchor-set.json" "$S/review_anchor_bad.json" \
      --rubric "$RUBRIC" --min-anchors 8 --out "$OUT/calib_bad.json"; then
  echo "!! 坏评审应被拦，却 PASS——演练失败"; exit 1
else
  echo "[互锁] reviewer-B 被拦 FAIL——其评审不得被采信（纪律 2）"
fi

echo; echo "===[3/7] 分层抽样 =="
python3 "$TOOLS/sample_picker.py" "$S/sample_units.tsv" --out "$WK/sample.json"

echo; echo "===[4/7] 判定（fail-closed 演示：v1 含 critical 应 FAIL 且拦签发）==="
python3 "$TOOLS/verdict.py" "$S/review_full_critical.json" --rubric "$RUBRIC" \
  --cert "$WK/cert_reviewer-A.json" --doc-words 2000 --out "$WK/verdict_v1.json" \
  && { echo "!! v1 应 FAIL——演练失败"; exit 1; } \
  || echo "[签发拦截] v1 FAIL（critical 一票否决），不得签发（纪律 3）"

echo; echo "===[4b/7] 攻击演示：空评审 / 坏证书 必须被拒 =="
if echo '{"segments": []}' > "$OUT/empty_review.json" \
  && python3 "$TOOLS/verdict.py" "$OUT/empty_review.json" --rubric "$RUBRIC" \
       --cert "$WK/cert_reviewer-A.json" --doc-words 2000 2>"$OUT/attack_empty.log"; then
  echo "!! 空评审应被拒绝——fail-closed 失效"; exit 1
else
  echo "[fail-closed] 空评审被拒（exit != 0）：$(tail -1 "$OUT/attack_empty.log")"
fi
if python3 "$TOOLS/verdict.py" "$S/review_full_clean.json" --rubric "$RUBRIC" \
     --cert "$OUT/calib_bad.json" --doc-words 2000 2>"$OUT/attack_cert.log"; then
  echo "!! FAIL 的校准报告不该当证书用——证书链失效"; exit 1
else
  echo "[证书链] 非 PASS 证书被拒：$(tail -1 "$OUT/attack_cert.log")"
fi

echo; echo "===[5/7] 判定（返工后 v2 应 PASS，带证书与 rubric hash）==="
if python3 "$TOOLS/verdict.py" "$S/review_full_clean.json" --rubric "$RUBRIC" \
  --cert "$WK/cert_reviewer-A.json" --doc-words 2000 --out "$WK/verdict_v2.json"; then
  echo "[可签发] v2 PASS：判定报告含 rubric_hash + reviewer + cert"
else
  echo "!! v2 应 PASS——演练失败"; exit 1
fi

echo; echo "===[6/7] 缺陷台账 + 理由抽核（交互点 4 落点）==="
python3 "$TOOLS/defect_log.py" add --doc sample_report_EN_v1 --verdict "$WK/verdict_v1.json" --db "$WK/defect_log.db" --notes "演练稿：含预埋 critical"
python3 "$TOOLS/defect_log.py" add --doc sample_report_EN_v2 --verdict "$WK/verdict_v2.json" --db "$WK/defect_log.db" --notes "演练稿：返工后 PASS"
python3 "$TOOLS/defect_log.py" quality --doc sample_report_EN_v2 --reviewed 6 --agree 6 --db "$WK/defect_log.db"
python3 "$TOOLS/defect_log.py" trend --db "$WK/defect_log.db" --check-rubric "$RUBRIC"

echo; echo "===[7/7] 裁决回填（dry-run 预览 → confirm 落盘）==="
python3 "$TOOLS/glossary_backfill.py" "$S/decisions.json" --glossary "$WK/glossary" --style "$WK/style.md"
echo "--- 交互点 6：人确认后 ---"
python3 "$TOOLS/glossary_backfill.py" "$S/decisions.json" --glossary "$WK/glossary" --style "$WK/style.md" --confirm
echo "--- 重跑去重演示（同 decisions 再 confirm 应跳过不双写）---"
python3 "$TOOLS/glossary_backfill.py" "$S/decisions.json" --glossary "$WK/glossary" --style "$WK/style.md" --confirm
echo; echo "回填产物："; cat "$WK/glossary/20_项目_裁决沉淀.md" 2>/dev/null

echo; echo "=== e2e 演练完成（含 fail-closed 攻击演示），全部产物在 $OUT ==="
