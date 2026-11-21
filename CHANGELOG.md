# CHANGELOG · 中译英报告交付工作台

本框架遵循语义化版本：MAJOR（结构性变化）/ MINOR（skill 新增、rubric 变更）/ PATCH（坑册、工具修复）。每条变更注明触发来源。

## 1.2.0 · 2026-11-21

对抗式审查（三路子代理：代码/体系一致性/红队绕过）修复批次，36 项发现落地：
- 新增 `tools/export_feedback.py`：反馈包白名单脱敏导出，替换裸 zip 命令（防泄密，红队 R0-7）
- `verdict.py` 全面 fail-closed：空评审/缺段>5%/缺维度/未知 severity（从严计 major）一律拒绝或判 FAIL；`--rubric` 必填；`--docx` 绑定交付物 sha256+实算词数（防谎报词数与判定移植）；`--cert` 证书链校验；`--diff` 增量改动段全审；seed 回填报告
- `calibrate.py`：锚点覆盖门（缺段=FAIL，防挑段提交）、规模门（默认 ≥20，显式调低标 demo）、reviewer 读取与上岗证书产出、rubric_version 互检、无理由低分段作废、fail_reasons 逐项
- `sample_picker.py`：属性列「表格单元/题注」并入分层（不再丢弃）、标题判定加无句读约束、补齐 room 负数与单层抽干修复、min 超全集告警
- `freq_scan.py`：候选逻辑重写为逐轮掩码重计（滑窗噪声清零）、术语表表头泄漏修复、虚词碎片过滤、docx 防御
- `defect_log.py`：字段校验+父目录自建、`quality` 子命令（交互点 4 落点）、seed 防狩猎（同稿重复 seed 拒入库）、`trend --check-rubric` 防偷改
- `glossary_backfill.py`：缺 kind 整批拒写（防按文档操作静默丢数据）、promote 锚定状态列、重跑去重、路径前置校验
- 文档对齐：rubric-hash 落外部文件（修复自指矛盾）、总纲计数 0→12/七交互点、decisions 格式补 kind、l10n-calibrate 证书描述与实现对齐、l10n-accept 命令补全参数、版本纪律 PATCH/MINOR 修正

## 1.1.0 · 2026-11-21

- 新增 `l10n-improve`（回顾迭代 skill）：错误模式提炼、四向归因修订提案（交互点 7）、反馈包导出回流维护者（#需求输入：决策人 2026-11-21——「越用越好」+ 真实样例回流迭代）
- 总纲新增阶段 12（回顾迭代）与交互点 7（框架修订确认）；版本纪律与 CHANGELOG 机制生效

## 1.0.0 · 2026-11-21

- 首版：总纲 + 六个子 skill（glossary / review / calibrate / accept / sediment / incremental）+ 六工具（freq_scan / sample_picker / calibrate / verdict / defect_log / glossary_backfill）+ rubric-v1 签认资产
- 需求书 v1.0 冻结：rubric 四维（F/L/T/S）、错误分类学（critical 一票否决、major≤2/千词、minor 不计）、抽样（10% 下限 30 段结论区 ×2）、锚点校准门（一致率 ≥80% + critical 召回 100%）
- 设计：superpowers 式集合（总纲路由+互锁纪律），增量整合既有 15 脚本为事实层执行件
