# Visual Novel Builder Skill

让 coding agent **从零制作一部可玩的视觉小说**的完整流程 skill。

输入：1-3 组角色图 + 角色背景设定（wiki）+ 用户的模糊想法（甚至可以没有想法）。
输出：一个**聊天窗口内直接可玩的 9:16 竖屏视觉小说 H5**——带剧情分支选择、隐藏数值驱动、多结局，封面/HUD/开场动效全部随题材主题自动生成。

题材不限：恋爱、悬疑、冒险、奇幻、科幻、日常均可。不是填空模板——视觉风格、动效、配色、字体质感全部由 agent 从角色设定和剧情意象**现场推导**，每个参数都要求带推导依据。

## 它能做什么

跑完一遍，你会得到类似这样的成品（均为本 skill 实测产出）：

| 案例 | 题材 | 结构 |
|---|---|---|
| 《雨停之前》 | 治愈系 | 单结局，双版本情绪变体 |
| 《同一场雨》 | 双角色恋爱 | 双主线数值，HE/BE 结局 |
| 《第三小时》 | 都市奇幻 | 双版本 GDD（自由/孤独氛围对仗） |
| 多攻略悬疑案 | 悬疑 noir | 多角色攻略，4 结局全路线可达 |

具体能力：

- **需求澄清**：从零需求或一句话想法出发，通过对话补全缺口，产出 GDD（游戏设计文档），用户确认后才动工
- **剧本生成**：WebGAL 脚本，分支选择驱动隐藏数值，导向多结局；自动校验语法
- **视觉资产**：立绘（参考图保持角色一致性）、背景、CG、**封面直出**（标题字体设计由生图模型随主题生成，非后期叠字）
- **开场动效从零写**：引擎零预置粒子代码，每个项目的粒子意象、运动、配色都由 agent 按主题现场推导写成 `effects.css`（雨是沉降、灰烬是上浮，不是同一批扫光换色）
- **一键装配**：内置 WebGAL 竖屏引擎 + 主题系统（HUD/对话框/选择支随题材适配）
- **自动验收**：无头浏览器跑完全部结局路线，逐张截图检查，全绿才交付

## 对宿主 agent 的要求

本 skill 是**流程文档 + 脚本工具集**，需要一个能读文档、跑命令、看图的 coding agent 来执行。要求：

**能力面**

- 能执行多阶段长流程（六阶段状态机，单项目约 30-60 分钟），并在阶段间持久化状态（`state.json`）
- 能看图（VLM 能力）：验收环节要逐张判读截图、校对封面标题文字、确认立绘像不像用户上传的角色图
- 能与用户多轮对话：INTAKE 阶段需要澄清需求，ASSETS 阶段需要用户确认立绘

**环境依赖**

| 依赖 | 用途 | 安装 |
|---|---|---|
| Python 3.10+ | 全部脚本 | — |
| Pillow | 图片处理（抠图/瘦身/降级叠字） | `pip install Pillow` |
| agent-gw Python SDK ≥ 0.2.6 | 生图（默认 provider） | `pip install agent-gw`，key 用环境变量 `KIMI_API_KEY` 或 `~/.kimi/agent-gw.json` |
| Playwright + Chromium | QA 无头浏览器验收 | `pip install playwright && playwright install chromium` |
| sh / bash | 装配与主题脚本 | macOS/Linux 自带 |

**网络**：生图需要能访问生图 API（默认走 Kimi agent-gw；`tools/providers.yaml` 预留了 OpenAI 兼容接口的插拔位）。

**不需要**：Node.js、前端构建工具、公网部署能力（产物是本地 H5，不做公网发布）。

## 安装

### 方式一：作为 agent skill 挂载（推荐）

把本仓库整个目录放进你的 agent 运行时的 skills 目录，让 agent 能在索引中发现它：

```bash
git clone https://github.com/guangyuniu8023-arch/visual-novel-builder.git
# 然后把 visual-novel-builder/ 目录复制/链接到你 agent 的 skills 路径，例如：
#   Kimi Work:  .../daimon/skills/visual-novel-builder/
#   Claude Code: ~/.claude/skills/visual-novel-builder/
```

`SKILL.md` 顶部的 frontmatter（name + description）就是触发索引——agent 看到"制作视觉小说 / 互动剧情游戏 / 上传角色图做游戏"类请求时会命中它。

### 方式二：手动喂给 agent

不支持 skill 索引的环境，直接在对话里告诉 agent：

> 阅读 `<仓库路径>/SKILL.md`，严格按其中的流程和 references/ 文档执行。

效果相同，只是少了自动触发。

### 验证安装

对 agent 说一句：**"用这两张角色图给我做个视觉小说"**（附图）。agent 应该开始 INTAKE 阶段的澄清提问，而不是直接写代码。如果它上来就写 HTML，说明没读到 skill。

## 使用方式

挂载后无需记命令，用自然语言即可：

- **零需求**："把这个角色做成游戏" → agent 带推断提问，补全 GDD
- **模糊需求**："想要雨夜治愈系的感觉" → 只问真缺口，氛围直接采用
- **明确需求**："双主角、悬疑、4 个结局" → 直接进 GDD 确认

全流程：`INTAKE → SCRIPT → ASSETS → BUILD → QA → DELIVER`，每阶段有出口 Gate（如"用户明确确认 GDD""立绘像原图""QA 全绿"），不满足禁止进入下阶段。

## 目录结构

```
SKILL.md            入口：状态机、硬规则、交付定义
references/         各阶段执行文档（intake / scriptwriter / art-director / build / qa）
scripts/            工具链：init_project / gen_image / bake_title / trim_asset /
                    validate_script / check_assets / assemble_build / e2e_test
assets/engine/      内置 WebGAL 竖屏引擎（13M，开箱即用，无需构建）
assets/themes/      主题系统（HUD/对话框/选择支样式骨架，配色随 GDD 配方注入）
tools/providers.yaml  生图 provider 配置（默认 agent_gw，预留插拔）
CHANGELOG.md        版本演进（每版都是实测蒸馏出的通用策略）
```

## 设计原则

1. **视觉随内容推导，零预置模板**——没有任何"悬疑=蓝、恋爱=粉"的查表规则；每个主题参数必须能从角色/剧情意象说出推导依据，否则 QA 判回炉
2. **Gate 驱动，不靠自觉**——每阶段出口条件明确，脚本化校验（语法、资产存在性、结局可达性）能自动的全自动
3. **所有优化蒸馏回 skill**——每个版本改动都来自真实案例踩坑，且写成通用策略（"遇到 X 类问题按 Y 推导"），而不是只修当前项目

## License

MIT
