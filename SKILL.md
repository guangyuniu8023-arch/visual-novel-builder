---
name: visual-novel-builder
description: 根据用户上传的 1-3 组角色图和角色背景设定（wiki），通过对话澄清需求，生成一个可玩的、9:16 竖屏手机端、带剧情分支选择和多结局的视觉小说/互动叙事 H5 游戏。题材不限（恋爱、悬疑、冒险、奇幻、科幻、日常等），由角色设定和用户偏好决定；HUD/封面/动画按题材主题配方自动适配。当用户要求制作视觉小说、互动剧情/互动叙事游戏、分支多结局游戏，或上传角色图/角色设定并要求做成游戏时使用。覆盖全流程：需求澄清、剧本生成（WebGAL 脚本）、立绘/背景/CG 生图、引擎装配、自动验收与交付。
---

# Visual Novel Builder（视觉小说生成器）

把「1-3 组角色图 + 角色 wiki」变成一个可玩的多结局竖屏视觉小说游戏。玩家在剧情分支点做出选择，选择驱动隐藏数值变化，导向不同结局（多角色支持主线/多攻略两种数值模式）。引擎使用内置的 WebGAL 竖屏版（`assets/engine`），剧本是 WebGAL 脚本，UI 按题材主题配方切换（HUD/封面/标题粒子随题材适配）。

## 总流程（状态机）

每个游戏是一个项目目录 `<workspace>/projects/<id>/`，由 `scripts/init_project.py` 创建，内含 `state.json` 记录流水线状态。**每完成一个阶段就更新 state.json，进入下阶段前必读。**

```
INTAKE → SCRIPT → ASSETS → BUILD → QA → DELIVER
```

| 阶段 | 先读 | 产出 | 出口条件（Gate，不满足禁止进入下阶段） |
|---|---|---|---|
| INTAKE | references/intake.md | `gdd.md`（游戏设计文档） | **用户明确确认 GDD** |
| SCRIPT | references/scriptwriter.md | `game/scene/*.txt` 剧本 | `validate_script.py` 零错误 |
| ASSETS | references/art-director.md | 立绘/背景/CG + `manifest.json` | `check_assets.py` 通过 + **用户确认立绘像原图** |
| BUILD | references/build.md | 可运行站点 `build/` | 本地服务能打开 + build.md 界面检查点全过 |
| QA | references/qa.md | `qa_report/` 截图与结论 | 验收清单全绿，否则按 qa.md 回炉规则返工 |
| DELIVER | — | 聊天窗口内可玩的 H5（本地预览 URL + `build/` 目录） | QA 通过 |

DELIVER 的交付形态（QA 全绿后）：最终产物是**聊天窗口里直接可玩的 H5**。向用户交付**本地预览**（`python3 -m http.server <端口> -d projects/<id>/build`，报告 URL 与端口，环境支持时给预览卡片链接）+ **build/ 目录本体**（自包含静态站点，用户可自行处置）。默认**不做公网部署**；用户明确要求公网分享时，用 **GitHub Pages**（`gh repo create <id>-game --public --source=build --push` + `gh api repos/<user>/<repo>/pages -X POST -f source[branch]=main -f source[path]=/`，约 1-2 分钟构建后 `https://<user>.github.io/<repo>/` 可玩；仓库公开=任何人可玩，介意则用私有仓库+授权访问）。交付时一并报告：游戏名、结局数与达成路径数、QA 结论、已知简化项（见 qa.md 环境注意事项）。

## 硬规则

