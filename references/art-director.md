# ASSETS：美术资产生产

按 GDD 的资产清单生成全部图片，登记 `manifest.json`。**剧本校验通过前禁止生图。**

## 1. 资产规格（竖屏引擎，设计坐标 1440×2560）

| 资产 | 画幅 | 数量来源 | 命名（放 game/ 对应目录） |
|---|---|---|---|
| 情绪姿态对话差分 | 2:3 竖版（1024×1536） | `visual_plan.figure_catalog` | `figure/<角色名>_<情绪或语气>.png` |
| 专用动作立绘 | 2:3 竖版（1024×1536） | `visual_plan.figure_catalog` 的 action 项 | `figure/<角色名>_act_<动作>.png` |
| 背景状态变体 | 9:16 竖版（2160×3840 或 1024×1536 竖裁） | `visual_plan.beats` 的 background 项 | `background/<场景>_<状态>.jpg` |
| CG（关键剧情图） | 9:16 竖版 | `visual_plan.beats` 的 cg 项 | `background/cg_<事件>.jpg` |
| 标题主视觉 | 9:16 竖版 | 1 张 | `background/title_main.jpg` |

### 1.1 立绘镜头与占幅契约（硬规则）

`2:3` 只是文件画布比例，不等于人物占屏比例。为避免全身立绘被引擎按高度缩小，所有 `dialogue_pose` 与单人 `action` 立绘必须共享以下镜头，不得因手势或参考图是全身而改变：

- 实际文件必须为 **1024×1536 RGBA PNG**，`visual_plan` 与 `manifest` 都登记 `"framing":"thigh_up"`
- 构图固定为**半身至大腿中部近景**：头顶留白 0%-8%，人物下缘贴近画布底部并在大腿中部出画；膝盖、小腿、脚和鞋不得入镜
- 透明像素包围盒高度占画布 88%-100%，宽度占 60%-92%；人物过窄或四周留白过多必须重生，不得交给 WebGAL 运行时放大补救
- 所有差分锁定同一镜头距离、头部大小、肩宽尺度与下缘裁切；只改变表情、肩线、躯干朝向和画面内双手动作
- 对话姿态描述不得出现 `full-body`、`full body`、`entire figure`、`feet planted`、`stride`、`全身`、`双腿`、`膝盖`、`脚`、`迈步` 等会诱导远景的词
- 若动作必须看见迈步、奔跑、转身离开的全身轮廓，或双人身体关系，使用 9:16 CG；若只需表达离场，先写 lead text，再退立绘并用画外声音承接

每张立绘 prompt 在外貌锚点和本张身体语言之后，**逐字附加同一条构图后缀**：

```text
visual novel character sprite, thigh-up medium close shot, cropped at mid-thigh,
same camera distance and head size as the other sprites, head near the upper frame,
torso and both hands large and readable, no full body, no knees, no lower legs,
no feet or boots visible, no distant shot, plain solid #00FF00 green background,
flat uniform backdrop, no gradient, no shadow, no floor line
```

外貌锚点可以原样提到长裤、枪套或靴子以保持角色身份，但末尾裁切后缀优先级最高，明确这些部位不入镜。模型返回尺寸或占幅不合格时必须重生；禁止把非 2:3 图拉伸成 2:3，也禁止事后把全身图机械放大裁成半身。

对话姿态建议集（核心角色 4-6 张）：常态 normal、命令 command、警惕 guarded、温柔 soft、生气 angry、担心 concerned，按角色题材取舍。**每张都要让身体语言参与表达，也要能稳定承接一小段对话**：抱臂、插兜、前倾、开放手势、移开视线等均可；禁止只换眉眼嘴形，也禁止为一句短反应单独生图。

动作立绘与表情差分是两类资产：

- `dialogue_pose`：可在语义匹配的普通对话中复用，允许表情+姿态+非剧情性手势变化；必须登记 `gesture` 与 `usage_tags`
- `action`：必须写明 `action`、`props`、`allowed_beat_ids`，只允许在对应视觉节拍使用；动作结束后剧本要切到与下一句匹配的 dialogue pose 或退场
- 牵手、拥抱、止血、双人遮挡、复杂道具交互等空间关系难以用单人透明立绘表达的动作，直接用 CG，不生成“看似接近”的通用立绘

分类边界不是“手有没有动”，而是“这张图是否制造剧情事实”：

