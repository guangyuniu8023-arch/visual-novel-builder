#!/bin/sh
# 用法: apply_theme.sh <主题名> [dist目录]
# dist 可传 <id>/build 或 <id>/build/game（自动识别，文档与脚本不再打架）
# 复制皮肤模板+全局样式；校验粒子 tile 存在；把 effects.css（项目级优先，
# 主题级兜底）注入落地页 index.html 与 React 层 userStyleSheet.css 的
# __FX_CSS__ 占位符；按 theme.json effects 推导参数注入扫光/推拉/兜底色
set -e
THEME="$1"
DST="${2:-/tmp/webgal/packages/webgal/dist/game}"
# 路径自适配：传入的是 build 根（含 game 子目录）时自动下钻
if [ ! -d "$DST/template" ] && [ -d "$DST/game/template" ]; then
  DST="$DST/game"
fi
SRC="$(cd "$(dirname "$0")" && pwd)/$THEME"
INDEX_HTML="$(cd "$DST/.." && pwd)/index.html"

cp "$SRC/template/template.json"              "$DST/template/template.json"
cp "$SRC/template/Stage/TextBox/textbox.scss" "$DST/template/Stage/TextBox/textbox.scss"
cp "$SRC/template/Stage/Choose/choose.scss"   "$DST/template/Stage/Choose/choose.scss"
cp "$SRC/template/UI/Title/title.scss"        "$DST/template/UI/Title/title.scss"
cp "$SRC/userStyleSheet.css"                  "$DST/userStyleSheet.css"

# 粒子 tile 检查：tile 是项目主题素材（agent 按主题推导后用
# gen_particles.py 自由参数绘制 / gen_image.py 生成 / 自行创作），
# apply_theme 不再按枚举配方代生成——素材从零，脚本只把关存在性与原创性。
# 教训（v8.3）：引擎曾内置默认 tile，存在性检查被默认件满足而静默放行，
# 4 个项目标题粒子全是同一批光斑。默认件已删，且 md5 撞默认件同样报错。
if [ ! -f "$DST/background/title_particles.png" ]; then
  echo "ERROR: 缺少 $DST/background/title_particles.png" >&2
  echo "  粒子 tile 需按主题推导后自行提供（tools: gen_particles.py / gen_image.py）" >&2
  exit 1
fi
TILE_MD5=$(md5 -q "$DST/background/title_particles.png" 2>/dev/null || md5sum "$DST/background/title_particles.png" | cut -d' ' -f1)
if [ "$TILE_MD5" = "a5d1b2a8a2502a03d51c100e210076ea" ]; then
  echo "ERROR: title_particles.png 与引擎旧默认光斑 tile 完全相同（md5 碰撞）" >&2
  echo "  粒子 tile 必须由本项目按主题推导自产，禁止沿用默认件" >&2
  exit 1
fi

# 动效注入（effects.css → 落地页 index.html + React 层 userStyleSheet.css）
# 引擎零预置动效：每个项目的动效由 agent 按主题从零设计（推导法见 references/build.md）。
# 查找顺序：项目级 effects.css（项目根，dist 的上两级）→ 主题级 effects.css（皮肤骨架兜底）
PROJ_ROOT="$(cd "$DST/../.." 2>/dev/null && pwd || echo "")"
FX_CSS_FILE=""
if [ -n "$PROJ_ROOT" ] && [ -f "$PROJ_ROOT/effects.css" ]; then
  FX_CSS_FILE="$PROJ_ROOT/effects.css"
elif [ -f "$SRC/effects.css" ]; then
  FX_CSS_FILE="$SRC/effects.css"
fi
if [ -z "$FX_CSS_FILE" ]; then
  echo "ERROR: 动效设计缺失：请为主题从零编写 effects.css（项目根或主题目录）" >&2
  echo "  推导法见 visual-novel-builder/references/build.md「动效设计」" >&2
  exit 1
