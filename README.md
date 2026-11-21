# 中译英报告交付工作台（l10n-workbench）

> 仓库：https://github.com/coconut-image/l10n-workbench（public，直接 clone 即用）

一套把「中文工程报告 → 可直接交付的英文 docx」做成**AI 一遍过 + 机器全量兜底 + 人只花极小预算签发**的完整体系：1 本总纲手册 + 7 个子 skill + 7 个小工具 + 1 份签认质量标准（rubric）。人只出现在 **7 个拍板点**，其余全部由 skill 路由、工具执行、资产沉淀。

> 给会用 AI 的翻译/技术文档/咨询交付人员。**5 分钟看懂整体怎么干活**读 `docs/工作思路总览_v1.md`；设计理由与单 skill 方案的对比论证见 `docs/为什么这样设计_v1.md`（读它就懂这套东西为什么长这样）。

## 它解决什么

你的翻译流程「事实层」（结构/数字/术语/不错位）已经有机器全量检查兜底；**表达层**（语序自然/语气恰当/论证清楚）此前只能靠人逐段通读。本工作台给表达层补上可验证的信任机制：

- **校准门**：AI 评审先对人工标注的锚点集考试（一致率 ≥80% 且 critical 召回 100% 才上岗，产出证书）
- **评审**：上岗的评审会话按定版 rubric 四维（忠实/流畅/术语/风格）逐段打分，低分必须附原文引用
- **抽检**：分层抽样（10%、下限 30 段、结论区加权），critical 一票否决、major 密度 ≤2 处/千词才可签发
- **沉淀**：裁决结果回填术语表/风格记忆，错误模式回流为资产——**越用越好**

全部门禁 fail-closed：输入不完整/证书无效/rubric 改动未重校准，一律拒绝出分，绝不静默放行。

## 安装（Claude Code）

```bash
git clone https://github.com/coconut-image/l10n-workbench.git /tmp/l10n-workbench   # 或解压交付 zip
# skills 全部安装（全局）：
cp -r /tmp/l10n-workbench/skills/l10n-* ~/.claude/skills/
# 或只装到某个项目：cp -r /tmp/l10n-workbench/skills/l10n-* <项目>/.claude/skills/
```

- `tools/` 与 `assets/` 不装进 skills——放在你项目的工作区旁，跑命令时用路径引用
- 装完重启 CC 会话；对 AI 说「翻译这份报告」/「交付前抽检」/「客户改稿了」，总纲会自动路由
- **首次使用**：先走 `l10n-calibrate`（rubric 签认 + 锚点标注，一次性，约 1 小时），此后每份报告只是例行流程

## 人的全部工作（7 个拍板点）

| # | 时机 | 你做什么 | 耗时 |
|---|---|---|---|
| 1 | 首次/改版 | 签认 rubric（四维+分类学+阈值） | 一次性 30 分钟 |
| 2 | 首建/改版 | 给 20-30 段锚点按 rubric 打分 | 一次性 1 小时 |
| 3 | 每份报告 | 裁决不确定列表（3-8 条，选译法） | 10 分钟 |
| 4 | 每份报告 | 抽核 5-10 条评审理由 | 10 分钟 |
| 5 | 交付前 | 逐条核 critical/major、签字签发 | 10 分钟 |
| 6 | 每份报告后 | 确认错误模式→资产回填 | 5 分钟 |
| 7 | 攒 3-5 份报告 | 确认框架修订提案（diff） | 半小时 |

5 万字报告的目标：人的总投入 ≤30 分钟/份（首建锚点另计）。

## 目录结构

```
├── README.md                 ← 本文件（安装与使用）
├── CHANGELOG.md              ← 版本记录（1.2.0 = 对抗审查修复版）
├── skills/                   ← 8 个 skill（总纲 + 7 子）
│   ├── l10n-workbench        ← 总纲：阶段表 0→12、路由、互锁纪律（先读这个）
│   ├── l10n-glossary / l10n-review / l10n-calibrate / l10n-accept
│   └── l10n-sediment / l10n-incremental / l10n-improve
├── tools/                    ← 7 个单文件工具（标准库 only，--help 自解释）
├── assets/rubric-v1.md       ← 签认资产（四维/分类学/阈值/抽样，定版）
├── docs/                     ← 需求书 + 为什么这样设计
└── samples/                  ← 合成样例 + 端到端演练（bash samples/run_e2e.sh）
```

## 先跑一遍演练（强烈建议）

```bash
bash samples/run_e2e.sh
```

用合成样例走完整条链：高频词扫描 → 校准（好评审上岗/坏评审被拦，证书产出）→ 分层抽样 → 判定（含预埋 critical 的稿被签发拦截）→ **攻击演示（空评审/假证书被拒）** → 台账 → 裁决回填。全程无客户数据，产物在 `samples/e2e_out/` 对照看。

## 与既有 zh-en-docx-translation（v2.4.0）的关系

**增量整合，不推翻**：既有 15 个脚本（qc/consistency/backtranslate/merge/polish_diff 等）原样保留为事实层执行件，工作台总纲的阶段 0-9 直接编排它们；本工作台新增的是表达层验证链（校准→评审→抽检→沉淀）与全流程的人机交互设计。迁移路径见 `docs/为什么这样设计_v1.md` 末节。

## 技术附录（给维护者）

- 工具契约：单文件、Python 3 标准库 only、fail-closed、`--help` 自解释；改阈值须同步 rubric 与 CHANGELOG
- 证书链：calibrate 产出 cert（reviewer+rubric-hash+锚点 hash）→ verdict `--cert` 物理校验 → 台账记 hash 可回溯
- 反馈通道：`tools/export_feedback.py` 白名单脱敏导出反馈包（verdict 只留计数、中文术语换指纹、notes 默认拒绝）——发给维护者即可远程迭代
- 版本纪律：MAJOR/MINOR/PATCH 见 CHANGELOG 头；rubric 改版必须全量重校准

## 不承诺的事（如实）

- 图片内文字不翻（单独立项）；锚点「人工代打」纯数学上不可根除（理由抽核是事后人防）；无分词器下的高频词扫描有少量碎片需人工分辨；本体系的质量保证是 AI 辅助口径（如实在交付声明中描述），不等同 ISO 17100 第二人通读。
