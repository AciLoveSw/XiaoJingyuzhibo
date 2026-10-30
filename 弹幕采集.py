# -*- coding: utf-8 -*-
"""小鲸鱼 · 弹幕采集（固定区域版）
直播伴侣「互动消息」面板：默认坐标见 DEFAULT_REGION，可用 --pick 重框
"""
import asyncio, ctypes, json, os, re, sys, time
import 识屏
import difflib
from collections import Counter
from PIL import Image, ImageChops, ImageGrab

BASE = os.path.dirname(os.path.abspath(__file__))
REGION = os.path.join(BASE, "采集区域.json")
DANMU = os.path.join(BASE, "弹幕.txt")
LOG = os.path.join(BASE, "采集日志.txt")
SHOT = os.path.join(BASE, "采集截图.png")
HB = os.path.join(BASE, "监听心跳.txt")     # 弹幕转接.py 活着就会每秒刷新它

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

DEFAULT_REGION = (1548, 380, 1916, 892)

# 单实例保护（在 main 里调用；--pick / --test 是临时命令，不占锁）
_guard = None


def _single_instance(port=8799, name="弹幕采集"):
    global _guard
    import socket as _socket
    _guard = _socket.socket()
    try:
        _guard.bind(("127.0.0.1", port))
    except OSError:
        print("已经有一个「%s」在运行，本进程退出。" % name)
        raise SystemExit(0)

UI_NOISE = ("CPU", "cpu", "内存", "帧率", "消费", "诈骗", "交易", "开播地", "辨别",
            "谨防", "诱导", "礼物消息", "展示本场", "主播在直播", "互动消息",
            "说点什么", "发送", "人气榜", "直播广场", "观众",
            "损失", "人身", "财产", "私下", "TOP", "恭喜")

FIX_TABLE = [("氵肖", "消"), ("礻勿", "物"), ("卣", "礼"), ("讠刂", "判"),
             ("小鯨鱼", "小鲸鱼"), ("鯨", "鲸"), ("矬", ""), ("氵去", "法")]

GIFT_KEYS = ("送出", "投喂", "打赏")


def normalize(t):
    for a, b in FIX_TABLE:
        t = t.replace(a, b)
    # OCR 有时会把「名字：」和「：内容」拼成双冒号
    t = t.replace("：：", "：").replace("::", "：").replace(":：", "：")
    return t


def clean(s):
    s = re.sub(r"(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])", "", s)
    return s.strip()


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + msg + chr(10))
    except Exception:
        pass


def bridge_healthy():
    """数据流"真的在出数据"时才让位。
    只看进程活着（心跳）不够——它会连着但一条都收不到，那样两边都不写，全哑。"""
    try:
        return time.time() - os.path.getmtime(os.path.join(BASE, "监听数据.txt")) < 90
    except Exception:
        return False


def dkey(t):
    """去重用的指纹：抹掉 OCR 抖动（x1/×1、空格、标点、开头符号）"""
    k = re.sub(r"^[^\w\u4e00-\u9fa5]+", "", t)
    # 把 ×1 / X5 / ＊3 统一成 x1，但**保留数字**：
    # 数量从 x1 变成 x5 说明又送了，必须能区分出来
    k = re.sub(r"[xX×＊*]\s*(\d+)", r"x\1", k)
    k = re.sub(r"[\s\W_]+", "", k)
    return k


CHAT_MARK = "弹幕｜"      # 评论区里的送礼消息：当弹幕，不当礼物

SYSTEM_START = ("恭喜", "系统", "提示", "欢迎", "本场", "在线观众", "TOP")


def similar(a, b):
    """判两条是不是"同一条被 OCR 认成了两种样子" """
    if a == b:
        return True
    if a in b or b in a:
        return min(len(a), len(b)) / max(1, max(len(a), len(b))) > 0.55
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.78


def starts_new(l):
    if re.match(r"^[^：:]{1,20}[：:]", l):
        return True
    if l.endswith("来了"):
        return True
    if l.startswith(SYSTEM_START):
        return True
    return any(k in l for k in GIFT_KEYS)


