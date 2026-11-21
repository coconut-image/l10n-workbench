---
name: l10n-sediment
description: 裁决沉淀——引导用户逐条裁决不确定列表（每份报告 3-8 条），术语类回填 glossary、风格类回填 style 文件，provisional 条目二次裁决升格，错误模式回流为资产提案。不确定列表裁决、沉淀术语与风格记忆、把经验变成下次的硬约束时使用。含交互点 3（逐条裁决）与交互点 6（缺陷回流确认）。
---

# l10n-sediment · 裁决沉淀

> **职责**：把每份报告产生的人的判断变成资产，让下一份报告的 AI 直接站在这次裁决之上——「术语表→AI 建议→人工改→沉淀为强记忆」闭环的落地件。
> **输入**：机器信号清单（既有 review_list 流程产物）+ 表达层评审的 flagged 段 + 源稿问题。**输出**：更新后的 glossary/、style.md、决策记录。

## 流程三步

### 1. 不确定列表裁决（交互点 3）
先把机器信号收敛（既有纪律：36 条信号 → 真需拍板的 3-8 条；超 20 条 = 术语表要大修，退回 `l10n-glossary`）。
每条呈**结构化选择**，不是开放问题：
> 「『準確率』：本次用了 `accuracy`（评审与第二引擎一致），术语表规定 `accuracy rate`——A 改译文按表 / B 改术语表删 rate / C 此处特例保留。请选」

**为什么需要人**：裁决的是「以后都这么说」的规则，规则的所有权在人。
裁决结果落 `wk/decisions.json`，**每条必须含 `kind` 字段**（`term`/`style`/`table_usage`，回填工具按它分流，缺 kind 整批拒写）：`{"kind": "term", "term_zh":…, "chosen":…, "rejected":…, "reason":…, "date":…}`。

### 2. 分流回填（交互点 6 确认后执行）
```bash
python tools/glossary_backfill.py wk/decisions.json --glossary wk/glossary --style wk/style.md
```
分流规则：
| 裁决性质 | 去向 | 形态 |
|---|---|---|
| 术语定译（X→Y） | glossary P 层 | 新条目，标 provisional |
| 风格/语气偏好（摘要用主动语态等） | style.md | 规则行 |
| 表格用法类（表头锁定词） | glossary「用法」列 | 修订 |
| 源稿问题（数据/用词不一致） | 不回填 | 反馈客户清单（翻译不修源稿） |

**执行前把回填预览呈用户确认**（diff 形式）——资产是全流程共享的，写错污染所有后续报告。

### 3. 升格与生效
- provisional 条目在**下一份报告**再遇同类裁决 → 升格正式（`glossary_backfill.py --promote`）
- 改变既有译法的裁决（原 A 现 B）→ **必须回扫**已定稿内容（既有 consistency.py 重跑纪律），不回扫不生效
- style.md 的规则随翻译任务书下发（软约束），glossary 是硬约束——别把风格塞进术语表

## 红线

- 一次裁决不升格为全局规律（「一次≠规律」，provisional 机制的意义）
- 回填必须经交互点 6 确认，不许静默写资产
- 源稿问题永远不回填、不代改——那是客户的稿子
