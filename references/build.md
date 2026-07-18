# BUILD：引擎装配与界面定制

产出：`projects/<id>/build/`——引擎 dist + `game/` 覆盖层 + 皮肤 + 界面补丁。出口条件：本地 HTTP 服务打开后，标题页和游戏内界面符合本文全部检查点。

## 装配流程

```bash
scripts/assemble_build.sh <id> <主题> [游戏显示名]   # 一键完成下述全部步骤+自检
```

**装配前置备齐（缺一 apply_theme 即报错退出）**：

1. `effects.css`（项目根）——粒子动效，按本文「动效设计」节从 GDD 主题配方的动效语义从零编写
2. `game/background/title_particles.png`——粒子 tile，按 GDD 粒子意象用 gen_particles.py 绘制 / gen_image.py 生成 / 自行创作

脚本做的事（等价手工步骤，仅排查时需要）：

```bash
rm -rf <id>/build                       # 必须！init_project 预建了 build/，
                                        # 直接 cp -r 会嵌套成 build/engine
cp -r assets/engine <id>/build          # 引擎 dist 为基座
cp -r <id>/game <id>/build/             # 游戏内容覆盖（scene/background/figure/config.txt…）
assets/themes/apply_theme.sh <主题> <id>/build   # 应用皮肤（build 或 build/game 均可，脚本自适配）
```

注意：`apply_theme.sh` 内部用 perl 做就地替换（GNU/BSD sed 语法互斥），且会在 `__FX_CSS__` 等占位符残留时**直接报错**——看到 ERROR 不要跳过，说明 index.html 注入失败，落地页动效会静默失效。

## 主题配方（HUD/封面/动画随题材适配，不再一成不变）

### 视觉策略推导法（强制：参数必须推导，禁止查表）

**主题参数不是从"题材→主题"的映射表里查出来的，是 agent 从本项目的内容主体推导出来的。** 推导产物写进 GDD 主题配方节，每个参数带一句"为什么是它"。

**第一步：从角色卡与剧情提炼视觉意象**（这是全部参数的源头）
- 角色代表色/气质（角色卡外貌锚点：凌霜=黑白灰街头冷感）
- 核心场景与光源（剧情发生地：深夜老街=琥珀路灯、雨夜木工房=暖台灯）
- 情绪温度与节奏（治愈=慢、燃=克制中爆发、悬疑=冷）

**第二步：逐参数推导**（每个参数都要能答出"为什么"）

| 参数 | 推导依据（从意象出发，不是从题材出发） |
|---|---|
| primary 主色 | 核心场景光源色 × 角色代表色的交集。凌霜黑白灰+深夜老街 → 琥珀（路灯），而不是"竞技=热血红" |
| 粒子意象 | **故事核心场景里真实存在的漂浮物/动态元素**：雨夜故事=雨、木工作坊=木屑光尘、深夜街道=灯尘、雪日=雪。场景里没有的粒子不许出现（都市恋爱撒花瓣前自问：场景里有花吗）。意象只决定"粒子是什么"，**它怎么动必须按「动效设计」节从零推导并写进 effects.css**——不许出现"所有粒子都是圆点垂直下落"，也不许从预置动效菜单里选型 |
| 粒子颜色/密度 | 与光源同色；情绪越静，密度越低 |
| sheen 扫光 | **场景里是否存在移动光源**（车灯/霓虹/日光）——深夜街道有（琥珀低峰），木屋/雨夜室内没有（关闭）。这条不是"题材配不配"，是"世界里有没有" |
| kenburns 推拉 | 叙事节奏：情绪越沉越慢越克制（16-18s、112-115%），越明快越快越大（14s、117%） |
| fallback 兜底渐变 | 封面暗部色调——玩家首帧看到的是它 |
| 封面氛围 | 核心场景 + 情绪温度的直译（midnight city street, warm amber lamps, lonely but warm） |

**第三步：理由落档**。GDD 主题配方节里每个参数后写推导句（例："primary=#E8A33D：取自 wiki'深夜骑电动车兜风'的街灯意象，落在黑白灰人设上作暖点缀"）。**写不出推导句的参数 = 没推导，按回炉处理。**

**预设主题（anime/noir/warmwood/midnight/simple）的定位是结构骨架与兜底**：SCSS 骨架必须复用（防结构缺失翻车），时间紧或用户全权委托时可从最近似的预设起步再按推导改参数——**但禁止直接套预设交差**。新题材=复制最近骨架 + 推导参数覆盖。

