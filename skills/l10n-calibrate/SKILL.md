---
name: l10n-calibrate
description: 评审校准与上岗——构建锚点集（人工标注 20-30 段）、计算评审者与人工的一致率、判定评审者是否可上岗、管理 rubric 版本与签认。首次使用表达层评审、更换评审模型、rubric 改版、评审被降级后必走本 skill。含交互点 1（rubric 签认）与交互点 2（锚点标注）。
---

# l10n-calibrate · 评审校准与上岗

> **职责**：把「AI 评审」从裸模型变成「被校准+受审计的评分器」。核心思想：评审者先对人工标注的锚点集考试，达标才上岗；rubric 先定版留档，才允许出分。
> **触发**：首次使用 / 更换评审模型或改 prompt / rubric 改版 / 抽检中评审理由抽核不合格被降级。

## 流程五步

### 1. rubric 定版与签认（交互点 1）
- 读 `assets/rubric-v*.md`；若是新版，呈给决策人**逐条确认**（四维定义、分类学、阈值、抽样方案）
- 签认后计算指纹并记入 `assets/rubric-v1.hash`（`python tools/verdict.py --hash assets/rubric-v1.md`）——**hash 不写回 rubric 文件**（写回会使文件变化、后续比对永远失败）；rubric 文件签认后内容冻结，改动=升 vN
- **为什么需要人**：rubric 是全流程的「法律」，AI 参与评分的前提下，法律必须先于人看过的分数存在——这是「不得出分后调参凑过」红线的物理实现

### 2. 锚点集构建（交互点 2）
选段标准：**20-30 段，好/中/差三层齐备**（大致 1:2:1），覆盖正文长段/表格单元/题注三种类型，含已知典型错误各至少 2 段（漂移、术语、翻译腔）。
**人工标注**：请用户对每段按 rubric 打分（给出分数模板；人在没有干扰的情况下独立打）。
落盘 `assets/anchor-set.json`：
```json
{"rubric_version": "v1", "annotated_by": "决策人", "date": "2026-11-21",
 "anchors": [{"idx": 42, "zh": "…", "en": "…", "human_scores": {"F":3,"L":2,"T":3,"S":3}, "human_errors": [{"severity":"major","type":"翻译腔"}]}]}
```
**为什么需要人**：锚点分是全系统的「真值基准」，模型不能自己给自己定基准。

### 3. 评审者考锚点
让待上岗的评审会话（走 `l10n-review` 流程）对锚点集盲评（不给人工分），产出评审 JSON。

### 4. 一致率计算与上岗判定
```bash
python tools/calibrate.py assets/anchor-set.json wk/review_anchor.json \
    --rubric assets/rubric-v1.md --cert-out wk/cert_<reviewer>.json --out wk/calib_report.json
```
判据（定版，fail-closed）：**一致率 ≥80% 且 critical 召回 100%，且评审覆盖全部锚点段（挑段提交直接 FAIL），且锚点集 20-30 段**；任一维 ≤2 分的段必须附 span 级理由，无理由低分段作废。
- 过 → calibrate.py 写出上岗证书 `cert_<reviewer>.json`（含 reviewer、rubric-hash、锚点集 hash、日期），`l10n-review`/`verdict.py --cert` 凭证书采信
- 不过 → 看 fail_reasons（一致率/召回/覆盖/规模/无理由低分，逐项列出），换评审模型或调 prompt，**重跑全部锚点**（不许只重跑错的）
- 演练/测试需用小锚点集时显式 `--min-anchors N`——证书自动标 `demo:true`，不得用于正式签发

### 5. 版本与失效管理
| 事件 | 动作 |
|---|---|
| rubric 改版（升 vN） | 锚点集增补 ≥5 段 → 重新校准 → 历史评审结果标注「旧 rubric」 |
| 更换评审模型/prompt | 全锚点重考 |
| 抽检中理由抽核一致率低（交互点 4） | 评审降级，回本 skill 第 3 步 |

## 红线

- **校准集不可污染**：锚点段不得出现在任何评审练习/预热对话里；人工标注一旦落盘不可改（改 = 升版本 + 全量重校准）
- 锚点选段记录机器字段（`sampled_by`/`selection_seed`，见 anchor-set 模板）——「谁选的段」可审计；锚点代打是纯数学上不可根除的，理由抽核（交互点 4）是唯一事后人防
- 一致率不达标的评审结果**作废重评**，不存在「差一点先用着」
- 调参只能发生在校准环节之后、下一轮评审之前——已出分的批次永不追溯调参
