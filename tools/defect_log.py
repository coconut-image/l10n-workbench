# -*- coding: utf-8 -*-
"""缺陷密度台账：逐稿记录抽检判定结果，攒趋势——「基本无错」要靠统计站得住。

用法：
  python defect_log.py add --doc report_EN_v2 --verdict wk/verdict.json [--notes "..."] [--db wk/defect_log.db]
  python defect_log.py quality --doc report_EN_v2 --reviewed 8 --agree 7 [--db wk/defect_log.db]   # 交互点 4 理由抽核
  python defect_log.py trend [--db wk/defect_log.db] [--check-rubric assets/rubric-v1.md]

quality 子命令是交互点 4（评审理由抽核）的落点；同稿重复抽检 seed 拒绝入库（防 seed 狩猎）；
--check-rubric 比对当前 rubric 文件 hash 与台账最早记录，防出分后改 rubric 不改版。
"""
import sys, os, json, sqlite3, argparse, datetime, hashlib

sys.stdout.reconfigure(encoding="utf-8")
DDL = """CREATE TABLE IF NOT EXISTS records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT, doc TEXT, sampled INTEGER, seg_passed INTEGER,
  critical INTEGER, major INTEGER, minor INTEGER, words INTEGER,
  density REAL, verdict TEXT, rubric_hash TEXT, seed INTEGER,
  doc_sha256 TEXT, notes TEXT)"""
QA_DDL = """CREATE TABLE IF NOT EXISTS review_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT, doc TEXT, reviewed INTEGER, agree INTEGER, rate REAL)"""
REQUIRED = ("sampled", "seg_passed", "critical", "major", "minor",
            "words_basis", "major_per_1000", "verdict", "rubric_hash")


def db(path):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(DDL)
    conn.execute(QA_DDL)
    try:
        conn.execute("ALTER TABLE records ADD COLUMN seed INTEGER")       # 旧库迁移
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE records ADD COLUMN doc_sha256 TEXT")
    except sqlite3.OperationalError:
        pass
    return conn


def load_verdict(path):
    try:
        v = json.load(open(path, encoding="utf-8-sig"))
    except FileNotFoundError:
        raise SystemExit(f"[输入错误] verdict 文件不存在：{path}")
    except (json.JSONDecodeError, UnicodeDecodeError) as ex:
        raise SystemExit(f"[输入错误] verdict 不是合法 JSON：{path}（{ex}）")
    missing = [k for k in REQUIRED if k not in v]
    if missing:
        raise SystemExit(f"[输入错误] verdict JSON 缺少 {missing}——请用 tools/verdict.py 的新版产出"
                         f"（旧版产物无 hash/seed 字段，不入台账）")
    return v


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    a1 = sub.add_parser("add", help="记录一稿判定")
    a1.add_argument("--doc", required=True)
    a1.add_argument("--verdict", required=True)
    a1.add_argument("--notes", default="")
    a1.add_argument("--db", default="wk/defect_log.db")

    a2 = sub.add_parser("quality", help="记录交互点 4 评审理由抽核结果")
    a2.add_argument("--doc", required=True)
    a2.add_argument("--reviewed", type=int, required=True)
    a2.add_argument("--agree", type=int, required=True)
    a2.add_argument("--db", default="wk/defect_log.db")

    a3 = sub.add_parser("trend", help="查历史趋势")
    a3.add_argument("--db", default="wk/defect_log.db")
    a3.add_argument("--check-rubric", dest="check_rubric", default="",
                    help="比对当前 rubric 文件与台账最早 hash")

    a = ap.parse_args()
    if a.cmd == "add":
        v = load_verdict(a.verdict)
        seed = (v.get("sample_coverage") or {}).get("seed")
        conn = db(a.db)
        if seed is not None:
            dup = conn.execute("SELECT COUNT(*) FROM records WHERE doc=? AND seed=?",
                               (a.doc, seed)).fetchone()[0]
            if dup:
                conn.close()
                raise SystemExit(f"[拒绝] {a.doc} 已有 seed={seed} 的记录——同稿重抽请说明原因并人工处理"
                                 f"（防 seed 狩猎）")
        conn.execute("INSERT INTO records VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (datetime.date.today().isoformat(), a.doc, v["sampled"], v["seg_passed"],
                      v["critical"], v["major"], v["minor"], v["words_basis"],
                      v["major_per_1000"], v["verdict"], v.get("rubric_hash", ""), seed,
                      v.get("doc_sha256", ""), a.notes))
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        conn.close()
        print(f"已记录 {a.doc}（verdict={v['verdict']}），台账累计 {n} 稿")
    elif a.cmd == "quality":
        rate = a.agree / max(1, a.reviewed)
        conn = db(a.db)
        conn.execute("INSERT INTO review_audit VALUES (NULL,?,?,?,?,?)",
                     (datetime.date.today().isoformat(), a.doc, a.reviewed, a.agree, round(rate, 4)))
        conn.commit()
        conn.close()
        flag = "（<70%，评审应降级重校准）" if rate < 0.70 else ""
        print(f"抽核记录：{a.agree}/{a.reviewed} = {rate:.0%} {flag}")
    else:
        if not os.path.exists(a.db):
            print("（台账为空）")
            return 0
        conn = db(a.db)
        if a.check_rubric:
            cur = hashlib.sha256(open(a.check_rubric, "rb").read()).hexdigest()[:16]
            first = conn.execute("SELECT rubric_hash FROM records ORDER BY id LIMIT 1").fetchone()
            if first and first[0] and first[0] != cur:
                print(f"[警告] 当前 rubric hash {cur} != 台账最早记录 {first[0]}——"
                      f"rubric 已变更未走 vN 改版流程，趋势口径已破坏")
        rows = conn.execute("SELECT date,doc,sampled,critical,major,density,verdict FROM records "
                            "ORDER BY date,id").fetchall()
        qas = conn.execute("SELECT date,doc,reviewed,agree,rate FROM review_audit "
                           "ORDER BY date,id").fetchall()
        conn.close()
        if not rows:
            print("（台账为空）")
            return 0
        print(f"{'date':<12}{'doc':<28}{'抽样':>5}{'crit':>5}{'major':>6}{'密度':>8}  verdict")
        for r in rows:
            print(f"{r[0]:<12}{r[1]:<28}{r[2]:>5}{r[3]:>5}{r[4]:>6}{r[5]:>8.2f}  {r[6]}")
        if qas:
            print("\n评审理由抽核（交互点 4）：")
            for q in qas:
                print(f"  {q[0]}  {q[1]:<24} {q[3]}/{q[2]} = {q[4]:.0%}"
                      + ("  → 降级重校准" if q[4] < 0.70 else ""))
        fails = sum(1 for r in rows if r[6] != "PASS")
        print(f"\n累计 {len(rows)} 稿，FAIL {fails} 稿"
              + ("——趋势稳定" if fails == 0 else "——FAIL 稿的错误模式应回流资产（l10n-sediment 交互点 6）"))


if __name__ == "__main__":
    main()
