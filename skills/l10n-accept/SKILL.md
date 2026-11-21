---
name: l10n-accept
description: 抽检验收——交付前对英文译文做分层抽样（10%、下限 30 段、结论区加权），按错误分级判定稿级通过与否（critical=0、major≤2/千词），记录缺陷密度台账，引导抽检复核与签发签字。交付前验收、判断「这稿能不能交」时使用。含交互点 4（评审理由抽核）与交互点 5（抽检复核+签发）。
---

# l10n-accept · 抽检验收

> **职责**：回答「这稿可以交吗」，用统计抽检替代逐段通读，并把每份报告的缺陷密度记进台账（攒趋势，让「基本无错」在统计上站得住）。
> **前置互锁**：事实层机器门禁全绿（qc/consistency/回译）+ 表达层评审 JSON 已产出（评审者已上岗）。缺 → 退回对应阶段。

## 流程四步

### 1. 分层抽样
```bash
python tools/sample_picker.py wk/units.tsv --rate 0.10 --min 30 --weight conclusions --out wk/sample.json
```
分层 = 章节 × 段落类型（正文长段/表格单元/题注标题，TSV 属性列即分层键）；每章 ≥2 段正文；结论/建议/摘要章节 ×2 加权。产出抽样段清单。

### 2. 评审与判定
对抽样段取评审 JSON 的对应记录：
```bash
python tools/verdict.py wk/review.json --rubric assets/rubric-v1.md \
    --cert wk/cert_<reviewer>.json --sample wk/sample.json \
    --docx report_EN_v2.docx --out wk/verdict.json
```
稿级判据（定版）：**critical = 0 且 major ≤ 2 处/千词**（minor 不计）。判定报告 fail-closed：绑定交付 docx 的 sha256（防判定移植到别的稿子）、校验证书与 rubric 版本、抽样缺段 >5% 即 FAIL、缺维度/未知 severity 从严处理——**没有干净输入就没有 PASS**。增量场景另加 `--diff wk/changed_idx.txt`（改动段必须全部覆盖评审）。

**不过的升级路径（固定，不临场发挥）**：
- 有 critical 或 major 超标集中在个别章节 → 该章节全查 + 定向返工 + 复检
- major 弥漫全稿 → 全稿升级为全量表达层评审，逐段返工

### 3. 评审理由抽核（交互点 4）
从评审 JSON 抽 5-10 条（优先含 major 标注的），呈给用户核：「评审说 [span] 有 major 问题因为 [理由]——你同意吗？」
**为什么需要人**：这是「评审的评审」——AI 评分的信任链顶层必须有人。
**记录落点**（防断粮）：
```bash
python tools/defect_log.py quality --doc report_EN_v2 --reviewed 8 --agree 7
```
一致率 <70% → 输出降级标记，评审回 `l10n-calibrate` 重校准。

### 4. 台账与签发（交互点 5）
```bash
python tools/defect_log.py add --doc report_EN_v2 --verdict wk/verdict.json --notes "…"
python tools/defect_log.py trend --check-rubric assets/rubric-v1.md   # 看趋势 + 核对 rubric 未偷改
```
同稿重复 seed 拒绝入库（防抽检运气狩猎）；判定报告不带 doc hash / rubric hash 的新版产物不入台账。
**签发呈报**（给用户的签发卡，一次给全）：
- 判定结果 + 分项统计（critical/major 密度/四维分布）
- critical/major 逐条明细（附 span）供逐条复核
- 交付物 hash 与证书信息（判定报告内嵌）
- 七个交互点的完成状态
- 事实层门禁状态（引用阶段表 5-9 的产物）

用户逐条核完签字 → 交付放行（`l10n-incremental` 出交付声明）。**未签字不得出交付声明**（纪律 3、4）。

## 红线

- 抽样清单由工具生成，**不许人工挑段**（挑段 = 抽检失效）
- 判定只认 verdict.py 输出，不许看着「差不多」口头放行
- minor 不阻塞签发，但进台账（趋势用）
- 每份报告的判定结果必进台账——没有趋势数据，「基本无错」永远是口说