- 抱臂表示警惕、叉腰表示训斥、轻微前倾表示担心——属于 `dialogue_pose`
- 递出指定信物、单人按住伤口且能在半身镜头说清——可用 `action`；牵住另一人、转身离开、奔跑追赶——使用 CG/offstage

**多角色差分预算**：每个可攻略角色配 4-6 张可长期持有的 dialogue pose；主线配角 3-4 张。每章 action≤2、CG≤2，只有复杂空间关系与真正的叙事锚点才使用。所有角色共用画风、镜头距离和裁切基准，但不得用增加切图频率代替演出判断。

## 2. 生图工具

一律调用：

```
python3 scripts/gen_image.py --prompt "..." --out <路径> [--ratio 2:3|9:16] \
    [--ref <本地角色图>] [--retries 3]
```

立绘必须额外传 `--asset-type figure --ratio 2:3 --chroma-key "#00FF00"`。该模式会在每次下载后检查提示词、1024×1536 尺寸与透明人物占幅；不合格自动进入下一次重试，耗尽重试后 ASSETS 阶段失败。

- provider 由 `tools/providers.yaml` 配置（默认 agent_gw，可换其他兼容端点）；未配置或连续失败 → 转「占位模式」：生成纯色占位图 + 把待生成清单写进 `manifest.json` 的 `pending` 字段，告知用户后流程继续
- `--ref` 会先把本地角色图上传为公网 URL 再作为参考图生成（角色一致性的主要手段）
- `--out` 扩展名即最终格式：写 `x.jpg` 就落 jpg（服务端格式不一致时自动 PIL 转换，jpg 自动去 alpha）
- **限流纪律**：agent_gw 高并发会回 HTTP 424。串行生成，每张间隔 sleep 10-20s；脚本命中 424/429 自动退避 30s+ 重试，不要并行刷

**生图调用规范（每次调用必须产出三样，缺一不可）**：

1. **完整 prompt**：自包含文本——风格词 + 画面描述 +（含角色时）GDD 角色卡外貌锚点原文 +（封面）标题三层文字与排版。禁止"接着上一张改"式的上下文依赖——每条 prompt 必须能脱离会话单独复现这张图
2. **输入图**：`--ref` 参考图路径，或明确标注"无"。判定规则：**构图含角色 → 必须带角色参考图；纯场景/物件 → 不带**（带错参考图会污染场景氛围，不带角色图会生出"像主角的陌生人"）
3. **落档**：`manifest.json` 对应资产条目记 `prompt`（完整文本）与 `ref`（参考图路径或 null）——可复现、可审查、翻车可溯源

## 3. 一致性锚点（强制）

所有含角色的 prompt 必须满足：

1. **正文开头固定插入 GDD 角色卡的「外貌锚点描述」原文**（发色/瞳色/服装/气质），一字不改
2. 带 `--ref` 角色原图
3. 同一角色的 dialogue pose 批量生成只锁定**画风、镜头距离、人物比例和裁切**，不锁定姿势。每张都使用 1.1 节的完整固定构图后缀；prompt 必须逐张写清当前台词语义对应的表情与画面内手势，例如：
   `..., guarded questioning mood, arms crossed, body turned slightly away, tense shoulders, no story prop, no interaction with another character, [固定构图后缀]`
4. dialogue pose 允许抱臂、叉腰、插兜、轻微前倾、扶额、手扶胸口、开放式指令手势；必须写 `no story-specific prop, no touching another character, no locomotion, no scene-changing action`，防止模型擅自生成剧情动作。**严禁再写 `same neutral standing pose` 或 `only facial expression changes`**
5. action 立绘 prompt 必须逐字包含 `visual_plan.figure_catalog` 的 `pose/action/props`，并附 `only for beat <id>` 的用途说明；仍必须是 `thigh_up`。需要腿脚、步态、背影离场或完整身体轮廓的 action 不得生成立绘，回 SCRIPT 改为 CG/offstage

背景/CG prompt 不含角色外貌锚点，但要带题材风格词与 GDD 主色。

## 4. 透明底处理（重要约束）

**生图模型本身不生成透明底。** 立绘按以下顺序处理：

