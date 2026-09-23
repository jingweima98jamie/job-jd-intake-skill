# job-jd-intake

一个 Agent Skill：把招聘 JD 截图批量变成**可决策的投递包**。

丢进去一批岗位截图，它按固定流程产出：

- 每个岗位一个编号文件夹，JD 截图归档齐全
- 每个岗位一份公司背调文档：**是不是外包**、真实规模（参保人数拆平台水分）、口碑、风险信号、JD 逐条适配度表格、匹配度百分比、明确的投/不投建议、面试必问清单
- 判定要投的岗位，附一份按该 JD 定制的**单页 PDF 简历**（HTML 源文件可改，超页自动压回单页）
- 岗位收录清单、优先级排序与下一步动作

## 为什么是 skill 而不是一份提示词

流程固定、有判定规则、有可执行脚本（简历生成 + 单页校验），换成"每家公司背调一遍、再手工排一份简历"就是几小时的活。装成 skill 之后，下次丢截图直接跑同一套标准。

## 安装

技能的目录名就是技能名，把整个 `job-jd-intake` 文件夹放进所用工具的 skills 目录即可：

| 工具 | 目录 |
|---|---|
| WorkBuddy | `~/.workbuddy/skills/` |
| Claude Code | `~/.claude/skills/`（或 `/plugin marketplace add` 走插件市场） |
| Cursor / Codex / Gemini CLI / VS Code / GitHub Copilot 等 | 各自的 skills 目录，格式同为 SKILL.md（[agentskills.io](https://agentskills.io) 开放标准） |

```bash
git clone https://github.com/<你的用户名>/job-jd-intake.git ~/.workbuddy/skills/job-jd-intake
```

## 首次使用：建 profile.md

技能需要知道"你是谁"，所以第一次运行会引导你建 `profile.md`：

```bash
cp profile.example.md profile.md   # 然后填自己的信息
```

`profile.md` 里放四类东西：

1. **基本信息**：姓名、联系方式、所在城市
2. **履历事实库**：只写真实发生过的事和真实数字（简历只能从这里取材）
3. **写作铁律**：你自己不想在材料里出现的东西（例如"不写正在学"）
4. **路径配置**：工作根目录、简历母版 HTML 的位置

> ⚠️ **`profile.md` 是私有的，已在 `.gitignore` 里排除。** 它包含手机号、邮箱、真实履历，提交到公开仓库等于挂到网上。自己 clone 别人的仓库时也请先确认对方没有误传。

## 依赖

- Python 3.9+，`pip install pypdf`（校验简历页数）
- Chrome 或 Chromium（HTML 转 PDF）；找不到时用 `CHROME_PATH` 环境变量指定
- 可选：`PYLIBS` 环境变量，指向已安装 pypdf 的目录（不想装进全局环境时用）

## 目录结构

```
job-jd-intake/
├── SKILL.md                       # 流程主文件
├── README.md / LICENSE / .gitignore
├── profile.example.md             # 档案模板 → 复制成 profile.md
├── references/
│   ├── 背调模板.md                # 八段制背调文档模板
│   ├── 判定规则.md                # 命名规范、匹配度锚点、投递规则
│   └── 检索关键词库.md            # 背调检索词
├── scripts/
│   └── make_resume.py             # 规格驱动简历生成器
└── assets/
    ├── spec.example.json          # 简历规格示例
    └── resume-template.example.html  # 空白简历母版
```

## 简历生成器单独用

```bash
python scripts/make_resume.py assets/spec.example.json --root /path/to/output
```

它会：读取你的母版（排版、教育背景、照片都从母版取）→ 按规格生成 HTML → Chrome 无头导出 PDF → 校验页数 → 超过 1 页自动收紧 CSS 重导（最多 2 轮）→ 仍超页直接报错，不会静默给你一份 2 页简历。

## 许可

MIT。`LICENSE` 里的署名请改成你自己。

## 一点说明

这套流程是在真实求职过程中反复跑了十几批岗位沉淀出来的，判定规则（比如虚假招聘的红旗组合、匹配度四档锚点）来自实际踩过的坑。你可以按自己的行业调整 `references/判定规则.md`，但建议保留"不编造、先背调再判定、判定后才做简历"的顺序。