fi
for f in "$INDEX_HTML" "$DST/userStyleSheet.css"; do
  [ -f "$f" ] || continue
  # CSS 经文件读入作变量值替换：避免 @keyframes 的 @ 被 perl 当数组插值吞掉
  FX_CSS_FILE="$FX_CSS_FILE" perl -0777 -pi -e '
    open my $fh, "<", $ENV{FX_CSS_FILE} or die "read effects.css: $!";
    local $/; my $css = <$fh>; close $fh;
    s{/\*__FX_CSS__\*/}{$css}g;
  ' "$f"
  if grep -qF '/*__FX_CSS__*/' "$f"; then
    echo "ERROR: $f 动效占位符注入失败" >&2; exit 1
  fi
done
echo "effects.css: $FX_CSS_FILE 已注入"

# 动效配方注入（theme.json effects → 落地页 index.html + React 层 userStyleSheet.css）
# 扫光/推拉不再是全局写死：治愈系可关扫光、悬疑系关扫光保持冷峻、深夜系换琥珀微光
if [ -f "$SRC/theme.json" ] && [ -f "$INDEX_HTML" ]; then
  eval $(python3 - "$SRC/theme.json" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1]))
fx = d.get("effects", {})
sh = fx.get("sheen", {})
kb = fx.get("kenburns", {})
if sh.get("enabled", True):
    tint = sh.get("tint", "255,255,255")
    peak = float(sh.get("peak", 0.30))
    angle = sh.get("angle", "115deg")
    lo = round(peak * 0.53, 3)
    bg = f"linear-gradient({angle}, transparent 30%, rgba({tint},{lo}) 45%, rgba({tint},{peak}) 50%, rgba({tint},{lo}) 55%, transparent 70%)"
    anim = f"titleSheen {sh.get('duration','9s')} ease-in-out infinite"
else:
    bg, anim = "none", "none"
# 兜底渐变（封面图就位前的落地页底色）与点击闪色（primary 派生）
fallback = fx.get("fallback", "linear-gradient(180deg, #1a1a2e 0%, #2a2a3e 100%)")
primary = d.get("primary", "#8FD8C6").lstrip("#")
flash = f"linear-gradient(#{primary}4D 0%, #{primary}99 100%)"
def shq(s):  # shell 单引号安全
    return "'" + str(s).replace("'", "'\\''") + "'"
print("SHEEN_BG=" + shq(bg))
print("SHEEN_ANIM=" + shq(anim))
print("KB_DUR=" + shq(kb.get("duration", "14s")))
print("KB_Z0=" + shq(kb.get("zoomFrom", "104%")))
print("KB_Z1=" + shq(kb.get("zoomTo", "117%")))
print("FALLBACK=" + shq(fallback))
print("FLASH=" + shq(flash))
PYEOF
)
  for f in "$INDEX_HTML" "$DST/userStyleSheet.css"; do
    [ -f "$f" ] || continue
    SHEEN_BG="$SHEEN_BG" perl -pi -e 's/__SHEEN_BACKGROUND__/$ENV{SHEEN_BG}/g' "$f"
    SHEEN_ANIM="$SHEEN_ANIM" perl -pi -e 's/__SHEEN_ANIMATION__/$ENV{SHEEN_ANIM}/g' "$f"
    KB_DUR="$KB_DUR" perl -pi -e 's/__KB_DURATION__/$ENV{KB_DUR}/g' "$f"
    KB_Z0="$KB_Z0" perl -pi -e 's/__KB_ZOOM_FROM__/$ENV{KB_Z0}/g' "$f"
    KB_Z1="$KB_Z1" perl -pi -e 's/__KB_ZOOM_TO__/$ENV{KB_Z1}/g' "$f"
    FALLBACK="$FALLBACK" perl -pi -e 's/__COVER_FALLBACK__/$ENV{FALLBACK}/g' "$f"
    FLASH="$FLASH" perl -pi -e 's/__ENTER_FLASH__/$ENV{FLASH}/g' "$f"
    if grep -q "__SHEEN_\|__KB_\|__COVER_FALLBACK__\|__ENTER_FLASH__" "$f"; then
      echo "ERROR: $f 动效占位符注入不完全" >&2; exit 1
    fi
  done
  echo "effects: sheen=$SHEEN_ANIM kb=$KB_DUR $KB_Z0->$KB_Z1"
fi

echo "theme applied: $THEME -> $DST"
