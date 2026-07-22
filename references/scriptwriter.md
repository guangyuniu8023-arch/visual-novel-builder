# SCRIPT：剧本生成（WebGAL 脚本）

产出：`game/scene/` 下的 WebGAL 剧本文件。写完后**必须**跑 `scripts/validate_script.py`，零错误才算完。

## WebGAL 脚本速查

```
角色名:对话内容;                    # 带名牌的对话
:旁白内容;                          # 无名牌旁白
changeBg:xxx.webp -next;            # 换背景（-next 立即执行下一句）
changeFigure:xxx.png -center -next; # 立绘上屏（本引擎统一 -center 近景；-left/-right 语法不报错但渲染归中，禁止用于同屏双人）
changeFigure:none -center -next;    # 立绘下屏
bgm:xxx.mp3 -enter=3000;            # BGM
choose:选项文字:标签|选项2:标签2;    # 选择支（目标为同文件 label）
choose:(cond)->文字:标签|文字2:标签2; # 带显示条件的选项
setVar:affection=affection+10;      # 变量运算
label:xxx;  jumpLabel:xxx;          # 标签与跳转
jumpLabel:xxx -when=affection>=15;  # 条件跳转（不满足则继续顺序执行）
changeScene:chapter2.txt;           # 切换场景文件
callScene:xxx.txt;                  # 调用子场景（返回）
end;                                # 场景结束（必需）
; 注释内容                            # 注释：分号开头（WebGAL 没有 // 注释，写 // 会被当对话显示！）
```

**注意**：WebGAL 的注释是**分号开头**（`;` 后的内容即注释）。`//` 开头的行会被当作普通对话显示在屏幕上，严禁使用。

## 视觉节拍契约（先做分镜状态，再写台词）

图文对应不是 QA 阶段猜出来的，而是 SCRIPT 阶段的必备输入。写任何 `scene/*.txt` 前，先创建项目根的 `visual_plan.json`。它同时是编剧的视觉状态机、ASSETS 的生图清单和 `validate_visual_plan.py` 的校验依据。

### 哪些句子必须成为视觉节拍

只要玩家能合理期待画面发生变化，就必须建 beat，不能只写在旁白里：

- **环境状态**：每章首个地点建立，以及熄灯/亮灯、断电、警报变色、昼夜切换、天气变化、门开启、空间损毁；每条 `changeBg` 都必须属于一个 beat
- **人物空间状态**：进场、退场、转身、背影、离开、奔跑、躲藏；从无立绘到有立绘、从有立绘到 `none` 都必须属于 beat，尤其是“通讯里只剩声音”“没有回头”“再也没有回来”
- **具体肢体动作**：伸手、递物、握手、拥抱、跪下、按住伤口、拉到身后、抛出物品
- **关键道具状态**：道具出现/消失/损坏/被放到桌上、屏幕投影或终端内容改变

每个 beat 使用以下结构：

```json
{
  "version": 3,
  "visual_policy": {
    "min_pose_hold_lines": 3,
    "max_pose_changes_per_100_lines": 12,
    "max_visual_changes_per_100_lines": 24,
    "max_cg_per_scene": 2,
    "max_action_beats_per_scene": 2,
    "max_background_beats_per_scene": 4,
    "max_text_lead_transition_ms": 220
  },
  "figure_catalog": {
    "qilin_guarded.png": {
      "role": "dialogue_pose",
      "framing": "thigh_up",
      "pose": "微侧身抱臂，肩线收紧",
      "expression": "警惕",
      "gesture": "arms_crossed",
      "props": [],
      "usage_tags": ["guarded", "questioning"]
    },
    "qilin_act_offer_ring.png": {
      "role": "action",
      "framing": "thigh_up",
      "pose": "站立，右手向镜头递出脉冲环",
      "expression": "温柔",
      "action": "offer_ring",
      "props": ["pulse_ring"],
      "allowed_beat_ids": ["c1_offer_ring"]
    }
  },
  "beats": [
    {
      "id": "c2_blackout",
      "scene": "chapter2.txt",
      "lead_text": "蜂鸣声短促地断了一拍。",
      "text": "所有屏幕沉入黑暗，只剩地面的应急条。",
      "mode": "background",
      "asset": "bg_command_blackout.webp",
      "timing": "text_leads",
      "character_state": "onstage",
      "description": "指挥室断电，全部屏幕黑掉"
    },
    {
      "id": "c6_radio_only",
      "scene": "chapter3.txt",
      "text": "通讯里只剩风穿过隧道的声音。",
      "mode": "offstage",
      "timing": "text_leads",
      "lead_text": "他的脚步越过拐角。",
      "character_state": "offstage",
      "description": "祁凛已离开画面，只保留通讯声音"
    }
  ]
}
```