def merge_lines(lines):
    """把被 OCR 拆成两行的长弹幕拼回去（只在明显是续行时拼接）"""
    out = []
    for l in lines:
        # 礼物行 / 系统提示行都是完整的，绝不能和上一行拼在一起：
        # 拼起来会变成一个新的指纹，同一条礼物就会被反复当成新礼物
        joinable = (out and not starts_new(l)
                    and not any(k in out[-1] for k in GIFT_KEYS)
                    and not out[-1].startswith(SYSTEM_START)
                    and re.match(r"^[\u4e00-\u9fa5]", l)
                    and not re.search(r"[。！？!?）)]$", out[-1]))
        if joinable:
            out[-1] = out[-1] + l
        else:
            out.append(l)
    return out


def looks_like_danmu(t):
    cjk = sum(1 for c in t if "\u4e00" <= c <= "\u9fff")
    if cjk < 2 or len(t) < 3:      # 昵称常被识别吞掉，3 个字的短弹幕也要收
        return False
    if t.rstrip().endswith(("：", ":")):    # 只认出名字、没认出内容
        return False
    if any(k in t for k in UI_NOISE):
        return False
    if any(k in t for k in GIFT_KEYS):
        return True
    if t.endswith("来了"):
        return True
    if re.search(r"[：:]", t):
        return True
    return False


def region_now():
    try:
        b = tuple(json.load(open(REGION, encoding="utf-8")))
        if b[2] - b[0] > 100:
            return b
    except Exception:
        pass
    return DEFAULT_REGION


_last_small = None
_last_lines = []


def grab_lines(box):
    """用 RapidOCR 识别（中文小字比 Windows OCR 准很多）

    - 画面没变化就复用上次结果：OCR 很吃 CPU，重复识别会把 OBS 拖到掉帧
    - 只识别下半部分：新弹幕总是出现在面板底部，上半部分是旧消息
    """
    global _last_small, _last_lines
    img = ImageGrab.grab(bbox=box).convert("RGB")
    try:
        img.save(SHOT)
    except Exception:
        pass
    small = img.resize((32, 40)).convert("L")
    if _last_small is not None:
        diff = ImageChops.difference(small, _last_small)
        hist = diff.histogram()
        mean = sum(i * c for i, c in enumerate(hist)) / float(small.width * small.height)
        if mean < 3.0:          # 几乎没变化 -> 不重复识别
            return _last_lines
    _last_small = small
    # 不再按上下位置分区（面板高度一变就切歪）。
    # 真礼物那一行长这样：  「花粉宝宝 送出玫瑰 x1」   —— 没有冒号
    # 评论区一律长这样：    「昵称：送出小心心x999」   —— 有冒号
    # 所以用「有没有冒号」判断，跟窗口大小无关，永远准。
    rows = 识屏.rows_of(img)
    raw = []
    for text, cy in rows:
        t = normalize(clean(text))
        if not t:
            continue
        if any(g in t for g in GIFT_KEYS) and ("：" in t or ":" in t):
            # 评论区里说「送出 xxx」：是玩笑或回声，当普通弹幕，不走感谢
            t = CHAT_MARK + t
        raw.append(t)
    _last_lines = merge_lines(raw)
    return _last_lines


def pick():
    import tkinter as tk
    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.attributes("-alpha", 0.25)
    cv = tk.Canvas(root, cursor="cross", bg="grey20", highlightthickness=0)
    cv.pack(fill="both", expand=True)
    st = {}

    def down(e):
        st.update(x=e.x, y=e.y, r=cv.create_rectangle(e.x, e.y, e.x, e.y, outline="red", width=3))

    def move(e):
        if "r" in st:
            cv.coords(st["r"], st["x"], st["y"], e.x, e.y)

    def up(e):
        json.dump([min(st["x"], e.x), min(st["y"], e.y), max(st["x"], e.x), max(st["y"], e.y)],
                  open(REGION, "w", encoding="utf-8"))
        root.destroy()

    cv.bind("<ButtonPress-1>", down)
    cv.bind("<B1-Motion>", move)
    cv.bind("<ButtonRelease-1>", up)
    cv.bind("<Escape>", lambda e: root.destroy())
    root.mainloop()


