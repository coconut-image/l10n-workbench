# -*- coding: utf-8 -*-
"""高频词扫描：找「出现 >= N 次、术语表未收录」的中文候选词，供建表补缺口。

用法：
  python freq_scan.py <中文.docx> --glossary wk/glossary [--min 5] [--out 候选.md]

逻辑（对抗审查修复版：逐轮掩码重计，替代滑窗+贪心去重）：
抽取全文含中文段落 -> 现有术语表最长匹配剔除 -> 逐轮：在剩余文本里枚举 2-6 字
候选按（频次降序、长度降序）选 top -> 挖空该词全部出现 -> 重计，直至无候选 >= min。
覆盖达标 = 输出为空（操作定义见 l10n-glossary：min=5 下候选为空 + 人工抽核低频专业词）。
"""
import sys, os, re, zipfile, argparse
from collections import Counter
from xml.etree import ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CJK = re.compile(r"[一-鿿]")
# 首尾出现即弃的虚词（简繁并收）；双端同时为虚词也弃
EDGE_STOP = set("的與及為在对使被将其這这个于由从或而並并且之了是對於從並著")
MID_STOP = set("的了是")


def para_texts(path):
    try:
        with zipfile.ZipFile(path) as z:
            root = ET.fromstring(z.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        raise SystemExit(f"[输入错误] 不是有效 docx：{path}")
    out = []
    for p in root.find(W + "body").iter(W + "p"):   # 注：表格内段落计入（表格标签复现率高，口径在输出注明）
        st = p.find(W + "pPr/" + W + "pStyle")
        if st is not None and re.match(r"TOC\d", (st.get(W + "val") or "").upper()):
            continue
        t = "".join(x.text or "" for x in p.iter(W + "t"))
        if CJK.search(t):
            out.append(t)
    return out


def load_terms(gdir):
    terms = set()
    if not os.path.isdir(gdir):
        return terms
    for fn in sorted(os.listdir(gdir)):
        if not fn.endswith(".md"):
            continue
        for ln in open(os.path.join(gdir, fn), encoding="utf-8"):
            if not ln.strip().startswith("|"):
                continue
            cells = [c.strip("*` ") for c in ln.strip().strip("|").split("|")]
            # 表头/纯中文行过滤：英文列必须含字母（防「中文/英文」表头泄漏为术语）
            if len(cells) >= 2 and CJK.search(cells[0]) and re.search(r"[A-Za-z]", cells[1]):
                terms.add(cells[0])
    return terms


def is_junk(w):
    if w[0] in EDGE_STOP or w[-1] in EDGE_STOP:
        return True
    if w[0] in MID_STOP and w[-1] in MID_STOP:
        return True
    return any(c in MID_STOP for c in w[1:-1])   # 内部含 的/了/是 的必是句碎片（「法是主要手段」类）


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("docx")
    ap.add_argument("--glossary", required=True, help="术语表目录")
    ap.add_argument("--min", type=int, default=5, help="最低出现次数（默认 5；正式覆盖判定请勿调高）")
    ap.add_argument("--out", default="", help="输出 md 文件（默认打印到终端）")
    a = ap.parse_args()

    terms = load_terms(a.glossary)
    matcher = re.compile("|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))) if terms else None

    corpus = []
    for text in para_texts(a.docx):
        if matcher:
            text = matcher.sub("\x00", text)          # 已收录术语挖空
        corpus.extend(re.findall(r"[一-鿿]{2,}", text))
    text_all = "\x00".join(corpus)                     # 连续汉字串以非 CJK 分隔

    picked = []
    while True:
        cnt = Counter()
        for run in text_all.split("\x00"):
            for n in range(2, min(7, len(run) + 1)):
                for i in range(len(run) - n + 1):
                    cnt[run[i:i + n]] += 1
        cands = [(w, c) for w, c in cnt.items() if c >= a.min and w not in terms]
        if not cands:
            break
        cands.sort(key=lambda x: (-x[1], -len(x[0]), x[0]))   # 频次降序→长度降序→字典序（确定性）
        top, freq = cands[0]
        if is_junk(top):
            terms.add(top)                              # 虚词碎片也挖空，防死循环
            text_all = text_all.replace(top, "\x00")
            continue
        picked.append((top, freq))
        text_all = text_all.replace(top, "\x00")        # 挖空全部出现后重计

    lines = [f"# 高频词候选（>= {a.min} 次，术语表未收录）", "",
             f"源：{a.docx}；已剔除术语表条目 {len(terms)} 个（含本轮挖空的虚词碎片）；候选 {len(picked)} 个",
             "口径：表格内段落计入频次；标题段落计入", ""]
    if not picked:
        lines.append("（空——按操作定义达标：请再人工抽核出现 <5 次的专业词）")
    for w, c in picked:
        lines.append(f"| {w} | {c} | 人工定译： |")
    body = "\n".join(lines)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(body + "\n")
        print(f"候选 {len(picked)} 个 -> {a.out}")
    else:
        print(body)


if __name__ == "__main__":
    main()