`mode` 只允许：

| mode | 用途 | 文字前必须出现 |
|---|---|---|
| `background` | 灯光、天气、空间状态变体 | `changeBg:<asset>` |
| `figure` | 专用动作立绘或姿态变化 | `changeFigure:<asset>` |
| `cg` | 双人接触、复杂动作、关键构图 | `changeFigure:none` 后 `changeBg:<asset>` |
| `offstage` | 角色离场、远程通讯、只剩声音 | `changeFigure:none` |
| `text_only` | 纯声音、气味、内心等无法直接拍到的内容 | `reason` 说明；不得用于可见动作或环境变化 |

### WebGAL 中的标注与顺序：文字先解释，画面再承接

每个 beat 在剧本中用 WebGAL 注释绑定。只有章节第一张地点建立图可用 `timing=establish` 直接先上画面；其他视觉变化一律使用三段式：

1. `lead_text` 先告诉玩家发生了什么或什么即将改变
2. `@visual` 后执行不超过 `max_text_lead_transition_ms` 的短转场
3. `text` 承接新画面，让图片至少被一行可见文字解释和停留

```text
:蜂鸣声短促地断了一拍。;
; @visual:c2_blackout
changeBg:bg_command_blackout.webp -enter=enter -enterDuration=180;
:所有屏幕沉入黑暗，只剩地面的应急条。;

:他的脚步越过拐角。;
; @visual:c6_radio_only
changeFigure:none -center -exit=exit -exitDuration=160;
:通讯里只剩风穿过隧道的声音。;
```

这样图片不会无解释地抢在文字前出现，也不会在一张陌生画面上等待长转场和打字机。`lead_text` 与 `text` 都要写入 visual plan；一个 beat 绑定注释前最近的一句 lead text 与注释后第一句承接文本，ID 全项目唯一。场景建立镜头使用 `timing=establish`，不写 `lead_text`。

普通对话姿态不必全部写成高风险 beat。每次切换 `dialogue_pose` 都必须用 `@pose` 声明语义，但切换应发生在一条已经可见的刺激/反应文字之后，再由新姿态承接后续台词；标签必须属于该立绘的 `usage_tags`：

```text
:你把终端推到他面前。;
; @pose:questioning
changeFigure:qilin_guarded.png -center -enter=enter -enterDuration=150;
祁凛:你接了什么？;
```

`@pose` 解决“上一句刺激为什么让身体语言改变”；`@visual` 解决“画面状态或剧情动作发生了什么”。人物首次进场时两者可以同时出现。普通姿态切换后至少持有 `min_pose_hold_lines` 行可见文本；没有持续意义就保持当前姿态。

### 视觉克制预算（强制）

- 每个核心角色默认 4-6 张 dialogue pose，不因每句情绪词新增一张图
- 每章默认 action≤2、CG≤2、background beats≤4
- dialogue pose 平均每 100 行最多切 12 次；所有背景、进退场、CG、动作与姿态合计每 100 行最多切 24 次
- 两个环境状态若只各停留一句（例如“先黑一下、马上红灯”），合并成一个有叙事意义的最终状态，用 lead text 交代中间过程
- 选择反馈首先由选项后的台词、停顿和数值变化承担；只有身体语言会稳定影响后续至少 3 行时才切 pose
- 一张 CG 必须承担不可由现有背景+立绘清楚表达的空间关系；“更好看”不是增加 CG 的理由

### 连续性状态机

逐章维护四项当前状态：`location/background_state`、`visible_character`、`pose/action`、`prop_state`。每次写 beat 前先读取上一个 beat 的结束状态：

