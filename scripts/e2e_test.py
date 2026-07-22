#!/usr/bin/env python3
"""e2e_test.py — 9:16 竖屏无头浏览器跑通测试

流程: 打开页面 → 触屏进入 → 开始游戏 → 推进对话 → 触发并点击选择支 →
      持续推进直到出现结局或步数耗尽，逐步截图。

用法:
  python3 e2e_test.py <url> --out <截图目录> [--max-steps 40] \
      [--choice-strategy first|middle|last] [--scene-dir <场景目录>]
退出码: 0=到达结局(end) 1=未到达/有 JS 报错
依赖: playwright (pip install playwright && playwright install chromium)

选择支处理:
  提供 --scene-dir 时（推荐）：解析剧本 choose 行得到每处选项文本与顺序，
  检测页面上含选项文本的元素，按 strategy 精确点击（first=第一个选项, last=最后一个），
  点击后校验选项消失，未消失重试。未提供时退化为几何探测（cursor:pointer 居中大按钮）。
  另含读档界面守卫：误进「读取存档」页时自动点「返回」。
多结局覆盖: 用不同 strategy 各跑一遍（first 通常好感最高路线, last 最低）。
步数参考: 每章约 20-25 步（5 章剧本建议 --max-steps 130）。
"""
import argparse
import asyncio
import os
import re
import sys

VIEWPORT = {"width": 390, "height": 844}  # 9:16 手机视口