题材+基调在 GDD 落成「主题配方」节，构建时由 `apply_theme.sh` 一键应用：

1. **theme.json 字段**（每主题一份，`assets/themes/<name>/theme.json`）：

```json
{
  "name": "noir", "mood": "悬疑/黑暗/推理",
  "primary": "#8FD8C6", "text": "#DCE3EE",
  "particle": {"imagery": "冷雨夜斜雨", "color": "#A8C8E8", "count": 90, "note": "推导落档：雨丝的色相/密度，供画 tile 时参考；动效本体在项目 effects.css"},
  "effects": {
    "sheen": {"enabled": false},
    "kenburns": {"duration": "18s", "zoomFrom": "104%", "zoomTo": "111%"}
  },
  "cover": {"stroke": "#8FD8C6", "prompt_mood": "rainy night, cold color grading, low saturation"},
  "hud": "玻璃拟态深色对话框+荧光青名签+档案卡片选择支+锐利描边按钮"
}
```

`particle` 段是 **tile 设计的推导落档**（画什么、什么色、多密，字段可自由扩展），不再是驱动脚本生成的枚举配方；`effects` 段的 sheen/kenburns 是**推导参数注入**（下面详述）；而**粒子动效本体 = 项目根 `effects.css`**，由 agent 按主题从零编写（见下「动效设计」）。

**effects 动效配方**（动态封面的扫光与推拉，落地页与 React 层双端同步注入）：

- `sheen` 扫光：`enabled` 开关 + `tint`（"r,g,b"）+ `peak`（峰值透明度 0-1）+ `duration`。**不是每个题材都该有扫光**——治愈/悬疑关掉（光面扫过破坏氛围），恋爱用白色 0.30，深夜题材用琥珀低峰（240,200,120 @ 0.14）像远处车灯。判据：扫光是否服务情绪，不服务就关
- `kenburns` 封面推拉：`duration` + `zoomFrom`/`zoomTo`。情绪越沉越慢（治愈 16s+/悬疑 18s），幅度越克制（zoomTo 112-115%）；明快题材 14s、117%
- `fallback` 兜底渐变：封面图就位前落地页的底色渐变，必须与封面暗部色调一致（玩家首屏第一帧看到的是它，不是封面图）
- 点击闪色：无需配置，自动从 `primary` 派生（30%/60% 透明度渐变）
- 缺省（旧 theme.json 无 effects 块）：扫光白色 0.30/9s，推拉 14s 104→117%，与旧行为一致

**动效设计（粒子怎么动——从零写，引擎零预置）**：

引擎不内置任何粒子动效，只提供挂载点：落地页层 `.html-body__title-enter::before` 与 React 封面层 `.css-kb8n67::before`（结构相同：`title_particles.png` 平铺），以及样式块末尾的 `/*__FX_CSS__*/` 注入占位符。动效本体是**项目根 `effects.css`**，由 agent 按以下链路从零推导编写：

1. **意象 → 运动语义**：先回答"这个东西在故事世界里怎么动"，用物理直觉描述——雨受重力直坠、速度快；灯尘随热气流上浮、忽明忽暗；花瓣受风飘落、左右摇曳；雾贴地水平流动。**先写语义句，再碰参数**。
2. **语义 → 技术选型**：
   - 单层平铺位移（最常用）：`@keyframes` 驱动 `background-position`，形状由 tile 承担
   - 双层视差：sheen 关闭时 `::after` 层空闲，可征用作远层（慢、小、淡），`::before` 作近层（快、大、实），速度差出景深
   - 透明度呼吸：`@keyframes` 里插值 `opacity`（灯尘/雾的"忽明忽暗"）
   - 禁止：大面积 `blur`/`filter`（移动端掉帧）、JS 定时器驱动（脱离样式层管理）
3. **技术 → 参数**：方向角、周期时长、摆幅、透明度呼吸幅度、缓动曲线，逐项从语义推（"急坠"→ 周期短 + linear；"摇曳"→ 横向正弦式往返 + 回零）。情绪越静，速度越慢、密度越低。
4. **落成 effects.css**，铁律：
   - **同时选中两端**：`.html-body__title-enter::before, .css-kb8n67::before { animation: ... }`（落地页→React 接力无缝）
   - `@keyframes` 名带项目前缀（如 `eavesRainNear`），禁止 `particleFall` 类通用名（防与未来样式冲突）
   - **无缝循环**：`background-repeat` 平铺下，纵向循环位移必须是 2560px 整数倍，横向必须回零或为 1440px 整数倍
   - 文件头部注释写推导句（意象→语义→参数依据），写不出=没推导，回炉