1. 文本说角色离场/只在通讯中出现 → 先用可见 lead text 说明离开，再短转场 `changeFigure:none`；后续不得再切正面表情，除非有明确重新进场的 lead text 和新 beat
2. 文本说背影/转身离开/迈步/奔跑 → 用 CG 或改为明确画外发生并先退场；这些动作需要腿脚或完整身体轮廓，禁止生成会拉远镜头的全身 action 立绘，也禁止用正面 idle 立绘代替
3. 文本说熄灯/红光/天亮 → 使用背景状态变体或 CG；但只闪过一行的中间状态不单独生图，用 lead text 交代、最终状态承接
4. 双人手部接触、拥抱、止血、递物等空间关系明确的动作，优先 CG；若用动作立绘，必须在 `figure_catalog` 中写明动作、道具与唯一允许的 beat
5. 剧情动作结束后必须显式切到与下一句语义匹配的 `dialogue_pose` 或退场；动作立绘不能“挂”进后续普通对话
6. 每条 `changeBg`、每次人物进场/退场都必须处于某个 `; @visual:<id>` 到目标文本之间；普通 `dialogue_pose` 切换用 `; @pose:<usage_tag>` 绑定文本语义。角色一旦进入 offstage 状态，重新显示立绘必须有明确“回到画面”的新 beat

完成 `visual_plan.json` 与场景脚本后，SCRIPT Gate 必须同时运行：

```bash
python3 scripts/validate_script.py projects/<id>/game/scene --min-endings <GDD结局数>
python3 scripts/validate_visual_plan.py projects/<id>/visual_plan.json projects/<id>/game/scene
```

## 叙事人称与名牌约定（按 GDD 同名字段执行）

引擎对 `角色名:内容;` 渲染名牌，对 `:内容;` 不渲染名牌（HUD 会用弱化样式区分，见 build.md「HUD 设计推导」）。三种文本的写法是**硬性分工**，混用会让玩家分不清"谁在说话"：

| 文本类型 | 写法 | 名牌 | 判据 |
|---|---|---|---|
| 角色（含主角）**说出口的话** | `名字:内容;` | 有 | 能用引号括起来、被对方听见的话 |
| 客观叙述（场景/动作/他人神态） | `:内容;` | 无（HUD 显示「旁白」幽灵标签） | 摄像机拍得到的东西 |
| 主角内心独白 | `:内容;`（第一/二人称叙述句） | 无（HUD 显示「旁白」幽灵标签） | 只有主角自己"听"得到 |

规则：

- **主角说出口的话必须带名牌**（名字取 GDD「叙事视角与名牌约定」的主角名牌名），禁止写成 `:你开口道歉。;` 这种"无名牌台词"——玩家会分不清这是旁白还是对话。只有 GDD 明确「刻意匿名主角」时，主角台词才允许并入旁白
- 内心独白与客观叙述都是无名牌旁白，靠**人称与语感**区分（独白带情绪与自我指涉："该死的，又搞砸了"；叙述是中性白描），HUD 弱化样式对两者一致
- 名牌名保持全剧本一致：同一角色的名牌字符串逐字相同（"顾樵"与"顾樵（小声）"是两个名牌——情绪注记写进立绘差分和台词文本，不写进名牌）

## 分支数值系统（题材决定变量，GDD 里定死）

选择不是装饰——**每个选择都要改变隐藏数值，数值决定结局**。

**通用设计法（任何题材按这五步推导，不要硬套下表）**：

1. **提炼核心张力**：这个题材"玩家在乎什么"？恋爱=关系亲密度、悬疑=离真相多近、竞技=胜负与成长、职场=能力与立场、治愈=心绪修复度——张力就是数值要追踪的东西
2. **选 1-2 个追踪变量**：不超过 2 个（多了剧本写不动、账本算不清）。双变量只用于"两条评价轴"的题材（如悬疑的信任×线索）
3. **定分值幅度**：普通选项 ±2~5，关键分歧 ±10；善意/契合角色的选项为正，冒犯/逃避为负
4. **反推阈值**：先算"全选最优"与"全选最差"总分，再把结局阈值切在中间——HE ≈ 满分的 60-70%，NE ≈ 30-40%，其余落 BE，写进 script_outline.md 数值账本
5. **选项排序约定（血泪教训）**：每个选择支的选项**必须按分值从高到低书写**（最优在第一项，最差在末项）。QA 的 E2E 策略是"first=全选第一项 / last=全选末项"——排序乱了，策略点击的路线就不是你以为的路线（本次实测：最优项写在末位，last 路线拿到最高分，双结局验证作废）。写完后按 script_outline.md 数值账本复核一遍"first 路线总分 / last 路线总分"是否与设计一致
6. **检验可达性**：每个结局都必须存在一条选项组合能走到（QA 阶段 E2E first/last 双路线实证，且两路线必须到达**不同**结局）

