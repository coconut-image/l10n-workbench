# -*- coding: utf-8 -*-
"""裁决→资产回填：把人工裁决结果回填术语表（provisional）与风格文件。

用法（默认 dry-run 只打印预览，--confirm 才写盘——交互点 6 确认后执行）：
  python glossary_backfill.py wk/decisions.json --glossary wk/glossary --style wk/style.md [--confirm]
  python glossary_backfill.py --promote --term 漏損定位 --glossary wk/glossary [--confirm]

decision 条目必须含 kind 字段（对抗审查 P0-3 修复：缺 kind 报错退出，不静默丢弃）：
  {"kind": "term"|"style"|"table_usage", "term_zh":…, "chosen":…, "reason":…, "date":…}
重复条目（term_zh+chosen 已在表中）自动跳过；路径校验前置，杜绝半写盘。
"""
import sys, os, json, re, argparse

sys.stdout.reconfigure(encoding="utf-8")
KINDS = {"term", "style", "table_usage"}


def load_decisions(path):
    try:
        ds = json.load(open(path, encoding="utf-8-sig"))
    except FileNotFoundError:
        raise SystemExit(f"[输入错误] decisions 文件不存在：{path}")
    except (json.JSONDecodeError, UnicodeDecodeError) as ex:
        raise SystemExit(f"[输入错误] decisions 不是合法 JSON：{path}（{ex}）")
    if isinstance(ds, dict):
        ds = ds.get("decisions", [])
    bad = []
    for i, d in enumerate(ds):
        k = d.get("kind")
        if k not in KINDS:
            bad.append(f"第 {i + 1} 条 kind={k!r}（合法值：{'/'.join(sorted(KINDS))}）")
        elif k in ("term", "table_usage") and not d.get("term_zh"):
            bad.append(f"第 {i + 1} 条 kind={k} 缺 term_zh")
    if bad:
        raise SystemExit("[输入错误] 裁决条目不合规，全部拒写：\n  " + "\n  ".join(bad))
    return ds


def existing_terms(path):
    """已存在的 (zh, en) 集合，用于去重。"""
    out = set()
    if os.path.exists(path):
        for ln in open(path, encoding="utf-8"):
            if ln.strip().startswith("|"):
                cells = [c.strip() for c in ln.strip().strip("|").split("|")]
                if len(cells) >= 2:
                    out.add((cells[0], cells[1]))
    return out


def backfill(dec_path, glossary, style, confirm):
    ds = load_decisions(dec_path)

    # 路径校验前置（防半写盘）
    os.makedirs(glossary, exist_ok=True)
    style_dir = os.path.dirname(style) or "."
    os.makedirs(style_dir, exist_ok=True)
    glossary_file = os.path.join(glossary, "20_项目_裁决沉淀.md")

    term_lines, style_lines, preview, skipped = [], [], [], []
    seen = existing_terms(glossary_file)
    for d in ds:
        if d["kind"] == "term":
            if (d.get("term_zh"), d.get("chosen")) in seen:
                skipped.append(f"术语跳过（已在表）：{d['term_zh']} -> {d['chosen']}")
                continue
            term_lines.append(f"| {d.get('term_zh','')} | {d['chosen']} | P | provisional "
                              f"| {d.get('date','')} 裁决：{d.get('reason','')[:40]} |")
            preview.append(f"术语 +: {d.get('term_zh')} -> {d['chosen']}（provisional）")
            seen.add((d.get("term_zh"), d.get("chosen")))
        elif d["kind"] == "style":
            line = f"- {d['chosen']}（{d.get('date','')} 裁决：{d.get('reason','')[:40]}）"
            if os.path.exists(style) and line in open(style, encoding="utf-8").read():
                skipped.append(f"风格跳过（已在文件）：{d['chosen']}")
                continue
            style_lines.append(line)
            preview.append(f"风格 +: {d['chosen']}")
        elif d["kind"] == "table_usage":
            preview.append(f"表格用法（人工改表）: {d.get('term_zh')} -> {d['chosen']}")
    print("\n".join(preview) or "（无条目）")
    for s in skipped:
        print(f"[去重] {s}")

    if not confirm:
        print("\n[dry-run] 未写盘。确认无误后加 --confirm 执行。")
        return
    if term_lines:
        if not os.path.exists(glossary_file) or os.path.getsize(glossary_file) == 0:
            with open(glossary_file, "w", encoding="utf-8") as f:
                f.write("# 项目层裁决沉淀（本文件由 glossary_backfill 维护）\n\n"
                        "| 中文 | 英文 | 依据 | 状态 | 备注 |\n|---|---|---|---|---|\n")
        with open(glossary_file, "a", encoding="utf-8") as f:
            f.write("\n".join(term_lines) + "\n")
        print(f"术语 {len(term_lines)} 条 -> {glossary_file}")
    if style_lines:
        if not os.path.exists(style):
            with open(style, "w", encoding="utf-8") as f:
                f.write("# 风格记忆（软约束，随任务书下发）\n\n")
        with open(style, "a", encoding="utf-8") as f:
            f.write("\n".join(style_lines) + "\n")
        print(f"风格 {len(style_lines)} 条 -> {style}")


def promote(glossary, term, confirm):
    # 锚定第 4 列（状态列）整格等于 provisional，防误改备注列
    pat = re.compile(r"^(\|\s*" + re.escape(term) + r"\s*\|[^|\n]*\|[^|\n]*\|)\s*provisional\s*(\|)",
                     re.MULTILINE)
    hits = 0
    for fn in sorted(os.listdir(glossary)) if os.path.isdir(glossary) else []:
        if not fn.endswith(".md"):
            continue
        p = os.path.join(glossary, fn)
        text = open(p, encoding="utf-8").read()
        new, n = pat.subn(r"\1 正式 \2", text)
        if n:
            hits += n
            print(f"[预览] {fn}: 「{term}」状态列 provisional -> 正式（×{n}）")
            if confirm:
                open(p, "w", encoding="utf-8").write(new)
    if not confirm:
        print("[dry-run] 未写盘。确认后加 --confirm 执行。")
    elif hits:
        print(f"已升格 {hits} 条")
    else:
        print(f"（{glossary} 中无「{term}」状态列为 provisional 的条目）")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("decisions", nargs="?", help="decisions.json")
    ap.add_argument("--glossary", required=True)
    ap.add_argument("--style", default="wk/style.md")
    ap.add_argument("--promote", action="store_true", help="升格模式")
    ap.add_argument("--term", default="", help="升格的术语（--promote 时必填）")
    ap.add_argument("--confirm", action="store_true", help="实际写盘（默认 dry-run）")
    a = ap.parse_args()
    if a.promote:
        if not a.term:
            ap.error("--promote 需要 --term")
        promote(a.glossary, a.term, a.confirm)
    else:
        if not a.decisions:
            ap.error("需要 decisions.json 或 --promote")
        backfill(a.decisions, a.glossary, a.style, a.confirm)


if __name__ == "__main__":
    main()