1. prompt 中写 `plain solid #00FF00 green background, flat uniform backdrop`（绿幕法，纯色无渐变）
2. 生成时用 `scripts/gen_image.py` 的 `--chroma-key "#00FF00"` 抠图转透明 PNG；**抠完自动跑 despill 去绿边**（G 显著大于 R/B 的不透明像素把 G 压回 max(R,B)），深色头发/深色衣服角色绿边高发，不再需要手工后处理；`--no-despill` 可关闭
3. `check_assets.py` 会验证立绘 PNG 是否带透明通道；抠图失败 → 重试生成；仍失败 → 占位模式

背景、CG、标题图不需要透明，直接 opaque 生成。

## 5. 验收与人审

1. 每生成一张：先由 `gen_image.py --asset-type figure` 通过尺寸/占幅 Gate，再用读图工具亲眼检查——像不像原图、是否为半身至大腿统一近景、有无明显崩坏（多手指、脸歪、文字乱码）。**立绘必须正脸可见、五官无遮挡**（头发完全遮脸、出现膝盖/脚、人物明显过小均为废图，重新生成）
2. 全套立绘生成完拼两张 contact sheet：**dialogue pose 表**（检查每张表情+姿态是否匹配标注的 usage tag，姿势轮廓应有变化，且没有剧情道具/位移行为）+ **action 用途表**（每张图下标出唯一动作和 allowed beat）。必须展示给用户同时确认「像不像」「身体语言是否自然」「图是否对应文本」
3. AI 生成图左下/右下角常带「AI生成」水印，**所有图（立绘/背景/CG/封面）入库前统一过 `scripts/trim_asset.py`**——按 3840 图高基准裁 130px（自动等比缩放；立绘绿幕图水印小可 --crop 60，有残留再补 130），背景图最常被漏掉，水印会在游戏里对话框下方露出来。批量用法：`python3 scripts/trim_asset.py assets_raw/*.png --crop 130 --to jpg --out-dir game/background`
4. **下载产物验证**：任何从远端/云端下载的资产，入库前先 `file <路径>` 确认是真图片——下载管道可能把错误页（JSON/HTML）存成 .png 文件名，直接入库会导致装配后封面黑屏且难以排查
4. 通过后登记 manifest.json。dialogue pose 条目除 prompt/ref/seed/status 外，必须复制视觉语义字段：`{"visual_role":"dialogue_pose","framing":"thigh_up","pose":"微侧身抱臂","expression":"警惕","gesture":"arms_crossed","usage_tags":["guarded","questioning"],"props":[]}`；action 另需 `action` 与 `allowed_beat_ids`，但 framing 同样只能是 `thigh_up`
5. 跑 `scripts/check_assets.py projects/<id>/game projects/<id>/manifest.json`。脚本会自动读取同级 `visual_plan.json`，核对剧本引用的每张立绘是否登记、manifest 语义是否与 figure_catalog 一致；通过后才能进 BUILD

## 6. 标题封面（title_main.jpg）生产流程

封面是玩家第一眼，必须是"一张完整的设计素材"，不是普通背景图。**标题与背景统一由生图模型一次直出**——字体设计随主题气质变化（木工作坊的刻痕宋体、街舞题材的涂鸦粗黑），这是 PIL 后期叠字做不到的；`bake_title.py` 降级为兜底路径。

1. **一张图直出**：9:16 4K（`--ratio 9:16`），**参考图按构图决定**：封面构图含角色 → 必须 `--ref` 角色参考图（封面人物是角色本人，不是氛围路人——真实踩坑：纯文字 prompt 让围裙少年顶替了绿外套的顾樵）；纯场景构图 → 不带。多角色封面参考图传主角，并在 prompt 里写清角色锚点（发型/外套/内搭）。prompt 一次写清画面 + 标题排版三层：
   - **画面**：氛围按 GDD 主题配方的 `cover.prompt_mood` 写（悬疑=noir 雨夜冷调低饱和、恋爱=黄昏暖调、治愈=柔光日常），不要千篇一律黄昏；**标题落区（上方约 1/3）压暗/留白**（open sky / negative space / 暗部），保证文字清晰可读；角色带锚点+回眸/标志性姿势
   - **主标题**：写确切文字（2-6 字游戏名）+ **字体气质推导**（从题材与氛围推：木工治愈=带刻痕的宋体、街舞=涂鸦粗黑、深夜电台=细宋微光、悬疑=冷硬无衬线）+ 颜色与描边（取主题配方 `cover.stroke` 色系，深底浅字）
   - **英文副标**：确切文字 + 宽字距小字
   - **tagline**：确切文字（**≤14 字**）+ 手写感/细体小字
   - prompt 参考句式：「封面上方三分之一处排游戏标题文字：中文主标题「雨停之前」四个大字，暖白色宋体带细腻深色描边，下方一行较小的英文副标题「BEFORE THE RAIN STOPS」，字距拉宽，再下方一行手写感中文小字 tagline「一夜，一盏灯，一块没刻完的木头」」
