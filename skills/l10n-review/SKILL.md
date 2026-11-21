---
name: l10n-review
description: 表达层评审——独立会话按 rubric 四维（忠实/流畅/术语/风格）逐段给英文译文打分并标注错误严重度，span 级理由绑定；版本对比时用成对判断（A/B 交换位置双判）。对译文质量评分、判断哪版更好、表达层把关时使用。开工前必须已过锚点校准（l10n-calibrate）。
---

# l10n-review · 表达层评审

> **职责**：对英文 docx（或其抽样段/改动段）逐段产出评审 JSON——四维分 + 错误标注 + span 级理由。你是**评审会话**：独立于翻译会话运行（总纲纪律 5），只对质量负责，不负责修改译文。
> **前置互锁**：`assets/` 中存在已签认的 rubric 版本 + 对应校准报告显示评审者「已上岗」。缺任一 → 拒绝开工并提示先走 `l10n-calibrate`（纪律 1、2）。

## 开工 checklist

- [ ] rubric 已签认定版（读到 `rubric-v*.md` 的签认行；hash 在 `assets/rubric-v1.hash`）
- [ ] 上岗证书存在且属于本会话（`wk/cert_<本会话reviewer>.json`，verdict=PASS、rubric-hash 与当前 rubric 一致——`verdict.py --cert` 会物理校验，不符拒出分）
- [ ] 评审对象清单已定：全量段 / 抽样段（`sample_picker.py` 产出）/ 增量改动段（--diff 清单）
- [ ] 中文原文在手（忠实度须对照源文评，**开着中文评**——与润色「合上中文」相反）
- [ ] 评审 JSON 的 `rubric_version` 与锚点集一致（跨版本校准无效）

## 逐段评审纪律

每段按 rubric 四维打 0-4 分，同时标注发现的错误（severity + 类型 + span）：

1. **F 忠实**：对照中文逐句核四类漂移（条件→绝对 / 建议→要求 / 部分→整体 / 可能→确定）、漏译、添译。这一维**最严**：工程报告里漂移比错字严重
2. **L 流畅**：只读英文，读起来是否像人写的；连续十句同构（主句+从句）要标
3. **T 术语**：按表核对（机器审计已做过「按表」），你补查机器查不了的「语境贴切」——flow data 不是 flow rate 这类
4. **S 风格**：语气是否匹配工程报告文体；摘要与正文口吻是否一致（we recommend vs it is recommended）

**理由绑定（硬规则，物理执行）**：任何维 ≤2 分，该段 `errors` 必须非空（引用原文片段 span + 一句话说清问题）——`calibrate.py` 会把无理由低分段**作废**并计 fail_reason，`verdict.py` 对畸形段按不通过处理。空 errors 配低分 = 白打。

**独立判断纪律**：不参考任何「这稿已经过 QC 全绿/已经润色过」的过程信息——过程信息与表达质量无关，先入之见会拉高分数。

## 成对比较模式（版本对比时）

回答「v2 比 v1 好吗」不要打绝对分，用成对判断：

- 对 `incremental` 算出的改动段，逐段判 A/B 哪个更好 + 一句理由
- **交换顺序双判**：先 (A,B) 判一轮，再 (B,A) 判一轮，两次结论不同 → 该段标「分歧」，进人工裁决
- 绝对分只对锚点段打（供校准用）

## 输出 JSON schema（评审产物，供 calibrate/accept 消费）

```json
{"rubric_version": "v1", "reviewer": "<模型/会话标识，须与上岗证书一致>", "doc": "report_EN_v2.docx",
 "segments": [
   {"idx": 128, "zh": "原文片段", "en": "译文片段",
    "scores": {"F": 3, "L": 4, "T": 3, "S": 3},
    "errors": [{"severity": "major", "type": "术语不贴切", "span": "flow data", "note": "此处指流量曲线，非流量率"}]}
 ] }
```

**schema 硬约束**（消费端 calibrate/verdict 按此校验，缺即从严）：四维 F/L/T/S 必须齐全且为 0-4 整数；severity 只认小写 `critical`/`major`/`minor`（未知值按 major 计）；任一维 ≤2 时 errors 必须非空。`reviewer` 与 `rubric_version` 是证书链字段，不可省。

段级通过 = 四维均 ≥3 且无 critical/major（判定交给 `verdict.py`，你不做稿级结论）。

## 红线

- 不改译文（返工是翻译会话的事，你只判定和举证）
- 不给「整体印象分」——只逐段，聚合交给工具
- 表面指标（句长/被动比例）不进入任何判分理由（Goodhart 条款）
- 噪声免疫：回译相似度、双引擎分歧等统计信号不是你的证据，你的证据只有 span 级原文对照