1. **GDD 未经用户确认，不得写剧本。** 剧本不过校验，不得生图（剧本改动会让资产全部报废）。
2. **剧本一律使用数值变量驱动分支**：`setVar` 定义分支数值（好感度/信任度/线索数等，由题材决定，见 scriptwriter.md）+ `choose` 选项 + `jumpLabel -when=条件` 判定结局。禁止写死线性剧情。
3. **主题皮肤按 GDD「主题配方」从 assets/themes 选择**（anime 恋爱暖系 / noir 悬疑冷系 / warmwood 木质暖调 / midnight 深夜琥珀 / simple 简约，新题材可复制现有主题改 theme.json 与视觉参数），**禁止从零写 UI**——新主题必须以现有主题的完整 SCSS 为骨架（结构类清单见 build.md 主题配方节）。装配+换肤统一走 `scripts/assemble_build.sh <id> <主题> [游戏名]`（内部调 apply_theme.sh，含自检）。
4. **生图一律走 `scripts/gen_image.py`**，provider 由 `tools/providers.yaml` 配置；生图模型不出透明底，立绘透明背景的处理按 art-director.md 第 4 节。
5. 所有资产按 art-director.md 的**竖构图规范**生成（背景/CG 9:16，立绘 2:3）。
6. **视觉参数零硬编码**：玩家可见的一切参数（颜色、动效、粒子、兜底渐变、点击闪色、封面投影色）必须来自 GDD/theme.json 配方注入或派生，禁止在引擎/脚本里写死。定死的只有**结构骨架**（SCSS 结构类、占位符机制、布局系统）——骨架是安全网，参数是自由度。新增任何可见常量前自问：它该在 theme.json 里吗？
7. **粒子动效从零设计**：引擎不预置任何粒子动效（无词汇库、无类型枚举）。每个项目的粒子"怎么动"由 agent 按主题意象推导后从零写成 `effects.css`（项目根），经 apply_theme 注入；tile（`title_particles.png`）同为项目素材。**禁止从预置动效里选型**——推导方法见 build.md「动效设计」。
8. 每个 gate 失败：按对应 reference 的回炉规则返工，禁止带病进入下一阶段。

## 项目目录结构

```
projects/<id>/
├── gdd.md              # INTAKE 产出
├── effects.css         # 粒子动效设计（BUILD 产出：按主题从零推导编写，apply_theme 注入双端）
├── state.json          # 流水线状态（init_project.py 维护）
├── character/          # 用户上传的角色图、wiki、提取的角色卡
├── game/               # 游戏内容（引擎 game/ 目录的覆盖层）
│   ├── scene/*.txt     # 剧本（SCRIPT 产出）
│   ├── background/ figure/ bgm/ vocal/ video/   # 资产（ASSETS 产出）
│   └── config.txt      # 游戏名/标题图/标题 BGM
├── manifest.json       # 资产清单（check_assets.py 使用）
├── build/              # BUILD 产出（引擎 + game 覆盖层合成）
└── qa_report/          # QA 产出
```

## 工具脚本

| 脚本 | 用途 |
|---|---|
| `scripts/init_project.py <id>` | 创建项目骨架与 state.json |
| `scripts/validate_script.py <scene目录> [--min-endings N]` | 剧本校验：标签/跳转/选择支闭合、结局可达性、变量先定义后使用 |
| `scripts/gen_image.py` | 生图（provider 可配，含重试），参考图自动上传转公网 URL |
| `scripts/check_assets.py <game目录> <manifest>` | 剧本引用的资产是否全部存在、立绘 PNG 是否含透明通道 |
| `scripts/bake_title.py <封面图> <主标题> [--eng 副标] [--tagline 标语]` | 封面文字**降级路径**：直出封面文字校对连错 3 次时，对干净底图后期排版（描边色取 cover.stroke）；`--shrink-only` 为直出封面的入库瘦身步骤 |
| `scripts/gen_particles.py --out <路径> --type petals\|rain\|motes\|snow\|fog [--color 主色] [--count N]` | 绘制粒子 tile 的**工具**（透明 PNG，垂直无缝循环）：形状库按需取用，也可自行创作/AI 出图；粒子"怎么动"不在此——那是项目 effects.css 的事 |
| `scripts/e2e_test.py <url> --out <目录> [--choice-strategy first\|middle\|last]` | 无头浏览器 9:16 跑通：标题→对话→选项→结局，逐步截图；换策略可覆盖不同结局路线 |

## 阶段入口

- 用户刚上传角色图/wiki → 读 `references/intake.md`
- 要写/改剧本 → 读 `references/scriptwriter.md`（含演出转场与分支回溯规范）
- 要生成任何图片资产 → 读 `references/art-director.md`
- 要装配引擎/定制界面 → 读 `references/build.md`
- 要验收/排查成品 → 读 `references/qa.md`