现成示例（仅作参考，不是白名单）：

| 题材 | 建议变量 | 含义 |
|---|---|---|
| 恋爱 | `affection` | 好感度 |
| 悬疑/推理 | `trust` + `clues` | 关键角色信任度 + 收集线索数 |
| 冒险 | `courage` | 勇气/羁绊 |
| 竞技/成长 | `progress` (+ `mindset`) | 实力精进（+ 心态） |

**多角色时的数值模式（GDD 按题材二选一，定死）**：

- **主线模式**（默认）：1 主角 + 配角群。变量只追主线（如 `affection`=玩家×主角），配角不攻略、不设独立变量，配角的作用是演出与剧情推力。结局判定与单角色无异
- **多攻略模式**：2-3 个可攻略角色，每角色一个独立变量（`trust_a` / `trust_b`，变量名带角色后缀）。每个选项只影响**在场角色**的变量。结局判定用组合：HE=最高变量达阈值且明显领先、各单人结局=对应角色达阈值、BE=全员低于阈值；判定分支仍从高到低排列，同分时取剧本 C 位角色
- 禁止"配角有好感度但不影响结局"的假变量——不设数值就不追踪

**单结局模式的数值意义**：用户明确要单结局时，数值不决定结局走向，改决定**结局呈现版本**（如：达阈值=完整版尾声+特殊 CG，未达=普通版尾声）。两版本同一结局走向，差在情感浓度与 CG 解锁——选择依然有意义，但承诺的"单结局"不能破。

**复合条件**：多攻略模式的组合判定用 `&&` / `||`（引擎表达式语法，单写 `&` 不报错但行为异常）：
```
jumpLabel:ending_he -when=trust_s>=11&&trust_q>=9;
jumpLabel:ending_s -when=trust_s>=11;
jumpLabel:ending_q -when=trust_q>=9;
jumpLabel:ending_be;
```

结构规范（强制）：

1. 开局 `setVar:<变量>=0;`（多变量各自初始化）
2. 每个 `choose` 的选项给 ±5~15 数值，**选项后必须 `jumpLabel` 收束回主线**（禁止无限分叉）
3. 场景组织：`start.txt`（共通线）→ 按章 `chapter2.txt`… → `ending.txt`（结局判定）
4. `ending.txt` 用条件跳转判定结局，**结局分支按阈值从高到低排列**：

```
label:judge;
jumpLabel:ending_good -when=affection>=30;
jumpLabel:ending_normal -when=affection>=10;
jumpLabel:ending_bad;                ; 兜底分支不设条件
```

5. 每个结局以 `end;` 收尾；结局文案要点题且风格贴题材（悬疑的 BE 是真相永远石沉大海，不是失恋）

## 演出与转场（强制，否则场景衔接生硬）

`changeBg` / `changeFigure` 支持四个演出参数（引擎原生）：`-enter=<动画名>`、`-exit=<动画名>`、`-enterDuration=<ms>`、`-exitDuration=<ms>`。**每一条换背景/上下立绘的语句都必须带**，否则画面瞬切、衔接生硬。动画名来自 `game/animation/*.json`，常用：

| 场景 | 写法 |
|---|---|
| 章节开场背景 | `changeBg:bg_xxx.jpg -enter=enter -enterDuration=500;` |
| 文字已引导的背景状态 | `changeBg:bg_xxx.jpg -enter=enter -enterDuration=180;` |
| 文字已引导的 CG | `changeBg:cg_xxx.jpg -enter=enter -enterDuration=200;` |
| 立绘首次进场 | `changeFigure:x.png -center -enter=enter -enterDuration=500;` |
| 文字已引导的姿态切换 | `changeFigure:x_angry.png -center -enter=enter -enterDuration=150;` |
| 文字已引导的退场 | `changeFigure:none -center -exit=exit -exitDuration=160;` |

规则（四条铁律）：

