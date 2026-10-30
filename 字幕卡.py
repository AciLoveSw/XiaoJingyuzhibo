# -*- coding: utf-8 -*-
"""把一句话渲染成「气泡+文字」的透明卡片，给 OBS 图片源用"""
import os
from PIL import Image, ImageDraw, ImageFont

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "字幕卡.png")
FB = r"C:\Windows\Fonts\msyhbd.ttc"
W, H = 920, 310
BLUE = (74, 123, 208)
BLACK = (27, 27, 27)


def _wrap(draw, text, font, maxw):
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) > maxw and cur:
            lines.append(cur); cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def render(text, out=OUT):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    TOP, BOT, R = 10, H - 96, 46
    d.rounded_rectangle((10, TOP, W - 10, BOT), radius=R, fill=(255, 255, 255, 255))
    d.polygon([(130, BOT - 2), (258, BOT - 2), (156, H - 12)], fill=(255, 255, 255, 255))
    d.rounded_rectangle((10, TOP, W - 10, BOT), radius=R, outline=BLUE, width=6)
    d.line([(132, BOT), (256, BOT)], fill=(255, 255, 255, 255), width=10)
    d.line([(132, BOT - 1), (156, H - 14)], fill=BLUE, width=6)
    d.line([(256, BOT - 1), (156, H - 14)], fill=BLUE, width=6)

    font = ImageFont.truetype(FB, 42)
    lines = _wrap(d, text, font, W - 150)[:3]
    lh = 58
    total = len(lines) * lh
    y = (BOT - total) // 2 + 4
    for ln in lines:
        tw = d.textlength(ln, font=font)
        d.text(((W - tw) / 2, y), ln, font=font, fill=BLACK)
        y += lh
    im.save(out)
    return out


if __name__ == "__main__":
    import sys
    t = sys.argv[1] if len(sys.argv) > 1 else "喵~ 欢迎来到小鲸鱼的直播间"
    print(render(t))