5. **验收**：两帧截图对比（间隔 ≥2s）粒子位置必须可辨变化；`index.html` 与 `userStyleSheet.css` 均无 `__FX_CSS__` 残留。

**HUD 设计推导（对话框/名牌/选择支——禁止"选预设换色"交差）**：

对话框是玩家全程盯着看的界面，**它不是从 5 套预设里挑一个换主色，而是从 GDD 主题配方推导出来的设计**。预设主题的 textbox.scss 只是结构骨架（缺类不渲染），视觉参数必须按本节逐参数推导并改写，推导依据落进 GDD 主题配方节的「HUD 设计」小节：

| 参数 | 推导依据（从意象出发） | 反例（换色思维） |
|---|---|---|
| 面板材质 | 核心场景的"触感"：木工房=温润实木（低透明实色+柔光）、深夜都市=湿冷玻璃（backdrop-blur+高反光）、纸质档案=哑光纸感（实色+细颗粒） | 所有题材都是"半透明圆角矩形" |
| 形状语言 | 题材气质的几何直译：治愈=大圆角软边、悬疑=锐利小圆角+单边强调线、科幻=切角/细线框 | 全部 44px 圆角 |
| 装饰图形 | **故事世界里真实存在的物件**（木工房刨花、侦探社铆钉）——没有依据的装饰一律 `background-image: none`，禁止挂与题材无关的图案 | 深夜都市挂爪印 SVG（从 anime 预设抄来的残留） |
| 名牌形态 | 与面板同一推导链：实体世界题材=铭牌/标签（矩形+描边）、幻想/治愈=胶囊/气泡；名牌色=主色，字色与面板的对比关系 | 所有题材都是"胶囊浮在框上沿" |
| 正文排版 | 字重/字距随节奏：慢节奏题材字距略松（0.08em+）、字重偏轻；紧张题材字距紧、字重偏沉 | 全局 600 字重 0.06em |
| 旁白弱化 | **必备规则**：无名牌旁白正文视觉弱化（见下），弱化色=正文色 80-85% 不透明度，不分题材 | 旁白与对话毫无区分 |

**旁白弱化与「旁白」标签（结构契约，5 套骨架与所有新主题必备）**：两条规则都放在 **userStyleSheet.css**（全局 CSS），**绝不能写进模板 scss**——见下方「模板 scss 选择器铁律」：

```css
/* userStyleSheet.css 内（5 套主题已内置） */
/* 1. 正文弱化：作用在文本容器上（子元素打字机 opacity 动画不受影响，容器不透明度与子元素相乘） */
#textBoxMain:not(:has(> :nth-child(3))) > :nth-child(2) {
  opacity: 0.82;
}
/* 2. 「旁白」标签：实底与面板同色，骑缝坐在框边上缘，与角色实心名牌同槽位、略小一号 */
#textBoxMain:not(:has(> :nth-child(3)))::before {
  content: "旁白";
  position: absolute; left: 76px; top: -34px;   /* 与名牌槽位一致（simple 主题 72/-32） */
  height: 68px; line-height: 64px; padding: 0 36px;
  font-size: 40px; letter-spacing: 0.12em;
  color: <主题主色>; border: 2px solid <主题主色>; border-radius: 34px;
  background: <面板同色实底>;                    /* 必须实底！透明底会让框边线穿过标签 */
  pointer-events: none; z-index: 3;
}
```

**旁白判定用 DOM 结构，禁止用类名**：旁白行 `#textBoxMain` 恰好 2 个直接子节点（miniAvatar + 文本容器），对话行 4 个（多 2 个名牌 div），`:not(:has(> :nth-child(3)))` 精确区分。**名牌 div 和文字 span 都是 emotion 随机类名**（`css-n0ia3h` 这类），`[class*="TextBox_showName"]` / `[class*="outer"]` 匹配不到任何东西——v8.1 曾因此标签与名牌重叠、弱化静默失效（教训：写完全局 CSS 必须 E2E 截图验证两种行各一张，不能只看一种）。`#textBoxMain` 是引擎固定 id，唯一稳定锚点。标签**不许透明底**（框边线会穿过去）也不许与角色名牌同质感（实心 vs 实心分不清层级）——实底取面板同色、尺寸略小、细边，层级一眼可辨。只调不透明度与标签、**不动 padding/字号**（旁白与对话交替出现，布局差会造成文本框跳动）。GDD「叙事视角与名牌约定」为「刻意匿名主角」的项目，全剧本都是旁白，此规则视觉上等同全文弱化——仍要保留（一致性与未来剧本改动安全）。