1. **章节建立镜头可用 500ms 淡入**。不要用 `enter-from-bottom`——从底部升起的中间帧会让玩家先看到头发/头顶，像"无脸立绘"
2. **非开场变化必须先有 lead text，随后 220ms 内完成**。长达 300-1500ms 的转场会让图片先出现而文字迟到
3. **换背景前必须先把立绘退场**，但同一 beat 的退场与换景都用短转场；否则角色会一直"贴"在新场景上
4. **每个场景文件开头必须先清场**：文件首条 `changeBg` 之前写 `changeFigure:none -center -exit=exit -exitDuration=400;`。WebGAL 的 `changeScene` **不会自动清空立绘**——上一场结尾的角色会原样挂进新场景，没有退场没有变化，像"穿越贴片"。清场后新场景从纯背景+旁白开场，角色该登场时再 `enter` 淡入
5. 时长按叙事时机区分：章节建立 500ms；文字已引导的背景/CG 180-220ms；姿态 120-160ms；退场 160-200ms

## 身体语言姿态：少切、长持有（强制）

立绘不是逐句插图。姿态表达一段持续的关系状态，先由文字给出刺激，再切一次并稳定承接后续：

- **禁止每个 choose 分支机械换立绘。** 玩家选择的即时反馈由台词、停顿、数值与已有姿态承担；只有变化会持续影响至少 3 行可见文本时才切
- 姿态切换前必须已有可见刺激文本，例如玩家质问、警报响起或角色看见伤口；图片不能先于原因出现
- 同一张姿态至少持有 3 行；不得 `惊讶→温柔→担心` 每句连切，也不得重复切入当前同一张图
- 一个章节通常只需要“建立姿态→核心冲突姿态→收束姿态”2-4 次切换
- **对话差分必须同时变化表情与身体语言**：警惕可抱臂/微侧身，命令可挺直并做开放手势，担心可前倾并手扶胸口，害羞可移开视线并收拢肩线。不得只换眉眼嘴形，也不要求不同差分保持相同手部姿势
- 对话姿态的边界是“不产生新的剧情事实”：可以抱臂、叉腰、插兜、轻微前倾、扶额、手扶胸口；不能递出剧情道具、触碰另一角色、跪地止血、转身离场或奔跑
- 每张对话姿态登记为 `dialogue_pose`，必须写 `gesture` 与 1-3 个 `usage_tags`；剧本切换时用 `; @pose:<tag>` 说明为什么它匹配当前台词
- 任何带道具或明确肢体动作的图都属于 `action`，命名为 `<角色>_act_<动作>.png`，并在 `figure_catalog.allowed_beat_ids` 中限定用途；action 也只能是 `framing: thigh_up`，需要腿脚/步态/全身轮廓则改用 CG/offstage；禁止把 `offer_ring` 当作所有 smile/soft 场景的通用差分
- 基础对话姿态默认 4-6 张，姿态轮廓应明显不同且能长期持有；剧情动作按 `visual_plan.json` 另行生成，不占差分名额
- 差分资产不存在时，**先回 ASSETS 阶段补生成，禁止用 normal 硬扛情绪戏**
- `validate_visual_plan.py` 会检查最短持有行数、切图密度与动作/CG预算；超预算先删切换，不先加图

## 多角色同场演出（竖屏单人切换制，强制）

本引擎 `-left` / `-right` 站位**语法不报错但渲染全部归中**——同屏双立绘不可用，后一条立绘会盖掉前一条。多角色对话必须用「谁说话谁在场」的单人切换：

1. **先退后进**：B 开口前，A 先退场（`-exit=exit -exitDuration=400`）再 B 进场（`-enter=enter -enterDuration=500`）。严禁两条带图 changeFigure 连写，视觉上就是瞬移换头
2. **反应镜头**：只在关系转折点切 B 的反应，先显示 A 的关键台词，再短切 B，并让镜头稳定承接至少 3 行；普通问答不切
3. **快节奏靠短句与停顿，不靠高频换图。** 争执场景也受总切图密度约束
4. 三人同场对话：仍逐人切换，禁止尝试任何"同屏"写法
5. 选项分支不强制换图；确有持续反应时，由受影响角色承担并遵守持有预算

## 分支回溯（关键分歧点必须提供）

WebGAL **没有 Ren'Py 式的原生 rollback**。「回退到上一个分支」用剧本级模式实现：**在重伤负向分支（减分最多的选项）末尾，给玩家一次重新选择的机会**。

