#!/bin/sh
# 一键装配：引擎基座 + 游戏内容覆盖 + 主题 + 必做补丁 + 自检
# 用法: assemble_build.sh <project_dir> <主题名> [游戏显示名]
#   project_dir 含 game/ 子目录的项目根（init_project.py 产出）
# 例: assemble_build.sh projects/third-hour-free midnight "第三小时"
set -e
PROJ="$1"
THEME="$2"
NAME="$3"
SKILL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

[ -d "$PROJ/game" ] || { echo "ERROR: $PROJ/game 不存在，先跑 init_project.py" >&2; exit 1; }
[ -n "$THEME" ] || { echo "ERROR: 缺少主题名" >&2; exit 1; }

# 1. 引擎基座（init_project 预建了 build/，直接 cp -r 会嵌套成 build/engine，必须先删）
rm -rf "$PROJ/build"
cp -r "$SKILL_ROOT/assets/engine" "$PROJ/build"

# 2. 游戏内容覆盖
cp -r "$PROJ/game" "$PROJ/build/"

# 3. 应用主题（脚本内部自动识别 build / build/game）
sh "$SKILL_ROOT/assets/themes/apply_theme.sh" "$THEME" "$PROJ/build"

# 4. config.txt 必做补丁：关继续游戏/CG鉴赏入口，设置游戏名
CFG="$PROJ/build/game/config.txt"
perl -pi -e 's/Enable_Continue:true;/Enable_Continue:false;/; s/Enable_Appreciation:true;/Enable_Appreciation:false;/' "$CFG"
[ -n "$NAME" ] && perl -pi -e "s/^Game_name:.*;/Game_name:$NAME;/" "$CFG"

# 5. 自检（任一失败即非零退出）
FAIL=0
grep -q "localStorage.setItem('lang'" "$PROJ/build/index.html" || { echo "MISS: 中文默认补丁"; FAIL=1; }
grep -qF '/*__FX_CSS__*/' "$PROJ/build/index.html" && { echo "MISS: 动效占位符残留（缺 effects.css？）"; FAIL=1; }
grep -qF '/*__FX_CSS__*/' "$PROJ/build/game/userStyleSheet.css" && { echo "MISS: React层动效占位符残留"; FAIL=1; }
[ -f "$PROJ/build/game/background/title_main.jpg" ] || { echo "MISS: 封面 title_main.jpg"; FAIL=1; }
[ -f "$PROJ/build/game/template/template.json" ] || { echo "MISS: 主题模板"; FAIL=1; }
grep -q "Enable_Continue:false;" "$CFG" || { echo "MISS: config 补丁"; FAIL=1; }
[ "$FAIL" -eq 0 ] && echo "assemble OK: $PROJ/build （主题 $THEME）" || { echo "assemble FAILED" >&2; exit 1; }