def parse_choice_groups(scene_dir: str):
    """从场景文件解析 choose 行的选项文本组（按文件+行号排序）。
    返回 [[opt1, opt2, ...], ...]，选项文本去掉条件前缀 (cond)->。"""
    groups = []
    if not scene_dir or not os.path.isdir(scene_dir):
        return groups
    files = sorted(f for f in os.listdir(scene_dir) if f.endswith(".txt"))
    for fn in files:
        with open(os.path.join(scene_dir, fn), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line.startswith("choose:"):
                    continue
                body = line[len("choose:"):].rstrip(";")
                opts = []
                for part in body.split("|"):
                    text = part.rsplit(":", 1)[0]  # 去掉 :label
                    text = re.sub(r"^\(.*?\)->", "", text)  # 去掉条件前缀
                    text = text.strip()
                    if text:
                        opts.append(text)
                if len(opts) >= 2:
                    groups.append(opts)
    return groups


async def click_text(page, text: str) -> bool:
    """div 文本定位 + bounding box 坐标点击（scale 容器内 playwright 原生点击不可靠）。"""
    els = await page.query_selector_all(f'div:has-text("{text}")')
    best = None
    for el in els:
        box = await el.bounding_box()
        if box and box["width"] > 40 and box["height"] > 20:
            area = box["width"] * box["height"]
            if best is None or area < best[0]:
                best = (area, box)
    if best:
        box = best[1]
        await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        return True
    return False


async def probe_choices(page):
    """返回页面上候选选项元素 [{text, x, y, area}]，按 y 排序。"""
    return await page.evaluate("""() => {
        const out = [];
        for (const el of document.querySelectorAll('div')) {
            const cs = getComputedStyle(el);
            if (cs.cursor !== 'pointer') continue;
            const r = el.getBoundingClientRect();
            if (r.width > 150 && r.height > 25 && r.height < 120
                && r.x > 20 && r.x + r.width < 370 && r.y > 150 && r.y < 800) {
                out.push({text: el.textContent.trim(),
                          y: r.y + r.height / 2, x: r.x + r.width / 2,
                          area: r.width * r.height});
            }
        }
        out.sort((a, b) => a.y - b.y);
        return out;
    }""")


async def guard_menu(page):
    """误进「读取存档」等系统页时点「返回」回到游戏。"""
    in_menu = await page.evaluate("""() => {
        const t = document.body.innerText;
        return t.includes('读取存档') && t.includes('返回');
    }""")
    if in_menu:
        await click_text(page, "返回")
        await page.wait_for_timeout(800)
        return True
    return False


async def main_async(args) -> int:
    from playwright.async_api import async_playwright

    os.makedirs(args.out, exist_ok=True)
    errors = []
    warns = []
    reached_choice = False
    choice_groups = parse_choice_groups(args.scene_dir) if args.scene_dir else []
    choice_plan = None
    if args.choice_plan:
        choice_plan = [int(x) for x in args.choice_plan.split(",") if x.strip() != ""]
        print(f"使用 choice-plan: {choice_plan}")
    if choice_groups:
        print(f"已从场景解析 {len(choice_groups)} 处选择支")

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport=VIEWPORT)
        await ctx.add_init_script("localStorage.setItem('lang','0'); localStorage.clear()")
        page = await ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: warns.append(f"console: {m.text}")
                if m.type == "error" else None)

        await page.goto(args.url, wait_until="networkidle")
        await page.wait_for_timeout(2500)
        await page.mouse.click(195, 422)  # PRESS TO START
        await page.wait_for_timeout(2500)
        await page.screenshot(path=os.path.join(args.out, "01_title.png"))

        if not await click_text(page, "开始游戏"):
            errors.append("未找到「开始游戏」按钮")
        await page.wait_for_timeout(3000)

        import time
        step, shot = 0, 2
        ended = False
        plan_pos = 0
        while step < args.max_steps and not ended:
            step += 1
            if step % 4 == 1:  # 每 4 步一图，结局场景不再被 8 步间隔跳过
                await page.screenshot(path=os.path.join(args.out, f"{shot:02d}_step{step}.png"))
                shot += 1

            if await guard_menu(page):
                continue

            # 结局 playVideo -skipOff 期间不能继续点屏幕：部分 WebGAL 版本会把
            # 点击解释为重新聚焦/重播，自动化因此永久停在视频首镜。可见视频
            # 播放时只等待自然结束；隐藏的预载 video 不应阻塞剧情推进。
            video_state = await page.evaluate("""() => {
                const v = document.querySelector('video');
                if (!v) return null;
                const s = getComputedStyle(v), r = v.getBoundingClientRect();
                const visible = s.display !== 'none' && s.visibility !== 'hidden' &&
                    Number(s.opacity || 1) > 0 && r.width > 40 && r.height > 40;
                return visible ? {ended: v.ended, paused: v.paused, time: v.currentTime} : null;
            }""")
            if video_state and not video_state["ended"]:
                await page.wait_for_timeout(1000)
                continue

            choices = []
            if True:  # 每步必探：选项停在屏幕中央，推进点击会误吞选择支
                cands = await probe_choices(page)
                if choice_groups:
                    # 文本感知：匹配已知选项组，取该组定义顺序
                    texts = [c["text"] for c in cands]
                    for group in choice_groups:
                        hits = [i for i, t in enumerate(group)
                                if any(t in ct or ct in t for ct in texts if ct)]
                        if len(hits) >= 2:
                            ordered = [group[i] for i in hits]
                            if choice_plan and plan_pos < len(choice_plan):
                                idx = min(choice_plan[plan_pos], len(ordered) - 1)
                            else:
                                idx = {"first": 0, "middle": len(ordered) // 2,
                                       "last": len(ordered) - 1}[args.choice_strategy]
                            target = ordered[idx]
                            # 候选里文本匹配且面积最小的元素（避开 wrapper）
                            pool = [c for c in cands
                                    if target in c["text"] or c["text"] in target]
                            pool.sort(key=lambda c: c["area"])
                            choices = [pool[0]] if pool else []
                            if pool:
                                plan_pos += 1
                            break
                elif len(cands) >= 2:
                    idx = {"first": 0, "middle": len(cands) // 2,
                           "last": len(cands) - 1}[args.choice_strategy]
                    choices = [cands[idx]]

            if choices:
                pt = choices[0]
                await page.screenshot(path=os.path.join(args.out, f"{shot:02d}_choice_{args.choice_strategy}.png"))
                shot += 1
                await page.mouse.click(pt["x"], pt["y"])
                reached_choice = True
                await page.wait_for_timeout(900)
                # 点击校验：选项还在就补点一次
                again = await probe_choices(page)
                if any(c["text"] == pt["text"] for c in again):
                    await page.mouse.click(pt["x"], pt["y"])
            else:
                # 打字机：第一击补完文本可能弹出选项，第二击必须先探再点，否则会误吞选择支
                await page.mouse.click(195, 422)
                await page.wait_for_timeout(300)
                if not (await probe_choices(page)):
                    await page.mouse.click(195, 422)
            await page.wait_for_timeout(500)
            # 结局判定：end; 后回到标题页，「开始游戏」按钮重新可见（每 3 步探测一次）
            if step > 5 and step % 3 == 0:
                els = await page.query_selector_all('div:has-text("开始游戏")')
                for el in els:
                    box = await el.bounding_box()
                    if box and box["width"] > 40 and box["height"] > 20:
                        ended = True
                        break
                if ended:
                    await page.screenshot(path=os.path.join(args.out, "98_ending.png"))

        await page.screenshot(path=os.path.join(args.out, "99_final.png"))
        await browser.close()

    print(f"steps={step} choice_reached={reached_choice} ended={ended}")
    if warns:
        print(f"资源加载警告 {len(warns)} 条（详见截图与 check_assets）:")
        for w in warns[:5]:
            print(f"  {w[:160]}")
    if errors:
        print("JS 报错:")
        for e in errors[:8]:
            print(f"  {e[:200]}")
    if ended and not errors:
        print("PASS: E2E 跑通")
        return 0
    print("FAIL: 未到达结局或存在报错")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-steps", type=int, default=40)
    ap.add_argument("--choice-strategy", default="middle",
                    choices=["first", "middle", "last"])
    ap.add_argument("--choice-plan", default="",
                    help="逗号分隔的选项序号序列，按选择支出现顺序覆盖 strategy（多结局覆盖用）")
    ap.add_argument("--scene-dir", default="",
                    help="场景 txt 目录，提供后选择支按文本精确点击")
    args = ap.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