2. **多角色封面构图**：**主角占视觉中心**（前景、回眸、最大占比），配角次要（后景/侧影/局部入镜），禁止平均站位的群像；多攻略模式可双主角但要有主次（一前一后、一实一虚）
2.5 **锚点色检查**：AI 易把角色配饰色画错（如蓝领巾画成红）——用区域限定+HSV 色相替换局部修正，禁止全图阈值替换（会误伤天空/头发）
3. **文字校对（必经）**：VLM 逐字核对主标题/副标/tagline——中文错字、缺字、多字、字幕组式乱排**任一出现即重抽**；同一 prompt 连错 3 次 → 走降级路径：prompt 删去全部文字要求生成**干净底图**，再用 `bake_title.py` 后期排版（主标题 + `--eng` + `--tagline`，描边色取 `cover.stroke`，位置 `--y 0.10` 避开角色头顶；重排必须从未排版干净底图重新烘焙，二次 bake 会叠影）
4. **入库**：水印裁剪（`trim_asset.py`，见第 3 条）→ 瘦身（`bake_title.py <图> --shrink-only`：>1440 宽缩到 1440、progressive JPEG q85）——瘦身为**结局返回标题页防灰块**：React 封面层 remount 时大图解码要 1s+，progressive 让间隙不可感知。游戏命名规范：2-6 字短词、有记忆钩子（优先取自角色台词或核心设定数字，如「差你两分」），**禁止用一句口语长句当游戏名**（「这次一定赢你」式命名不合格）

**推导示例（同 IP 双版本对仗）**：同一题材出两个基调版本时，封面也应从各自基调推导而非换字了事——《第三小时》自由版=琥珀暖色霓虹灯管字体 + 街道尽头天际线泛亮（夜将明）；孤独版=冷白细宋带微弱青光 + 孤灯空街没入黑暗。字体气质、色温、构图光源全部由"自由/孤独"两个基调分别推导，与动效设计（上浮/沉降）同一条推导链。

## 7. 音频资产（BGM / 配音）

GDD 选项库里的「仅 BGM / BGM + 关键句配音 / 无」决定了本节要做什么。**音频没有生成工具，当前来源只有两种**（用户不上传音频；后续将接外部音频工具，届时本节扩展）：

1. **免版税素材库**：agent 可联网时从免版税库（如 Kevin MacLeod / incompetech、FreePD 等）下载，**必须确认授权允许免费商用**并在 GDD 资产清单节注明来源与授权；下载后 `file` 验证是真音频
2. **无音频**：网络不可用或授权不确定时——`config.txt` 的 `Title_bgm:;` 留空，剧本**不写任何 `bgm:`/`vocal:` 语句**（引用了不存在的音频文件会被 check_assets.py 拦下）

规则：

- BGM 数量按 GDD 资产清单预算执行（通常 2-3 首：主场景循环 / 情绪高潮 / 标题页）；文件名进 `game/bgm/`，剧本用 `bgm:xxx.mp3 -enter=3000;` 引用，标题页 BGM 填 `config.txt` 的 `Title_bgm:xxx.mp3;`
- **禁止虚构音频 URL**（剧本里写外链 mp3 会在装配后静默无声）；音频必须是 build/game 内的本地文件
- 情绪匹配：BGM 选择与主题配方同一条推导链（治愈=钢琴/环境雨声、悬疑=低频氛围、燃=节奏型），在 manifest.json 对应条目注明选曲理由

## 8. 结局结算短片：强制 Seedance 2.5（分镜表用法见 scriptwriter.md「结局达成卡」节）

每个结局一段 15-20s 结算短片。**唯一允许的生产路径 = Seedance 2.5 直出**。ffmpeg 只可用于抽帧、探测和格式验收，不得用于生成、补帧、Ken Burns、转场或替代结局视频。Seedance 不可用时当前项目停留在 ASSETS，不得用本地产物冒充完成。

### 8.1 参考素材（只传 1 张角色主题图）

