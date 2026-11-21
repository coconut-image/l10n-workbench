# -*- coding: utf-8 -*-
"""分层抽样：从译元清单 TSV 生成抽检段清单（章节 × 段落类型分层，结论区加权）。

用法：
  python sample_picker.py wk/units.tsv [--rate 0.10] [--min 30] [--seed 42] [--out wk/sample.json]

TSV 格式（extract_units.py 产出，三列）：索引\\t属性\\t中文原文
分层键：章节（最近编号标题，标题=编号开头+短+无句读标点）× 段落类型。
段落类型：TSV 属性列的「表格单元/题注」直接成层（对抗审查 R0-8：不再丢弃）；
属性「译元」内部按文本启发式分 短标签/正文；TOC/域/图/空/纯拉丁 跳过；未知属性值警告并跳过。
配额：ceil(层数 × rate × 权重)，每章节正文 >=2；不足 --min 按层规模比例补齐（不抽干单一层）；
总量仍不足时告警并以 2 退出（fail-closed）。--min 超全集时告警退出。
"""
import sys, json, re, math, random, argparse

sys.stdout.reconfigure(encoding="utf-8")
HEAD = re.compile(r"^\d+(?:\.\d+)*[　\s]")
CONCL = re.compile(r"結論|总结|總結|结论|建議|建议|摘要|summary|conclusion|recommendation", re.I)
SKIP_ATTR = {"TOC", "域", "图", "空", "纯拉丁"}
KNOWN_ATTR = {"译元", "表格单元", "题注"}


def load_units(path, warnings):
    rows = []
    try:
        lines = open(path, encoding="utf-8-sig").read().splitlines()
    except FileNotFoundError:
        raise SystemExit(f"[输入错误] TSV 不存在：{path}")
    for ln in lines:
        parts = ln.split("\t", 2)
        if len(parts) != 3:
            continue
        attr = parts[1]
        if attr in SKIP_ATTR:
            continue
        if attr not in KNOWN_ATTR:
            warnings.append(f"未知属性值「{attr}」（第 {parts[0]} 行）已跳过——分层口径与 extract_units 约定不符")
            continue
        rows.append({"idx": int(parts[0]), "attr": attr, "zh": parts[2]})
    return rows


def stratify(rows):
    out, section = [], "（文首）"
    for r in rows:
        zh = r["zh"].strip()
        # 标题判定：编号开头 + 短 + 无句读标点（防「3 個斷點已復核。」被当章节）
        if HEAD.match(zh) and len(zh) <= 40 and not re.search(r"[。；：，、]", zh):
            section = zh
        if r["attr"] == "表格单元":
            typ = "表格单元"
        elif r["attr"] == "题注":
            typ = "题注"
        else:
            typ = "短标签" if (len(zh) <= 60 and not re.search(r"[。；]", zh)) else "正文"
        weight = 2.0 if CONCL.search(section) else 1.0
        out.append((section, typ, weight, r))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tsv")
    ap.add_argument("--rate", type=float, default=0.10)
    ap.add_argument("--min", dest="min_n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    warnings = []
    rows = load_units(a.tsv, warnings)
    if not rows:
        raise SystemExit("[输入错误] TSV 无有效译元行")
    for w in warnings:
        print(f"[警告] {w}")

    rng = random.Random(a.seed)
    items = stratify(rows)
    layers = {}
    for section, typ, w, r in items:
        layers.setdefault((section, typ, w), []).append(r)

    if a.min_n > len(rows):
        print(f"[警告] --min {a.min_n} 超全集 {len(rows)} 段——请核对抽样方案")
        return 2

    quota = {k: max(math.ceil(len(v) * a.rate * k[2]),
                    2 if k[1] == "正文" else 0) for k, v in layers.items()}
    quota = {k: min(q, len(v)) for k, q, v in ((k, quota[k], layers[k]) for k in layers)}

    # 不足下限：按层规模比例补齐（每层留 room，不抽干单层）
    def total():
        return sum(quota.values())
    if total() < a.min_n:
        attainable = sum(len(v) for v in layers.values())
        if attainable < a.min_n:
            print(f"[警告] 全集 {attainable} 段不足以达到下限 {a.min_n}")
        sizes = {k: len(v) for k, v in layers.items()}
        size_sum = sum(sizes.values())
        for k in sorted(layers, key=lambda x: -sizes[x]):
            if total() >= a.min_n:
                break
            room = max(0, sizes[k] - quota[k])
            share = math.ceil((a.min_n - total()) * sizes[k] / size_sum)
            quota[k] += min(room, max(share, 1))
    if total() < a.min_n:
        print(f"[警告] 容量不足：实抽 {total()} < 下限 {a.min_n}（各层已饱和）")

    sample = []
    for k, v in sorted(layers.items()):
        for r in rng.sample(v, min(quota[k], len(v))):
            sample.append({"idx": r["idx"], "section": k[0], "type": k[1], "weight": k[2]})
    sample.sort(key=lambda x: x["idx"])

    result = {"total_universe": len(rows), "total_sample": len(sample),
              "rate": a.rate, "min": a.min_n, "seed": a.seed,
              "warnings": warnings,
              "layers": {f"{k[0]}|{k[1]}": {"size": len(v), "quota": quota[k]}
                         for k, v in sorted(layers.items())},
              "segments": sample}
    body = json.dumps(result, ensure_ascii=False, indent=1)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(body)
        print(f"抽样 {len(sample)}/{len(rows)} 段 -> {a.out}")
    else:
        print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
