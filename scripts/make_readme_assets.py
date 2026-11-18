#!/usr/bin/env python3
"""make_readme_assets.py — 生成 README 用的三张大图（与静态站同一套设计语言）。

    python3 scripts/make_readme_assets.py            # 输出到 docs/assets/
    python3 scripts/make_readme_assets.py --out /tmp/x

产物：
    hero.png          首页大图：定位 + 关键数字 + 卡片墙
    how-it-works.png  一份清单、三种用法
    zero-body.png     仓库只存坐标，正文留在原作者

为什么用 PIL 而不是截图：仓库不想引入 150 MB 的无头浏览器依赖，PIL 输出
可复现、字体可控，文字也不会因为读者机器缺字体而错位。设计 token 取自
docs/index.html 的 :root 变量，改站点配色时这里同步改。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------- 设计 token
BG = (251, 251, 249)
BG_DEEP = (246, 245, 240)
PANEL = (255, 255, 255)
INK = (22, 24, 29)
INK2 = (91, 98, 112)
INK3 = (139, 146, 158)
LINE = (230, 228, 222)
LINE2 = (240, 238, 234)
ACCENT = (15, 92, 74)
ACCENT_SOFT = (232, 242, 238)
ACCENT_INK = (11, 70, 56)
MINT = (61, 138, 118)
MINT_SOFT = (122, 173, 157)
MINT_PALE = (180, 206, 197)
DOT = (235, 234, 228)

PINGFANG = ("/System/Library/AssetsV2/com_apple_MobileAsset_Font8/"
            "86ba2c91f017a3749571a82f2c6d890ac7ffb2fb.asset/AssetData/PingFang.ttc")
FALLBACK_CJK = "/System/Library/Fonts/Hiragino Sans GB.ttc"
MENLO = "/System/Library/Fonts/Menlo.ttc"

_FACES = {  # (weight) -> (path, index)
    "r": (PINGFANG, 3), "m": (PINGFANG, 7), "sb": (PINGFANG, 11),
    "mono": (MENLO, 0), "mono-b": (MENLO, 1),
}


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    path, idx = _FACES[kind]
    try:
        return ImageFont.truetype(path, size, index=idx)
    except OSError:
        return ImageFont.truetype(FALLBACK_CJK, size, index=2 if kind == "sb" else 0)


def canvas(w: int, h: int) -> Image.Image:
    """奶油底 + 竖向微渐变 + 网点纹理。"""
    base = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        base.putpixel((0, y), tuple(
            round(BG[i] + (BG_DEEP[i] - BG[i]) * t) for i in range(3)))
    img = base.resize((w, h), Image.BICUBIC).convert("RGBA")

    dots = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dots)
    for y in range(16, h, 26):
        for x in range(16, w, 26):
            dd.ellipse((x - 1, y - 1, x + 1, y + 1), fill=DOT + (255,))
    return Image.alpha_composite(img, dots)


def glow(size: tuple[int, int], center: tuple[int, int], radius: int,
         color: tuple[int, int, int], peak: int = 34) -> Image.Image:
    """柔和的径向光斑，给右侧内容垫一层色彩。"""
    small = 96
    tile = Image.new("L", (small, small), 0)
    px = tile.load()
    c = (small - 1) / 2
    for y in range(small):
        for x in range(small):
            d = ((x - c) ** 2 + (y - c) ** 2) ** 0.5 / c
            v = max(0.0, 1.0 - d) ** 2.2
            px[x, y] = int(v * 255)
    tile = tile.resize((radius * 2, radius * 2), Image.BICUBIC)
    tint = Image.new("RGBA", tile.size, color + (peak,))
    tint.putalpha(tile.point(lambda v: v * peak // 255))
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    layer.alpha_composite(tint, (center[0] - radius, center[1] - radius))
    return layer


def shadow(size: tuple[int, int], box: tuple[float, float, float, float],
           radius: int, blur: int = 26, dy: int = 12, alpha: int = 30) -> Image.Image:
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x0, y0, x1, y1 = box
    d.rounded_rectangle((x0, y0 + dy, x1, y1 + dy), radius=radius,
                        fill=(22, 24, 29, alpha))
    return layer.filter(ImageFilter.GaussianBlur(blur))


def text(d: ImageDraw.ImageDraw, xy, s: str, f, fill, anchor="ls") -> None:
    d.text(xy, s, font=f, fill=fill, anchor=anchor)


def tracked(d: ImageDraw.ImageDraw, xy, s: str, f, fill, tracking: float) -> float:
    """带字距的拉丁文（PIL 没有 letter-spacing）。"""
    x, y = xy
    for ch in s:
        d.text((x, y), ch, font=f, fill=fill, anchor="ls")
        x += d.textlength(ch, font=f) + tracking
    return x - tracking - xy[0]


def fit(d: ImageDraw.ImageDraw, s: str, kind: str, size: int, maxw: float):
    """超宽就降字号，避免中文长句压到右侧内容。"""
    while size > 12 and d.textlength(s, font=font(kind, size)) > maxw:
        size -= 1
    return font(kind, size)


def badge(d: ImageDraw.ImageDraw, xy, label: str, f, fg, bg,
          padx: int = 9, h: int = 22, radius: int = 6) -> int:
    tw = d.textlength(label, font=f)
    x, y = xy
    d.rounded_rectangle((x, y, x + tw + padx * 2, y + h), radius=radius, fill=bg)
    d.text((x + padx, y + h / 2), label, font=f, fill=fg, anchor="lm")
    return int(tw + padx * 2)


# ------------------------------------------------------------------ 01 hero
HERO_CARDS = [
    ("消保审查", "consumer-protection-review", "消费者保护", "skillhub", "proprietary"),
    ("公文写作", "official-document-skill", "办公与设计", "github", "MIT"),
    ("PPT 设计", "ppt-design-master", "办公与设计", "skillhub", "MIT"),
    ("深度研究", "deep-research-zh", "研究与分析", "github", "MIT"),
    ("反洗钱", "anti-money-laundering", "合规与法律", "github", "MIT"),
    ("日终对账", "reconciliation", "数据与技术", "skillhub", "proprietary"),
]


def make_hero(out: Path) -> None:
    W, H = 1600, 720
    img = canvas(W, H)
    d = ImageDraw.Draw(img)

    f_title, f_tag = font("sb", 62), font("sb", 15)
    f_lead, f_chip = font("r", 22), font("r", 13)
    f_num, f_lab = font("sb", 40), font("r", 13)
    f_card, f_id = font("sb", 18), font("mono", 11.5)
    f_badge, f_body = font("r", 11), font("r", 12.5)

    # ---- 右侧卡片墙：先画阴影、再画内容、最后裁进圆角面板
    px0, py0, px1, py1 = 856, 92, 1520, 648
    img.alpha_composite(glow((W, H), (1250, 330), 430, MINT_PALE, 30))
    img.alpha_composite(shadow((W, H), (px0, py0, px1, py1), 26, 34, 16, 34))

    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    pd.rounded_rectangle((px0, py0, px1, py1), radius=26, fill=PANEL)

    # 面板头：小圆点 + mono 标签
    pd.ellipse((px0 + 30, py0 + 30, px0 + 38, py0 + 38), fill=MINT)
    pd.text((px0 + 48, py0 + 34), "catalog.json", font=font("mono", 13),
            fill=INK3, anchor="lm")
    pd.text((px1 - 30, py0 + 34), "只存坐标 · 不存正文", font=font("r", 12.5),
            fill=INK3, anchor="rm")
    pd.line((px0 + 30, py0 + 60, px1 - 30, py0 + 60), fill=LINE2, width=1)

    cw, ch, gap = 296, 140, 18
    cx0, cy0 = px0 + 30, py0 + 78
    for i, (name, sid, cat, src, lic) in enumerate(HERO_CARDS):
        col, row = i % 2, i // 2
        x = cx0 + col * (cw + gap)
        y = cy0 + row * (ch + gap)
        pd.rounded_rectangle((x, y, x + cw, y + ch), radius=14,
                             fill=PANEL, outline=LINE2, width=1)
        pd.text((x + 18, y + 21), name, font=f_card, fill=INK, anchor="ls")
        pd.text((x + 18, y + 43), sid, font=f_id, fill=INK3, anchor="ls")

        bx = x + 18
        bx += badge(pd, (bx, y + 56), cat, f_badge, ACCENT_INK, ACCENT_SOFT) + 5
        bx += badge(pd, (bx, y + 56), src, f_badge,
                    ACCENT_INK if src == "skillhub" else (61, 69, 83),
                    ACCENT_SOFT if src == "skillhub" else (238, 240, 244)) + 5
        badge(pd, (bx, y + 56), lic, f_badge, INK2, (244, 243, 239))

        for k in range(2):
            w_line = cw - 36 if k == 0 else cw - 96
            pd.rounded_rectangle((x + 18, y + 94 + k * 15, x + 18 + w_line,
                                  y + 100 + k * 15), radius=3, fill=(244, 243, 239))

    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((px0, py0, px1, py1), radius=26, fill=255)
    img.paste(panel, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((px0, py0, px1, py1), radius=26, outline=LINE, width=1)

    # ---- 左侧文案
    lx = 96
    draw_logo(img, lx, 96, 64)

    text(d, (lx, 250), "金融行业skills精选", f_title, INK)
    tracked(d, (lx + 3, 292), "AWESOME  FINANCIAL  SKILLS", f_tag, INK3, 2.6)

    d.line((lx, 332, lx + 54, 332), fill=(214, 210, 200), width=2)

    text(d, (lx, 386), "从海量 AI 技能里，挑出真正能干活的那些。", f_lead, INK2)
    line2 = "只收录 Git / SkillHub 上被真实使用、作用明确的金融技能。"
    text(d, (lx, 428), line2, fit(d, line2, "r", 22, 716), INK2)

    stats = [("171", "项技能"), ("9", "大业务场景"), ("2", "类来源"), ("0", "行他人正文")]
    sx = lx
    for i, (num, lab) in enumerate(stats):
        text(d, (sx, 552), num, f_num, ACCENT)
        text(d, (sx, 578), lab, f_lab, INK3)
        sx += 118 if i < 3 else 0
        if i < 3:
            d.line((sx + 30, 518, sx + 30, 586), fill=LINE, width=1)
            sx += 88

    # 底部一行小字
    text(d, (lx, 646), "开源 · 许可证逐条标注 · 技能正文不入库",
         font("r", 12.5), (163, 169, 178))

    img.convert("RGB").save(out, optimize=True)


def draw_logo(img: Image.Image, x: int, y: int, size: int) -> None:
    """把 docs/logo.svg 的四个圆角块 + 连接点重绘成位图。"""
    d = ImageDraw.Draw(img)
    g = size / 36.0
    quads = [
        (1.5, 1.5, ACCENT, (16.5, 9)),
        (19.5, 1.5, MINT, (27, 16.5)),
        (19.5, 19.5, MINT_SOFT, (19.5, 27)),
        (1.5, 19.5, MINT_PALE, (9, 19.5)),
    ]
    for qx, qy, color, (dx, dy) in quads:
        d.rounded_rectangle((x + qx * g, y + qy * g,
                             x + (qx + 15) * g, y + (qy + 15) * g),
                            radius=4.2 * g, fill=color)
    for qx, qy, color, (dx, dy) in quads:
        r = 2.7 * g
        d.ellipse((x + dx * g - r, y + dy * g - r,
                   x + dx * g + r, y + dy * g + r), fill=color)


# --------------------------------------------------------- 02 how it works
ROWS = [
    ("01", "网站浏览", "九类筛选、来源筛选、中英切换，卡片上直接复制安装方式",
     "openfcp.github.io/awesome-financial-skills"),
    ("02", "WorkBuddy 技能市场", "只下清单不下技能，点哪张装哪张，包只有 2 KB",
     "cdn.jsdelivr.net/gh/openfcp/…@main/marketplace.json"),
    ("03", "DSH 插件 / 终端", "插件里看清单，或一条命令装进技能目录",
     "dsh plugin add github:openfcp/dsh-financial-skills"),
]


def make_how(out: Path) -> None:
    W, H = 1600, 620
    img = canvas(W, H)
    d = ImageDraw.Draw(img)

    text(d, (96, 96), "一份清单，三种用法", font("sb", 38), INK)
    text(d, (96, 136), "catalog.json 是唯一真相源，网站、市场、插件都从它派生。",
         font("r", 17), INK2)

    # 左：清单本体
    lx0, ly0, lx1, ly1 = 96, 196, 520, 540
    img.alpha_composite(shadow((W, H), (lx0, ly0, lx1, ly1), 20, 28, 12, 26))
    d.rounded_rectangle((lx0, ly0, lx1, ly1), radius=20, fill=PANEL, outline=LINE, width=1)
    d.text((lx0 + 28, ly0 + 40), "catalog.json", font=font("mono-b", 19), fill=INK, anchor="ls")
    badge(d, (lx0 + 28, ly0 + 58), "唯一真相源", font("r", 11.5), ACCENT_INK, ACCENT_SOFT, 10, 24)

    mono = font("mono", 13)
    lines = [
        ("171", "条技能坐标"),
        ("9", "个业务分类"),
        ("2", "类来源 skillhub / github"),
        ("369", "个标签"),
    ]
    yy = ly0 + 112
    for num, lab in lines:
        d.text((lx0 + 28, yy), num, font=font("sb", 22), fill=ACCENT, anchor="ls")
        d.text((lx0 + 92, yy), lab, font=font("r", 14.5), fill=INK2, anchor="ls")
        yy += 50

    d.line((lx0 + 28, ly1 - 58, lx1 - 28, ly1 - 58), fill=LINE2, width=1)
    d.text((lx0 + 28, ly1 - 30), "resolve 规则内含取回方式", font=font("r", 13), fill=INK3, anchor="ls")

    # 右：三条路径
    rx0, rx1 = 620, 1504
    top, rh, gap = 196, 118, 24
    centers = []
    for i, (num, name, desc, cmd) in enumerate(ROWS):
        y0 = top + i * (rh + gap)
        y1 = y0 + rh
        centers.append((y0 + y1) // 2)
        img.alpha_composite(shadow((W, H), (rx0, y0, rx1, y1), 16, 24, 10, 20))
        d.rounded_rectangle((rx0, y0, rx1, y1), radius=16, fill=PANEL, outline=LINE, width=1)

        d.rounded_rectangle((rx0 + 26, y0 + 34, rx0 + 76, y0 + 84), radius=12,
                            fill=ACCENT_SOFT)
        d.text((rx0 + 51, y0 + 59), num, font=font("mono-b", 17), fill=ACCENT_INK, anchor="mm")

        d.text((rx0 + 96, y0 + 48), name, font=font("sb", 22), fill=INK, anchor="ls")
        d.text((rx0 + 96, y0 + 78), desc, font=font("r", 15), fill=INK2, anchor="ls")

        tw = d.textlength(cmd, font=font("mono", 12))
        chip_x1 = rx1 - 26
        chip_x0 = chip_x1 - (tw + 28)
        d.rounded_rectangle((chip_x0, y0 + 34, chip_x1, y0 + 62), radius=8,
                            fill=(247, 247, 244))
        d.text((chip_x0 + 14, y0 + 48), cmd, font=font("mono", 12),
               fill=(120, 127, 139), anchor="lm")

    # 连接线：左卡 → 三条路径
    src = (lx1, (ly0 + ly1) // 2)
    for cy in centers:
        elbow = 566
        d.line([(src[0], src[1]), (elbow, src[1])], fill=(206, 202, 192), width=2)
        d.line([(elbow, src[1]), (elbow, cy)], fill=(206, 202, 192), width=2)
        d.line([(elbow, cy), (rx0 - 10, cy)], fill=(206, 202, 192), width=2)
        d.polygon([(rx0 - 2, cy), (rx0 - 12, cy - 5), (rx0 - 12, cy + 5)],
                  fill=(206, 202, 192))
    d.ellipse((src[0] - 4, src[1] - 4, src[0] + 4, src[1] + 4), fill=MINT)

    img.convert("RGB").save(out, optimize=True)


# ------------------------------------------------------------ 03 zero body
def make_zero(out: Path) -> None:
    W, H = 1600, 560
    img = canvas(W, H)
    d = ImageDraw.Draw(img)

    text(d, (96, 92), "仓库里只有坐标，没有正文", font("sb", 38), INK)
    text(d, (96, 132), "别人的技能留在别人的仓库；你装的时候现取，永远是最新版。",
         font("r", 17), INK2)

    # 左：本仓
    a = (96, 196, 700, 452)
    img.alpha_composite(shadow((W, H), a, 18, 26, 12, 24))
    d.rounded_rectangle(a, radius=18, fill=PANEL, outline=LINE, width=1)
    d.text((a[0] + 28, a[1] + 40), "本仓库 · catalog.json 约 184 KB",
           font=font("r", 14), fill=INK3, anchor="ls")

    mono, code_hi = font("mono", 14), font("mono-b", 14)
    y = a[1] + 84
    for seg in [('"source": {', mono, INK2),
                ('  "type": "skillhub",', mono, INK),
                ('  "namespace": "user_e3180ba3",', mono, INK),
                ('  "slug": "consumer-protection-review"', mono, INK),
                ("}", mono, INK2)]:
        d.text((a[0] + 28, y), seg[0], font=seg[1], fill=seg[2], anchor="ls")
        y += 26
    badge(d, (a[0] + 28, y + 14), "只有坐标 · 约 1 KB / 条", font("r", 11.5),
          ACCENT_INK, ACCENT_SOFT, 10, 24)

    # 右：原作者
    b = (940, 196, 1504, 452)
    img.alpha_composite(shadow((W, H), b, 18, 26, 12, 24))
    d.rounded_rectangle(b, radius=18, fill=PANEL, outline=LINE, width=1)
    d.text((b[0] + 28, b[1] + 40), "原作者仓库 · 正文留在原地",
           font=font("r", 14), fill=INK3, anchor="ls")

    tree = [("SKILL.md", INK, "bold"), ("scripts/review.py", INK2, "mono"),
            ("references/checklist.md", INK2, "mono"), ("… 以及其余文件", INK3, "cjk")]
    y = b[1] + 84
    for name, color, style in tree:
        f = {"bold": code_hi, "mono": mono, "cjk": font("r", 13.5)}[style]
        d.text((b[0] + 28, y), name, font=f, fill=color, anchor="ls")
        y += 28

    badge(d, (b[0] + 28, b[3] - 46), "只读引用 · 不回传本仓", font("r", 11.5),
          INK2, (244, 243, 239), 10, 24)

    # 中间的取回箭头
    ax0, ax1, ay = a[2] + 26, b[0] - 26, 324
    x = ax0
    while x < ax1 - 16:
        d.line((x, ay, min(x + 12, ax1 - 16), ay), fill=(178, 192, 186), width=2)
        x += 22
    d.polygon([(ax1, ay), (ax1 - 13, ay - 6), (ax1 - 13, ay + 6)], fill=(178, 192, 186))
    d.text(((ax0 + ax1) / 2, ay - 16), "安装时按坐标取回", font=font("r", 13),
           fill=INK3, anchor="ms")

    text(d, (96, 496), "构建时仓内一旦出现未声明的 SKILL.md 直接失败 —— 副本长不回来。",
         font("r", 14), (163, 169, 178))

    img.convert("RGB").save(out, optimize=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None, help="输出目录，默认 docs/assets")
    a = ap.parse_args()
    root = Path(__file__).resolve().parent.parent
    out = Path(a.out) if a.out else root / "docs" / "assets"
    out.mkdir(parents=True, exist_ok=True)

    make_hero(out / "hero.png")
    make_how(out / "how-it-works.png")
    make_zero(out / "zero-body.png")
    for p in sorted(out.glob("*.png")):
        print(f"[assets] {p.relative_to(root) if out.is_relative_to(root) else p}"
              f"  {p.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