```
setVar:c5_retried=0;                          ; 分歧点前：初始化回溯标记（只定义一次，label 之前）
label:c5_choice;
choose:当面找她道谢:c5_thank|装作不知道:c5_pretend|调侃她:c5_tease;
...
label:c5_tease;
setVar:affection=affection-5;
白霁:……下次别想再有。;
:（她的背影僵住了。你意识到这句话说重了。）   ; 给玩家情绪提示：这是个坏选择
choose:(c5_retried==0)->（叫住她，重新来过）:c5_retry|就这样继续:c5_after;
label:c5_retry;
setVar:c5_retried=1;                          ; 标记已回溯——条件选项随即消失，防死循环/防刷分
setVar:affection=affection+5;                 ; 回滚刚才的数值变动（数额必须与该分支扣分一致）
:你深吸一口气，在她离开之前叫住了她。;
jumpLabel:c5_choice;                          ; 跳回分歧点 label，重新面对同一组选项
```

四条铁律：

1. **数值回滚**：retry 分支必须把该分支的 ± 分加回去，否则数值账本失真
2. **防死循环**：用 `(retried==0)` 条件选项 + retry 内 `setVar:retried=1`，保证回溯只能用一次。没有这条，自动测试和最差路线会无限循环
3. **选项顺序**：回溯选项放 choose 的**第一个**位置（条件不满足时自动消失），「继续」放最后
4. **稀疏使用**：只在重伤分歧点（扣分最多、或情绪最关键的 1-2 处）加，每个分歧点都加会稀释选择重量

## 写作规范

- **第二人称代入**：玩家是「你」，不写玩家姓名性别外貌；玩家台词少而短，多用选项体现玩家意志
- 角色台词必须贴 wiki 角色卡的口癖性格；每句对话 ≤ 60 字，避免大段独白
- 每章 2-4 个选择支点；关键选项前后留情绪停顿（用旁白或省略号）
- 每句对话单独一行；立绘表情差分跟随情绪切换（`changeFigure:xxx_难过.png -center`）

## 长剧本工作法（强制，应对 1-3 万字剧本）

**核心原则：磁盘文件是外部记忆，不靠脑子记。** 绝不一次性写完整部剧本。

1. **先写大纲** `projects/<id>/script_outline.md`：每章一句话剧情 + 选择支点 + 数值变动 + 结局阈值表。给用户过目（轻量确认，不用正式 gate）
2. **再写视觉计划** `projects/<id>/visual_plan.json`：从大纲和 GDD「视觉演出预算」提取所有高风险视觉节拍，先定人物在/离场、动作承载方式和资产语义，再动笔写正文
3. **逐章生成**，每章一个 scene 文件，单章正文控制在 3000-5000 字；每写到具体动作/状态变化，先补 beat 与 `; @visual:<id>`，再写对应命令和文字
4. **每写完一章，立刻追加** `projects/<id>/script_notes.md`：
   ```
   ## 第N章摘要
   - 剧情进展：…
   - 埋下的伏笔（后文必须回收）：…
   - 回收的伏笔：…
   - 数值变动：选项A +10 / 选项B +5 / 选项C -5（本章满收 +15，最低 -5）
   - 角色状态：…（关系进展、约定、信物等）
   ```
5. **写第 N+1 章前必读**：script_outline.md 全文 + visual_plan.json 的上一章结束状态 + script_notes.md 全部摘要 + 上一章结尾 20 行。**不要重读全部已写章节**
6. **数值账本**：script_outline.md 里维护一张表——「全选最优」和「全选最差」两条极端路径到结局章的累计值，确保好结局阈值 ≤ 满收、坏结局阈值 ≥ 最低收、普通结局落在中间。写结局章前必须核算一次
7. **每写完一章就跑两项 SCRIPT 校验**（结构校验 + 视觉计划校验），不要攒到最后

## 结局达成卡（每个结局的仪式感闭环——`end;` 不许静默回标题）

结局不是剧本的终点，是**达成卡的素材**。用户验收原话："结局达成后特别平淡"。成熟做法（Fate 印章卡 / 隐形守护者死亡卡 / 橙光结算弹窗）蒸馏为本节的通用结构，每个结局必须落地：

**GDD 结局三要素（INTAKE 时定死，写进 GDD 结局清单）**：

1. **结局名**：剧情感命名（《雨停之后·晴》），禁止 HE/BE/NE 代号——代号没有记忆点
2. **判词**：一句给这个结局定调的话（出现在卡面下方的对话框旁白里），文案质量直接决定玩家是否愿意收集其他结局（隐形守护者靠判词让玩家主动收集死法）
3. **分镜表**：结算短片的拍摄设计（四步推导，见本节「分镜剧本推导链」；生产流程见 art-director.md 第 8 节）