**模板 scss 选择器铁律（血泪教训）**：引擎对 textbox/choose/title 三个模板 scss **不做真 Sass 编译**，是正则平铺解析（`\.([^{\s]+)\s*{…}` 抓类名→内联样式表）。因此：

- 只写**单层 `.类名 {…}`** 平铺规则和 `@` 规则；块内嵌套（如 `.Title_button { &:not(:first-child){…} }`）是引擎兼容写法，可以用
- **禁止独立的复合/伪类/后代选择器规则**（如 `.A:not(:has(.B)) .C {…}`、`.A .B {…}`、`.A:hover {…}`）：解析器会把 `.A… .C {…}` 误读成 `.C {…}`，**静默覆盖同名真规则**——旁白弱化规则写进 textbox.scss 时就把 `.outer` 的颜色/定位整个抹掉，正文全部消失
- 需要结构选择能力（`:has`/后代/伪类）的需求，一律去 userStyleSheet.css 用哈希前缀 substring 匹配实现

**选择支**同属 HUD：形态（卡片/按钮/列表）与材质随面板推导链走，结构类契约不变（见下）。

**项目级 HUD 改写（装配后必做）**：`apply_theme` 只铺骨架主题的默认参数，**装配完成后必须按 GDD「HUD 设计」节改写项目级参数**——直接改 `build/game/template/Stage/TextBox/textbox.scss`、`Stage/Choose/choose.scss`、`UI/Title/title.scss` 与 `build/game/userStyleSheet.css` 里的视觉值（面板色/描边/名牌渐变/旁白标签色/body 底色），让 HUD 跟着本项目的角色图与主题配方走，而不是全员骨架默认色。同 IP 双版本也要对仗拉开（第三小时：自由版琥珀霓虹 vs 孤独版冷青钢色——后者即装配后项目级改写：面板 `rgba(13,20,29,.85)` + 冷青 `#7FB3C8` 顶边与名牌渐变 `#3D5A6B→#5A8299` + 标签/底色同步）。注意 `assemble_build.sh` 会 `rm -rf build` 重建——**重新装配后项目级改写必须重放**（改写清单建议随 GDD「HUD 设计」节落档成参数表，重放照抄）。

2. **apply_theme.sh 流程**：拷 template.json + textbox/choose/title 三个 SCSS + userStyleSheet.css → **校验 `game/background/title_particles.png` 存在**（tile 是项目主题素材，agent 推导后用 gen_particles.py 自由参数绘制 / gen_image.py 生成 / 自行创作，缺失即报错）→ **注入 effects.css**（项目根优先，主题目录骨架兜底，写入落地页 index.html 与 userStyleSheet.css 的 `/*__FX_CSS__*/` 占位符）→ 注入 sheen/kenburns/fallback/点击闪色推导参数（`__SHEEN_*`/`__KB_*` 等，任一残留即报错退出）
3. **粒子 tile**：`scripts/gen_particles.py --type petals|rain|motes|snow|fog --color <hex> --count <n>` 是快速出基础 tile 的**工具**（形状库，非动效菜单），也鼓励按主题自由创作或 AI 出图——tile 承担"形状与质感"，effects.css 承担"运动行为"，两者都由项目主题决定
4. **新主题骨架铁律**：**必须以 anime 主题的完整 SCSS 为骨架、只改视觉参数，禁止从零写**——缺结构类会导致整个组件不渲染。而且**选择器写法也要逐字对齐**（嵌套/独立写法在引擎模板编译下行为不同：`:not(:first-child)` 必须写成 `.Title_button` 块内的 `&:not(:first-child)`，独立复合选择器会静默失效，菜单按钮全漏出来）。必备结构类与行为属性清单：
   - `textbox.scss`：`.TextBox_main` / `.TextBox_main_miniavatarOff` / `.TextBox_Background` / `.TextBox_showName` / `.TextBox_ShowName_Background` / `.outer` / `.inner` / `.outerName` / `.innerName` / `.miniAvatarContainer{display:none}` / `.miniAvatarImg{display:none}` / `.TextBox_textElement_start`（打字机显影动画，缺了正文永不显示）/ `.TextBox_textElement_Settled` / `@keyframes TextDelayShow` / `@keyframes showSoftly`（旁白弱化规则不在此文件——它必须用 `:has()`，放 userStyleSheet.css，见「HUD 设计推导」节）
   - `choose.scss`：`.Choose_Main`（z-index:13）/ `.Choose_item_outer` / `.Choose_item`（**必须带 font-family、font-size:220% 以上、`cursor: pointer`**——缺字号=文字小到不可见，缺 cursor=E2E 检测失效+用户无手型）/ `.Choose_item_disabled`（`cursor: not-allowed`）
   - `title.scss`：`.Title_main` / `.Title_buttonList`（结构照抄 anime：absolute 定位+padding 620px）/ `.Title_button`（`&:not(:first-child){display:none}` 嵌套在块内！+ `cursor: pointer`）/ `.Title_button:hover` / `.Title_button_text` / `.Title_button_text_outer{display:none}` / `.Title_button_text_inner{display:none}` / `.Title_backup_background` / `.Title_button_disabled`