用户拍板："不用那么多图片，文字描述+上传角色主题图就可以"。参考素材 = **角色主题图 1 张**（用户上传的原图 `character/<角色>_ref.png`，不用立绘/场景图）：

```python
# 本地图 → 公网 URL（复用 gen_image.py 的 agent_gw 通道）
from agent_gw import AgentGwClient
client = AgentGwClient()
url = client.upload_storage(file="projects/<id>/character/<角色>_ref.png").signed_url
```

### 8.2 prompt 组装规则（四段式——按规则组装，不靠自由发挥）

输入是 GDD 结局清单的**分镜表**（用户已批准），输出是喂给模型的单段文本：

```
【全局锚点，3 句定生死】<画风>（如"新海诚式动画电影质感"）+ 竖屏构图。<角色形象
  锚点>：图片1是<角色卡外貌锚点原文摘录——发型/瞳色/标志服装>，全片保持同一形象。
  情绪：<一句话基调（从结局名/判词提炼）>。
【分镜时间码】逐镜一句"X-Y秒：<分镜表该镜画面>+<运镜>"，时间码与分镜表一致。
【禁项，必须显式写】全程无人物对白，无字幕文字。
```

**不进 prompt 的东西**（硬规则）：结局名、判词、任何要显示的文字（模型渲染文字必翻车——结局名/判词走剧本旁白，见 scriptwriter.md）；BGM（走参数/后期，不写进文本）。

### 8.3 调用（scripts/gen_video.py）

```bash
python3 scripts/gen_video.py --prompt-file projects/<id>/storyboards/<结局>.txt   --ref projects/<id>/character/<角色>_ref.png   --out projects/<id>/game/video/card_<结局>.mp4   --ratio 9:16 --duration 15 --resolution 480p
```

- 视频生成 **provider 可插拔**（与 gen_image.py 同款模式）：`tools/providers.yaml` 的 `video.provider` 指定，当前默认 `seedance`（火山方舟异步任务 API），预留 `openai_compat`；新增 provider = `gen_video.py` 的 `PROVIDERS` 注册表加适配器（build_payload/create/poll_once/is_done 四钩子）+ yaml 同名段；**API key 走各 provider 的 `api_key_env` 环境变量，禁止写进脚本/文档/仓库**
- 本 skill 执行时 `video.provider` 必须为 `seedance`，且 `video.seedance.model_family` 必须为 `seedance-2.5`；不满足时 `gen_video.py` 直接失败，不允许切换其他 provider
- 默认 `generate_audio: true`（模型自带环境音轨；判词/结局名不在音轨里，AI 语音暂不用）
- 脚本行为：上传参考图 → 建任务 → 轮询（15s 间隔，超时 10 分钟）→ 下载校验（`file` 为真 MP4 + `ffprobe` 时长）
- prompt 存 `storyboards/<结局>.txt` 落档（可复现；跑偏了改它重跑，**不改分镜表**）
- 成功后脚本必须自动更新 `manifest.json`，并写 `video_receipts/<文件名>.seedance.json`；两处都要包含 `provider=seedance`、`model_family=seedance-2.5`、实际 `model`、真实 `task_id`、`prompt_file`、`reference_image`、输出路径和完成状态。禁止手填这些字段绕过生成脚本

### 8.4 验收（QA 前自检，逐条过）

1. **抽帧对照分镜表**：每镜抽 1 帧（`ffmpeg -ss <时间码中点>`），画面内容与 GDD 分镜表该镜描述一致
2. **角色一致性**：出镜帧与角色主题图对比——发型/瞳色/标志服装像不像（不像=参考图没生效，重跑）
3. **无乱码文字**：全片任何帧出现文字/字幕/水印即回炉（禁项没写够）
4. **时长与规格**：ffprobe 15-20s、9:16、480P
5. **音轨**：有环境音且与画面氛围不冲突（雨夜画面配鸟鸣=重跑）

### 8.5 失败处理（禁止自动降级）

- 建任务失败、任务状态 `failed`、轮询超时或下载校验失败：保留错误与任务 ID（如有），向用户报告，ASSETS Gate 判失败
- 禁止生成 ffmpeg 静帧动画、复制旧 MP4、把其他模型产物改名，或在 manifest 中手工伪造 Seedance 字段
- 只有重新调用 Seedance 2.5 并得到 `succeeded` 回执后，结算 MP4 才能进资产清单并进入 BUILD