**卡面标识**：判词与结局名都走剧本旁白（视频模型渲染文字必翻车）——播片结束后先一行**结局名**（如 `:「雨停之后·晴」;`），再一行**判词**，然后出「回到标题」。禁止 `ENDING x/N` 编号——用户验收："02/02 这种很难理解，就叫结局的名字就好"。收集进度的呈现留给未来的图鉴页，不塞进卡面。

**剧本结构（结局判定与卡场景分发）——播片式结算（v9.1 起为标准形态）**：

用户验收："结算动画应该是**不可操控的纯播放内容**，播完出按钮回主页，而不是多一个静态结算画面。"因此达成卡 = **结算 MP4 播片**（引擎 `playVideo` 全屏自动播放，`-skipOff` 禁跳过，播完自动继续剧本），不是可点击的场景：

```
:（终章收尾旁白）;
jumpLabel:card_a -when=peace>=18;   # 与结局判定用同一变量，每个结局一段片
jumpLabel:card_b;
label:card_a;
playVideo:card_a.mp4 -skipOff;      # 全屏播片：分镜视频（Seedance 直出，见 art-director.md 第 8 节）
:（判词，无名牌旁白——视频模型不渲染文字，判词走剧本）;
choose:回到标题:back_a;             # 播完出单按钮引导，卡的收尾动作
label:back_a;
end;
```

**镜头语言分结局方向**（多结局项目必须拉开，写进 GDD）：圆满=推近/转暖转亮（靠近、获得）；坏结局=拉远/降饱和（失去、抽离）；普通结局=平移/低对比（怅然）。镜头运动在**视频合成层**实现（ffmpeg zoompan 推拉/平移），不依赖引擎动画。

**分镜剧本推导链（v10 起，替代固定模板表——分镜是推导出来的，不是模板填出来的）**：

结算片 = 分镜视频（默认视频生成模型直出，见 art-director.md 第 8 节）。分镜剧本从**终章剧本 + 结局清单 + 角色卡**四步推导，禁止套用本节之外的任何固定模板：

1. **定情绪弧线**：读终章最后 5-10 句叙述，提炼结局收束的情绪走向（如释怀版：收"这一夜结束"→转"他放下了"→释"天亮上路"）。**弧线段数 = 镜头数（3-5 个，不超 5）**
2. **节拍映射镜头**：每个节拍 1 个镜头，画面只准从**剧本已有元素**三选一——核心场景（主舞台）/ 信物特写（反复出现的物件，情绪的实体）/ 角色动作（结局句里角色正在做的事）。**禁止发明剧本里没有的场景、物件、动作**——收束感来自"观众刚见过这个"
3. **配运镜与时长**：运镜按结局性质（圆满=推近、普通=平移、坏结局=拉远降饱和），开场镜最缓、顶点镜幅度最大；每镜 3-5s，总时长 15-20s，**时间码写死**（视频模型按时间码切镜）
4. **落分镜表进 GDD 结局清单**（产出格式如下）

**分镜表产出格式**（GDD 结局清单里每结局一张）：

| 镜 | 时间码 | 画面（资产来源） | 运镜 | 情绪节拍 |
|---|---|---|---|---|
| 1 | 0-4s | 深夜木工房（bg_studio_night，剧本主舞台） | 极缓推近 | 收——这一夜结束 |
| 2 | 4-9s | 顾樵捧出未完成木马（角色动作，取自结局句"捧出布包"） | 缓推 | 转——他放下了 |
| 3 | 9-15s | 木马放上窗台、晨光破云（信物特写） | 拉出渐定 | 释——天亮上路 |

**消费链**：分镜表随 GDD 确认 gate 由用户批准 → art-director 按表**组装**视频 prompt（组装规则见 art-director.md 第 8 节，**不靠 agent 自由发挥**）→ QA 抽帧对照分镜表验收；模型跑偏了**改 prompt 不改表**（表是用户批准的设计意图）。

BGM：结算片默认由视频模型 `generate_audio` 生成环境音轨；需指定配乐时用免版税库（授权注明进 GDD 音频节，后续接生成式音乐 API）。

## 自检

```
python3 scripts/validate_script.py projects/<id>/game/scene --min-endings <GDD结局数>
python3 scripts/validate_visual_plan.py projects/<id>/visual_plan.json projects/<id>/game/scene
```

报错必须修到零错误；警告（孤立节点等）逐条确认是否有意为之。