def main():
    if "--pick" in sys.argv:
        pick(); return
    if "--test" not in sys.argv:
        _single_instance(8799, "弹幕采集")
    box = region_now()
    if "--test" in sys.argv:
        log("TEST region=" + str(box))
        for l in grab_lines(box):
            print(l)
        return

    log("START region=" + str(box))
    prev_counts = Counter()
    lost = {}          # 指纹 -> (消失时的条数, 时间)
    recent = {}        # 指纹 -> 上次写入时间
    recent_text = []   # [(原文, 时间)] 用来做模糊去重
    pending = {}       # 无冒号的行（礼物条/进场）：等下一帧还在才认，防 OCR 空想
    while True:
        try:
            box = region_now()
            raw = grab_lines(box)
            hit = [t for t in raw if looks_like_danmu(t)]
            log("raw " + str(len(raw)) + " hit " + str(len(hit)) + " " + " | ".join(hit)[:140])
            now = time.time()
            # 按「出现次数」比较，而不是「有没有出现过」：
            #   面板上挂着一条不变的  -> 次数没变 -> 不写
            #   同一个人又送了一个同样的礼物（多出一行）-> 次数 +1 -> 写一条
            cur_counts = Counter(dkey(t) for t in hit)

            # OCR 偶尔会漏读一帧：礼物行消失再出现，就会被当成「又送了一个」。
            # 记下刚消失的指纹，12 秒内原样回来的不计数。
            for k, c in prev_counts.items():
                if cur_counts.get(k, 0) == 0:
                    lost[k] = (c, now)
            lost = {k: v for k, v in lost.items() if now - v[1] < 60}

            fresh_counts = {}
            for k, c in cur_counts.items():
                base = prev_counts.get(k, 0)
                lc = lost.get(k)
                if lc and now - lc[1] < 12:
                    base = max(base, lc[0])      # 刚消失过 -> 视为抖动
                d = c - base
                if d > 0:
                    fresh_counts[k] = d
            prev_counts = cur_counts

            recent = {k: v for k, v in recent.items() if now - v < 600}

            # 先把「上一帧挂起、这一帧仍然存在」的确认下来
            for k in list(pending):
                t_p, exp = pending[k]
                if k in cur_counts:
                    with open(DANMU, "a", encoding="utf-8") as f:
                        f.write(t_p + chr(10))
                    print("+ (确认)", t_p)
                    recent_text.append((t_p, now))
                    recent[k] = now
                    del pending[k]
                elif now > exp:
                    del pending[k]

            for t in hit:   # 每条只写一次，多余的由计数差决定
                k = dkey(t)
                if fresh_counts.get(k, 0) <= 0:
                    continue
                fresh_counts[k] -= 1
                # 礼物区是长驻的滚动列表（新礼物顶走旧的），数量变化就代表又来礼物了；
                # 评论区里的送礼消息已经在 grab_lines 里按区域丢掉，不会重复。
                # 这里只留一个很短的冷却，挡 OCR 抖动。
                ttl = 8 if any(g in t for g in GIFT_KEYS) else 30
                if bridge_healthy():
                    continue          # 数据流真的在出消息，OCR 让位
                if k in recent and now - recent[k] < ttl:
                    continue
                # 字认错一个、符号认成别的，指纹就变了。再按"像不像"兜一层：
                # 两分钟内写过高度相似的，就当同一条，不再重复发。
                recent_text = [(x, ts) for x, ts in recent_text if now - ts < 120]
                if any(similar(t, x) for x, _ in recent_text[-40:]):
                    continue
                # 没有冒号的行（礼物条 / 进场提示）：它们会停留好几秒，
                # 要求连续两帧都出现才认，免得 OCR 在静止画面上凭空识出字。
                if "：" not in t and ":" not in t and k not in recent:
                    pending[k] = (t, now + 4)
                    continue
                recent_text.append((t, now))
                recent[k] = now
                with open(DANMU, "a", encoding="utf-8") as f:
                    f.write(t + chr(10))
                print("+", t)
        except KeyboardInterrupt:
            return
        except Exception as e:
            log("ERR " + type(e).__name__ + " " + str(e)[:80])
        time.sleep(0.3)      # 评论只亮 1~2 秒，采样要快，否则会漏


if __name__ == "__main__":
    main()