5. 封面：标题与底图统一由生图模型直出（文字描边色取 `cover.stroke` 色系），底图氛围按 `cover.prompt_mood` 写 prompt（见 art-director.md 第 6 节），禁止所有题材千篇一律同一色调

## 必做补丁（每个游戏都要，缺一个就会被玩家看出来）

### 1. 默认中文，跳过语言选择页

引擎首发进语言选择页，视觉小说不需要。在 `build/index.html` `<head>` 任意 `<script>` 前插入：

```html
<script>
  // 默认简体中文，跳过语言选择
  if (!localStorage.getItem('lang')) { localStorage.setItem('lang', '0'); }
</script>
```

### 2. config.txt 关闭多余功能入口

标题页引擎默认带「继续游戏 / CG鉴赏」等按钮，视觉小说只留开始游戏：

```
Enable_Continue:false;
Enable_Appreciation:false;
```

### 3. 标题页四件套（opening 必须是一张"完整的设计素材"）

1. **封面排版**：封面图生产流程见 art-director.md 第 6 节（标题与底图由生图模型一次直出 → VLM 文字校对 → 修水印/锚点色 → 瘦身入库；文字连错 3 次降级 `bake_title.py` 后期排版）。禁止只放一张裸背景图加一行文字
2. **单按钮居中**：皮肤 `template/UI/Title/title.scss` 已内置：`.Title_button { &:not(:first-child) { display: none; } }`（只留「开始游戏」）+ `.Title_buttonList { justify-content: center; padding-top: 620px; }`（按钮落在画面 62% 处，避开角色主体）。定制皮肤变体时这两条随 sed 复制保留，不要删
3. **动态封面**（首屏第一帧就是动态封面，无黑屏加载期）。机制分两层接力：
   - **落地页层**（引擎 `index.html` 内联样式，已内置）：`.html-body__title-enter` 的背景设为封面图 + 三层动画（Ken Burns 推拉、`titleSheen` 光晕、粒子动效——时长与行为均由主题配方/effects.css 注入，引擎零预置）。它不等 React bundle，首屏立即可见
   - **React 封面层**（皮肤 `userStyleSheet.css`，已内置）：`.css-kb8n67` 挂同参数三层动画。React 加载完成后，`index.html` 内联的接力脚本（MutationObserver 监听 `.title__enter-game-target` 出现）把落地页淡出 `display:none`，React 封面无缝接管
   - 配套：`<link rel="preload">` 预载封面图与花瓣 tile；落地页尺寸必须是竖屏 `1440×2560`（引擎原装 2560×1440 横屏尺寸经 transform 缩放后**错位**，会在右上角露出残留色块）；落地页的 "PRESS THE SCREEN TO START" 文字与引擎链接已隐藏（封面自排标题）
   - 粒子 tile：项目主题素材（`game/background/title_particles.png`），由 agent 按主题推导后提供（`scripts/gen_particles.py` 自由参数绘制 / gen_image.py 生成 / 自行创作），apply_theme 只校验存在、不代生成
   - **教训（勿犯）**：`.title__enter-game-target` 是一个高度为 0 的"点击进入"幽灵热区，**不是背景层**——动画挂在它上面完全无效；真正的 React 封面层是 emotion 类 `.css-kb8n67`（dist 冻结期间稳定；若重新构建引擎，类名会变，需同步更新皮肤 CSS）
   - **引擎自动 enter 不可靠**：WebGAL 的自动进场 click 分发目标（React 热区）与落地页（独立 DOM）非父子，事件冒泡不到，落地页永不退场——必须由接力脚本处理，禁止用 `display:none` 粗暴隐藏落地页（那样会丢掉首屏封面，回到黑屏加载期）

### 4. 皮肤 userStyleSheet.css 内置规则（勿删）

| 规则 | 原因 |
|---|---|
| 规则 | 原因 |
|---|---|
| `[class*="_singleButton_"] { display:none }` | 隐藏底部控制条——视觉小说不需要引擎功能按钮，分支回溯由剧本承担（见 scriptwriter.md） |
| React 封面层三层动画 | 见上文「标题页四件套」第 3 条（落地页层在引擎 index.html 内联，不在本文件） |
| 旁白弱化 + 「旁白」标签（`#textBoxMain:not(:has(> :nth-child(3)))` 两条） | 无名牌旁白：正文弱化 + 名牌槽位补实底「旁白」标识（见「HUD 设计推导」节） |
| `div:has(+ #textBoxMain) { opacity:1 }` | 对话框底板不透明度锁定，压过引擎用户档位 |
| `body { background-color }` | 舞台外压深色 |

### 5. 已知瞬态与噪音（QA 判读标准，勿当 bug 返工）

- **返回标题页封面瞬态**：结局 `end;` 回到标题页时 React 封面层 remount，封面图解码期间会短暂露出 `.Title_backup_background`（约 0.5-1.5s）。缓解已内置：封面统一瘦身到 1440 宽 progressive JPEG（`bake_title.py --shrink-only`，见 art-director.md 第 6 节），且主题 `title.scss` 的备份背景渐变必须与封面暗部色调一致（midnight=#2A2E3C 深夜蓝、anime=#FFF0F3 浅粉——新主题照此配套）。QA 时截图要在返回标题后**停留 2s 再判**，瞬态残留不算缺陷
- **404 噪音白名单**：`/api/webgalsync` WebSocket（引擎联机同步功能，单机版必现）属无害噪音。SourceHanSerif 字体与 Live2D SDK 的 404 已在引擎层移除/改为按需加载，若再出现说明引擎 dist 被替换过

注意：模板 SCSS 不是真编译，是引擎正则平铺解析（复合选择器会被误读，铁律见「HUD 设计推导」节），解析结果按类名查表打成内联样式——所以改模板元素外观（标题按钮、对话框、选择支的面板/字号/颜色）改 `game/template/*.scss`；而**结构性选中**（`:has()`、后代、伪类）只能在 userStyleSheet.css 里用哈希前缀 substring 匹配（模板组件 DOM 保留 `_组件名_哈希` 类名，前缀稳定可读）。全局层（舞台外、启动层、控制条）也用 userStyleSheet.css。

## 检查点（QA 前自检）

- [ ] 打开站点直达动态封面（首屏无黑屏、无粉屏加载页、无语言选择页）
- [ ] 封面加载完成后落地页自动淡出消失，**标题页与游戏内无任何残留色块**（重点检查右上角）
- [ ] 标题页是一张"完整设计素材"：封面构图留白得当、游戏名像游戏名（2-6 字钩子）、英文副标+tagline 排版在位
- [ ] 「开始游戏」单按钮位于画面中轴（约 62% 处），不压角色主体
- [ ] 动态封面三层动画可感知：背景推拉、光晕扫过（如启用）、粒子按项目 effects.css 动效运动（落地页与 React 层接力，全程动画不中断）
- [ ] 粒子意象/动效/配色、HUD 材质、封面氛围与 GDD 主题配方一致（悬疑≠花瓣暖粉），effects.css 头部有推导句；**对话框无与题材无关的装饰图形**（装饰=无推导残留，回炉）
- [ ] 名牌约定落地：角色（含主角）说出口的话带名牌、名字与 GDD 主角名牌名一致；无名牌旁白带**实底「旁白」标签**（与面板同色、略小于角色名牌，框边线不穿过标签）且正文可辨弱化，旁白/对话交替时文本框无跳动；**对话行不得出现「旁白」标签与角色名牌重叠**（若出现=选择器误用类名匹配，回炉按 HUD 节的 DOM 结构判重写）
- [ ] 游戏内底部无控制条按钮
- [ ] 场景切换有淡入转场，且**立绘先退场再换景**；立绘换装不生硬（剧本参数，见 scriptwriter.md 演出与转场）
- [ ] 情绪节拍处立绘差分有对应反应（训斥→得意、被抓包→惊讶等），非一张 normal 挂到底
