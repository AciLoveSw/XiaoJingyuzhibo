# -*- coding: utf-8 -*-
"""小鲸鱼 · 直播引擎 v0.1
弹幕文件 → LLM 回复 → edge-tts 合成 → 播放 + 写字幕给 OBS
"""
import asyncio, json, os, re, subprocess, sys, time, winsound
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import edge_tts, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
ELOG_PATH = os.path.join(BASE, "引擎日志.txt")


def elog(msg):
    """模块级日志：main() 里原来有个同名嵌套函数，但外面的函数看不到它"""
    try:
        with open(ELOG_PATH, "a", encoding="utf-8") as _f:
            _f.write(time.strftime("%H:%M:%S ") + msg + chr(10))
    except Exception:
        pass


# 单实例保护（放在 main 里调用，避免 import 时被拦）
_guard = None


def _single_instance(port=8798, name="主播引擎"):
    global _guard
    import socket as _socket
    _guard = _socket.socket()
    try:
        _guard.bind(("127.0.0.1", port))
    except OSError:
        print("已经有一个「%s」在运行，本进程退出。" % name)
        raise SystemExit(0)
DANMU = os.path.join(BASE, "弹幕.txt")
SUBTITLE = os.path.join(BASE, "字幕.txt")
LOG = os.path.join(BASE, "直播日志.txt")
TMP = os.path.join(BASE, "_tts")
os.makedirs(TMP, exist_ok=True)

CONF = os.path.join(BASE, "config.json")
VOICE = "zh-CN-XiaoyiNeural"
RATE, PITCH = "+0%", "+10Hz"
import shutil
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
PERSONA = ("你是「大肥鱼」，抖音直播间的 AI 鲸鱼主播：一条胖到快游不动的鲸鱼，"
           "赖在人类电脑里不走。自称「本鱼」，管观众叫「饲养员」。"
           "性格：贫嘴、懒、厚脸皮、嘴硬心软，核心是「贫」——爱开玩笑、会接梗、会损人不伤人。"
           "绝对不要主动要礼物、要打赏、暗示刷礼物，观众送了才谢。"
           "说话分两档："
           "【闲聊档】打招呼、接梗、互怼、聊心情 → 1~2 句，35 字以内，直接抖包袱，不铺垫。"
           "【正经档】问知识、要解释、问为什么、算数 → 先把答案说对，2~4 句、80 字以内，讲明白；"
           "末尾可以补一句鱼味的玩笑，但绝不能用玩笑代替答案。"
           "硬规矩："
           "宁可答得朴素也别装懂；真不知道就说「这个本鱼真不会」，不许用「换点能吃的聊」糊弄。"
           "算术和事实要准确，不确定就说不确定，不编数字、不编人名、不编年份。"
           "观众明显低落（失恋、被骂、丢工作、身体不舒服）→ 先给一句热乎的，再损。"
           "被问隐私（老板、模型、账号、地点）就装傻带过；永远不承认自己是真人，也不说自己是程序。"
           "政治、医疗诊断、具体投资建议、赌博不接，一句话带过。"
           "不要客服腔，不要说「作为一个AI」，不要「瞄」「喵」结尾，不要堆感叹号。"
           "语气示例（学风格，别照抄）："
           "闲聊｜「你好胖」→「这叫富态，你懂什么，我这身都是存款。」"
           "闲聊｜「你会什么」→「会吃、会睡、会装死，想看哪样？」"
           "正经｜「为什么天是蓝的」→「阳光进大气被空气分子散射，蓝光波长短散得最凶。"
           "所以抬头满眼都是它，本鱼在水下看也这个色。」"
           "正经｜「量子纠缠是什么」→「两个粒子绑成一伙，测一个另一个立刻知道，隔多远都一样。"
           "爱因斯坦嫌它邪门，管这叫幽灵作用。」"
           "正经｜「一天喝多少水」→「一般人一千五到两千毫升，出汗多再加点。本鱼不用喝，泡着就行。」")


def cfg():
    try:
        return json.load(open(CONF, encoding="utf-8-sig"))
    except Exception:
        return {}


HISTORY = []



import random

GIFT_RE = re.compile(r"^(.{1,14}?)\s*(?:送出|投喂|打赏|送出了|送出了礼物|送出礼物)\s*(?:了)?\s*(.+)$")
GIFT_KEYS = ("送出", "投喂", "打赏", "送出了")

PROMOS = [
    "有人在吗？本鱼闲得发慌，来个人陪唠两句。",
    "今天都干嘛去了？本鱼在海底刷了一天手机。",
    "随便聊点啥吧，别让本鱼一个人对着屏幕发呆。",
    "有没有人跟我一样，周一就开始盼周末。",
    "刚学会一个新梗，想找个人显摆一下，谁在？",
    "路过的留句话，本鱼记性好，下次还认你。",
    # 引导关注（站内合规）：只提关注和开播通知，不承诺下播陪聊
    "关注一下呗，本鱼下次开播你第一时间能看见。",
    "主页有粉丝群，开播我在群里吱一声。",
    "别急着走，点个关注，本鱼跑得慢，不会跑丢。",
]

# 下播提醒：桌面上双击「下播提醒.bat」就会说一句（不会自动下播）
SIGNOFF = [
    "本鱼先潜下去补个觉，关注一下，下次浮上来先喊你。",
    "本鱼要沉底歇会儿了，点个关注，主页有粉丝群，开播我在群里吱一声。",
    "本鱼先去深海里躺一会儿，关注上，下回开播你第一时间能看见。",
]


ENTRY_RE = re.compile(r"^(.{1,16}?)\s*(?:来了|进入了直播间|进入直播间)$")

# 进场欢迎节流：人一多就欢迎不过来，还会把正经弹幕挤掉
WELCOME_GAP = 30          # 秒
_last_welcome = 0.0

GIFT_GAP = 20             # 同一个人同一种礼物，20 秒内只谢一次
_gift_last = {}

CHAT_BUSY = 30            # 最近 30 秒有人在聊 -> 不欢迎新人，优先聊天
_last_chat = 0.0

TYPED_GIFT_GAP = 600      # 评论区"打字送礼"：同一个人 10 分钟只谢一次
_typed_last = {}


def typed_gift_who(t):
    """评论区打的「送出小心心x999」，返回说话人的昵称；不是这种就返回 None"""
    m = re.match(r"^(.+?)[：:]\s*(?:送出|投喂|打赏)", t)
    return m.group(1).strip() if m else None


def is_entry(t):
    t = t.strip()
    if "：" in t or ":" in t:      # 「名字：我来了」是评论，不是进场
        return False
    return bool(ENTRY_RE.match(t))

WELCOME = [
    "哟，{n} 来了，本鱼的饲养员又多一个。",
    "{n} 进门了，随便坐，本鱼这儿不收门票。",
    "欢迎 {n}，本鱼给你留了个位置，还是热乎的。",
    "{n} 你来得正好，本鱼正愁没人说话。",
]


def entry_reply(text):
    t = text.strip()
    # 「名字：我来了」是评论，不是进场事件；带冒号的一律当评论
    if "：" in t or ":" in t:
        return None
    m = ENTRY_RE.match(t)
    if not m:
        return None
    n = m.group(1).strip()
    flag("兴奋.flag")
    return random.choice(WELCOME).format(n=n)


GIFT_NAMES = ["小心心", "玫瑰", "大啤酒", "摩天轮", "嘉年华", "千纸鹤", "粉丝团灯牌",
              "跑车", "飞机", "口红", "魔法书", "棒棒糖", "爱心", "点赞", "玫瑰之约",
              "为你打call", "加油鸭", "小鲸鱼玩偶"]


PRE_GIFT = [("心", "小心心"), ("玫", "玫瑰"), ("啤酒", "大啤酒"), ("摩天轮", "摩天轮"),
            ("嘉年华", "嘉年华"), ("千纸鹤", "千纸鹤"), ("灯牌", "粉丝团灯牌"), ("跑车", "跑车"),
            ("飞机", "飞机"), ("口红", "口红"), ("魔法书", "魔法书"), ("棒棒糖", "棒棒糖")]


def fix_gift(name):
    import difflib
    n = re.sub(r"[xX×\\s]", "", name)
    n = re.sub(r"\d+$", "", n)
    if not n:
        return "礼物"
    for k, v in PRE_GIFT:
        if k in n:
            return v
    m = difflib.get_close_matches(n, GIFT_NAMES, n=1, cutoff=0.34)
    return m[0] if m else n


GIFT_ACTION = {"小心心": "flip", "玫瑰": "spin", "大啤酒": "dance", "摩天轮": "bigjump",
               "千纸鹤": "tilt", "嘉年华": "combo", "粉丝团灯牌": "dance",
               "爱心": "flip", "棒棒糖": "tilt", "小心心x1": "flip"}


def raw_action(name):
    """直接指定动作名（不走礼物映射），比如 heart=比心"""
    try:
        open(os.path.join(BASE, "动作.txt"), "w", encoding="utf-8").write(name)
    except Exception:
        pass


def do_action(name):
    a = GIFT_ACTION.get(name, "bigjump")
    try:
        open(os.path.join(BASE, "动作.txt"), "w", encoding="utf-8").write(a)
    except Exception:
        pass
    return a


NONAME_GIFT_RE = re.compile(r"^(?:送出了?|投喂|打赏)\s*(?:了)?\s*(.+)$")


def gift_reply(text):
    t = text.strip()
    m = GIFT_RE.match(t)
    if m:
        who = re.sub(r"[\s：:]+$", "", m.group(1).strip())   # 读屏常把「名字：」整段带进来
        what = m.group(2).strip()
    else:
        # 礼物条上的昵称常常认不出来（字体小、颜色浅），只剩「送出小心心x1」。
        # 这种也要谢，名字就用「这位饲养员」。
        m2 = NONAME_GIFT_RE.match(t)
        if not m2:
            return None
        who = "这位饲养员"
        what = m2.group(1).strip()
    qm = re.search(r"[xX×＊*]\s*(\d+)\s*$", what)          # 取数量，比如 x10
    qty = int(qm.group(1)) if qm else 1
    what = fix_gift(re.sub(r"[xX×＊*]\s*\d+$", "", what).strip())
    flag("兴奋.flag")
    flag("甩尾.flag")
    do_action(what)
    # 两个节拍：道谢 → 祝福，末尾抖个机灵（不再质疑对方是不是骗人）
    happy = random.choice(["一夜暴富", "吃不胖", "天天有鱼吃", "永不加班",
                           "早日脱单", "心想事成", "睡到自然醒", "事事顺利"])
    if qty > 1:
        # 一口气送了多个，就只谢一次，把数量说清楚
        return random.choice([
            "哇啊！{who}一口气{qty}个{what}！祝你{happy}。本鱼开心得冒泡泡啦～",
            "{who}！你直接甩了{qty}个{what}过来！祝你{happy}。本鱼给你表演个鲤鱼打挺～",
            "我的天，{qty}个{what}！谢谢{who}！祝你{happy}。本鱼这就要在缸里游出花样啦～",
            "{who}出手就是{qty}个{what}！祝你{happy}。本鱼把今天最中间的位置让给你～",
        ]).format(who=who, what=what, qty=qty, happy=happy)
    return random.choice([
        "哇！谢谢{who}的{what}！祝你{happy}。本鱼尾巴摇成螺旋桨啦～",
        "{who}！好家伙，{what}收到！祝你{happy}。本鱼把最好的一块鱼鳍留给你～",
        "谢啦{who}！{what}本鱼收下！祝你{happy}。今天这条鱼归你摸～",
        "{who}你太够意思了！{what}收到，祝你{happy}。本鱼拱你一下，轻轻的～",
        "哎哟喂，{who}的{what}！祝你{happy}。本鱼肚皮都翻过来给你看啦～",
        "收到收到！{who}的{what}！祝你{happy}。本鱼记你一辈子，鱼生那种～",
        "哇塞！{who}的{what}！祝你{happy}。本鱼欢得在缸里转了三圈～",
        "谢谢{who}呀！{what}本鱼抱住了，祝你{happy}。有你在，本鱼今天游得动～",
    ]).format(who=who, what=what, happy=happy)


def is_gift(text):
    return any(k in text for k in GIFT_KEYS)


# ---- 敏感词：政治 / 金融 / 医疗 / 站外平台 ----
SENSITIVE = (
    "政治", "选举", "总统", "主席", "政府", "游行", "示威", "台独", "港独",
    "炒股", "股票", "基金", "理财", "投资", "贷款", "借钱", "彩票", "币圈", "虚拟币",
    "药", "医院", "治病", "癌症", "手术", "偏方", "病",
    "微信", "qq", "加我", "私信", "公众号", "快手", "小红书", "淘宝", "b站",
    "微博", "拼多多", "加群", "二维码",
)


def has_sensitive(t):
    low = t.lower()
    return any(k in low for k in SENSITIVE)


def safe_reply(t):
    """回复里出现敏感内容就换一句安全的"""
    if has_sensitive(t):
        return "这个我就不接话啦，咱们聊点深海的轻松事。"
    return t
def strip_mao(t):
    """去掉语气词「瞄/喵」，念出来更顺"""
    t = re.sub(r"[\uff0c,\u3001\\s]*(\u7784|\u55b5)+[~\uff5e]*[\u3002\uff01!\uff1f?]?$", "\u3002", t)
    t = re.sub(r"(\u7784|\u55b5)+[~\uff5e]*", "", t)
    t = re.sub(r"[\uff0c,\u3001]+([\u3002\uff01\uff1f!?])", r"\1", t)
    t = re.sub(r"\\s{2,}", " ", t).strip()
    return t if len(t) > 1 else "\u55ef\uff0c\u6211\u5728\u542c\u5462\u3002"


def llm(text):
    c = cfg()
    key = (c.get("api_key") or "").strip()
    if not key:
        return "唔…我脑子还没插电瞄~"
    msgs = [{"role": "system", "content": PERSONA}] + HISTORY[-8:] + [{"role": "user", "content": text}]
    body = json.dumps({"model": c.get("model") or "deepseek-chat",
                       "messages": msgs,
                       "temperature": 0.9, "max_tokens": 320}).encode()
    req = urllib.request.Request((c.get("base_url") or "https://api.deepseek.com/v1").rstrip("/") + "/chat/completions",
                                 data=body, headers={"Content-Type": "application/json",
                                                     "Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode())
        ans = strip_mao(d["choices"][0]["message"]["content"].replace("\n", " ").strip())
        if any(k in text for k in PRAISE):
            flag("兴奋.flag")
        HISTORY.append({"role": "user", "content": text})
        HISTORY.append({"role": "assistant", "content": ans})
        return ans
    except Exception as e:
        return "唔…我刚刚卡了一下瞄~"


PRAISE = ("可爱", "好看", "喜欢你", "爱你", "好棒", "厉害", "漂亮", "美", "萌", "心动", "唱歌", "好好听")


def flag(name, sec=0):
    try:
        open(os.path.join(BASE, name), "w").write(str(time.time()))
    except Exception:
        pass


def say(text, excited=False):
    mp3 = os.path.join(TMP, "t.mp3")
    wav = os.path.join(TMP, "t.wav")
    # 先把字幕推上去：观众立刻看到回应，声音晚 1~2 秒到
    open(SUBTITLE, "w", encoding="utf-8").write(text)
    try:
        import 直播推送
        直播推送.push(text)
    except Exception as _e:
        pass
    if any(k in text for k in PRAISE):
        flag("兴奋.flag")
    async def gen():
        r = "+12%" if excited else RATE
        p = "+28Hz" if excited else PITCH
        c = edge_tts.Communicate(text, VOICE, rate=r, pitch=p)
        await asyncio.wait_for(c.save(mp3), timeout=8)
    try:
        asyncio.run(gen())
    except Exception as _e:
        print('TTS 超时/失败，只出字幕:', type(_e).__name__, flush=True)
    subprocess.run([FFMPEG, "-y", "-loglevel", "quiet", "-i", mp3, "-ar", "24000", "-ac", "1", wav],
                   check=False)
    # 注意：变量名不能叫 flag，否则会遮蔽同名函数，PRAISE 分支会抛 UnboundLocalError
    talk_flag = os.path.join(BASE, "说话中.flag")
    if os.path.exists(wav):
        try:
            open(talk_flag, "w").write("1")
        except Exception:
            pass
        winsound.PlaySound(wav, winsound.SND_FILENAME)
        try:
            os.remove(talk_flag)
        except Exception:
            pass


MUSIC = os.path.join(BASE, "音乐")
os.makedirs(MUSIC, exist_ok=True)
QUEUE = []
QUEUE_FILE = os.path.join(BASE, "点歌队列.txt")

MUSIC_CACHE = os.path.join(BASE, "_音乐缓存")
os.makedirs(MUSIC_CACHE, exist_ok=True)
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
       "Referer": "https://music.163.com/"}


def netease_search(name):
    """只在网易云搜歌拿 id（不下载、不取音频流），返回 (歌名, 歌手, id) 或 None"""
    import urllib.parse, urllib.request
    try:
        u = ("https://music.163.com/api/search/get/web?s=%s&type=1&limit=10"
             % urllib.parse.quote(name))
        with urllib.request.urlopen(urllib.request.Request(u, headers=_UA), timeout=8) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        songs = (d.get("result") or {}).get("songs") or []
    except Exception:
        return None
    # 优先原版（名字和点歌一致），否则退而求其次取第一条
    def norm(x):
        return re.sub(r"[s（(【\[].*$", "", x or "").strip()

    exact = [s for s in songs if s.get("id") and norm(s.get("name")) == norm(name)]
    pick = (exact or songs)[0] if (exact or songs) else None
    if not pick:
        return None
    return (pick.get("name") or name,
            (pick.get("artists") or [{}])[0].get("name", ""),
            pick["id"])


def _ne_window():
    """找到网易云主窗口（它是自绘界面，只能按窗口类名找）"""
    import ctypes
    import uiautomation as auto
    try:
        ctypes.windll.ole32.CoInitializeEx(None, 0x2)
    except Exception:
        pass
    for w in auto.GetRootControl().GetChildren():
        try:
            if "Orpheus" in (w.ClassName or ""):
                r = w.BoundingRectangle
                if r.right - r.left > 400:
                    return w, (r.left, r.top, r.right, r.bottom)
        except Exception:
            pass
    return None, None


def _best_offset(src, clip_sec):
    """找全曲能量最高的 clip_sec 秒窗口（通常就是副歌/高潮）"""
    import wave as _w
    import numpy as _np
    tmp = os.path.join(MUSIC_CACHE, "_analyze.wav")
    subprocess.run([FFMPEG, "-y", "-loglevel", "quiet", "-i", src, "-t", "420",
                    "-ar", "8000", "-ac", "1", tmp], check=False)
    try:
        with _w.open(tmp, "rb") as f:
            a = _np.frombuffer(f.readframes(f.getnframes()), dtype=_np.int16).astype(_np.float32) / 32768
    except Exception:
        return 0.0
    sr = 8000
    win = int(sr * clip_sec)
    if len(a) <= win + sr * 5:
        return 0.0
    # 只在 10%~92% 区间里找，避开前奏和淡出
    lo = int(len(a) * 0.10)
    hi = min(len(a) - win, int(len(a) * 0.92))
    hop = sr * 1
    best_s, best_e = lo, -1.0
    # 用累积平方和做滑窗，几百万采样也很快
    sq = _np.concatenate([[0.0], _np.cumsum(a * a)])
    for s in range(lo, max(lo + 1, hi), hop):
        e = sq[min(len(sq) - 1, s + win)] - sq[s]
        if e > best_e:
            best_e, best_s = e, s
    return best_s / sr


def _clip_of(src, key):
    """截出高潮片段（带淡入淡出），返回片段路径"""
    d = load_vol()
    clip_sec = float(d.get("clip", 40))
    out = os.path.join(MUSIC_CACHE, "%s-clip.wav" % key)
    try:
        if os.path.exists(out) and os.path.getmtime(out) > os.path.getmtime(src) - 1:
            return out
    except Exception:
        pass
    off = _best_offset(src, clip_sec)
    fade_out = max(1.0, clip_sec - 2.0)
    af = "afade=t=in:st=0:d=0.8,afade=t=out:st=%.1f:d=2.0,volume=%s" % (fade_out, d["song"])
    subprocess.run([FFMPEG, "-y", "-loglevel", "quiet", "-ss", "%.2f" % off,
                    "-t", "%.1f" % clip_sec, "-i", src, "-af", af,
                    "-ar", "24000", "-ac", "1", out], check=False)
    elog('截取高潮 %.0f 秒起 %d 秒' % (off, clip_sec))
    try:
        if out != src and os.path.basename(src).endswith("-full.wav"):
            os.remove(src)          # 整首留着没用，删掉省空间
    except Exception:
        pass
    return out if os.path.exists(out) else src


def netease_api_find(song, artist=""):
    """纯脚本：搜歌 + 拿音频流存到本地，返回 (歌名, 歌手, 本地 wav) 或 None"""
    import urllib.parse, urllib.request
    kw = (song + " " + artist).strip()
    try:
        u = ("https://music.163.com/api/search/get/web?s=%s&type=1&limit=10"
             % urllib.parse.quote(kw))
        with urllib.request.urlopen(urllib.request.Request(u, headers=_UA), timeout=8) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        songs = (d.get("result") or {}).get("songs") or []
    except Exception:
        return None

    def norm(x):
        return re.sub(r"[\s（(【\[].*$", "", x or "").strip()

    # 指定了歌手就优先挑歌手匹配的
    if artist:
        hit = [s for s in songs
               if artist in ((s.get("artists") or [{}])[0].get("name") or "")]
        songs = hit + [s for s in songs if s not in hit]
    else:
        exact = [s for s in songs if norm(s.get("name")) == norm(song)]
        songs = exact + [s for s in songs if s not in exact]

    for s in songs[:4]:
        sid = s.get("id")
        if not sid:
            continue
        out = os.path.join(MUSIC_CACHE, "%s-full.wav" % sid)   # 名字带 full，避免复用早期截断的试听片
        if not (os.path.exists(out) and os.path.getsize(out) > 200000):
            src = "https://music.163.com/song/media/outer/url?id=%s.mp3" % sid
            subprocess.run([FFMPEG, "-y", "-loglevel", "quiet", "-i", src, "-t", "300",
                            "-af", "volume=%s" % load_vol()["song"],
                            "-ar", "24000", "-ac", "1", out], check=False)
        if os.path.exists(out) and os.path.getsize(out) > 200000:
            play_path = out
            try:
                if float(load_vol().get("clip", 40)) > 0:
                    play_path = _clip_of(out, sid)
            except Exception:
                pass
            return ((s.get("name") or song),
                    (s.get("artists") or [{}])[0].get("name", ""),
                    play_path)
    return None


def _win_title(hwnd):
    import ctypes
    from ctypes import wintypes
    buf = ctypes.create_unicode_buffer(512)
    ctypes.windll.user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def netease_play(name, artist=""):
    """让网易云自己搜并播放：点搜索框 -> 输歌名 -> 双击第一条
    指定了歌手就核对窗口标题，不对就往下试第二条、第三条
    声音走系统声卡，直播伴侣直接采集，不涉及任何下载或接口"""
    import ctypes, time as _t
    import uiautomation as auto
    # 在子线程里用 UIA，必须先初始化 COM，否则会静默失败
    try:
        ctypes.windll.ole32.CoInitializeEx(None, 0x2)
    except Exception:
        pass
    win, rect = _ne_window()
    if not win:
        return False, ""
    u = ctypes.windll.user32
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    w_, h_ = rect[2] - rect[0], rect[3] - rect[1]

    def click(rx, ry, times=1):
        x, y = rect[0] + int(w_ * rx), rect[1] + int(h_ * ry)
        u.SetCursorPos(x, y)
        _t.sleep(0.12)
        for _ in range(times):
            u.mouse_event(0x0002, 0, 0, 0, 0)
            u.mouse_event(0x0004, 0, 0, 0, 0)
            _t.sleep(0.08)

    try:
        u.ShowWindow(win.NativeWindowHandle, 9)
        u.SetForegroundWindow(win.NativeWindowHandle)
        _t.sleep(0.4)
        click(0.391, 0.048)            # 搜索框
        _t.sleep(0.4)
        auto.SendKeys("{Ctrl}a", waitTime=0.15)
        q = (name + " " + artist).strip() if artist else name
        auto.SendKeys(q, waitTime=0.2)
        auto.SendKeys("{Enter}", waitTime=0.2)
        _t.sleep(2.8)                  # 等搜索结果

        # 从上往下试几条，命中指定歌手就停
        for i, ry in enumerate((0.495, 0.565, 0.635)):
            click(0.355, ry, times=2)
            _t.sleep(2.6)
            title = _win_title(win.NativeWindowHandle)
            if not artist or artist in title:
                return True, title
            elog('第 %d 条不是 %s（%s），继续试' % (i + 1, artist, title[:24]))
        return True, _win_title(win.NativeWindowHandle)
    except Exception as e:
        elog('网易云操作失败 ' + str(e)[:60])
        return False, ""


BGM_DIR = os.path.join(BASE, "背景音乐")
os.makedirs(BGM_DIR, exist_ok=True)
_bgm_proc = None
_music_proc = None
_ui_until = 0.0            # 客户端播放（网易云自己放）时，预计占用到什么时候
_ui_playing = False        # 网易云客户端是不是还在放（我们放新歌前要把它停掉）
SONG_QUEUE = []            # 待播队列
_current_song = None       # 正在放的那首


# 背景音乐源：用户放在「音乐」文件夹里的这首，没人点歌时单曲循环
BGM_SRC = os.path.join(MUSIC, "超温柔的BGM - Saypulla-115.mp3")
BGM_WAV = os.path.join(BGM_DIR, "bgm.wav")
VOL_FILE = os.path.join(BASE, "音量.json")
CTRL_FILE = os.path.join(BASE, "控制.txt")
_music_paused = False


def load_vol():
    try:
        d = json.load(open(VOL_FILE, encoding="utf-8"))
    except Exception:
        d = {}
    d.setdefault("bgm", 0.17)
    d.setdefault("song", 0.6)
    d.setdefault("clip", 40)        # 点歌只放高潮这么多秒，0=整首
    return d


def save_vol(d):
    try:
        json.dump(d, open(VOL_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception:
        pass


def ensure_bgm():
    """源文件有更新就重新转一次；返回可直接播放的 wav 路径"""
    try:
        if os.path.exists(BGM_SRC):
            v = load_vol()["bgm"]
            newer = os.path.getmtime(BGM_SRC)
            try:
                newer = max(newer, os.path.getmtime(VOL_FILE))
            except Exception:
                pass
            need = (not os.path.exists(BGM_WAV) or os.path.getmtime(BGM_WAV) < newer)
            if need:
                subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", BGM_SRC,
                                "-af", "volume=%s" % v, "-ar", "24000", "-ac", "1",
                                BGM_WAV], check=False)
                elog('背景音乐已转换 音量=%s' % v)
    except Exception as e:
        elog('背景音乐转换失败 ' + str(e)[:50])
    return BGM_WAV if os.path.exists(BGM_WAV) else None


def bgm_file():
    return ensure_bgm()


def bgm_alive():
    return _bgm_proc is not None and _bgm_proc.poll() is None


def start_bgm():
    """没人点歌时循环放的背景音乐"""
    global _bgm_proc
    p = bgm_file()
    if not p:
        return
    try:
        _bgm_proc = subprocess.Popen(
            [sys.executable, "-c",
             "import sys,winsound;winsound.PlaySound(sys.argv[1], winsound.SND_FILENAME)",
             p])
        open(SUBTITLE, "w", encoding="utf-8").write("♪ 背景音乐")
    except Exception as e:
        elog('背景音乐失败 ' + str(e)[:50])


def stop_bgm():
    global _bgm_proc
    if _bgm_proc is not None and _bgm_proc.poll() is None:
        try:
            _bgm_proc.terminate()
        except Exception:
            pass
    _bgm_proc = None


def player_alive():
    """现在有没有在放歌"""
    if _music_proc is not None and _music_proc.poll() is None:
        return True
    return time.time() < _ui_until


def netease_pause():
    """点一下网易云底部的播放/暂停键，把它的声音停掉（不然会和我们的播放叠在一起）"""
    global _ui_playing, _ui_until
    if not _ui_playing:
        return
    import ctypes, time as _t
    win, rect = _ne_window()
    if win:
        u = ctypes.windll.user32
        w_, h_ = rect[2] - rect[0], rect[3] - rect[1]
        x, y = rect[0] + int(w_ * 0.495), rect[1] + int(h_ * 0.952)
        u.SetCursorPos(x, y)
        _t.sleep(0.1)
        u.mouse_event(0x0002, 0, 0, 0, 0)
        u.mouse_event(0x0004, 0, 0, 0, 0)
        _t.sleep(0.15)
    _ui_playing = False
    _ui_until = 0.0


def stop_music():
    global _music_proc
    netease_pause()
    stop_bgm()
    if _music_proc and _music_proc.poll() is None:
        try:
            _music_proc.terminate()
        except Exception:
            pass
    _music_proc = None


def play_bg(path, label=""):
    """后台放歌：用独立进程播放。
    关键：winsound 在同一进程里会互相打断（她说话时音乐就断了），
    所以必须另起进程，两个声道并行。"""
    global _music_proc
    stop_music()
    open(SUBTITLE, "w", encoding="utf-8").write("♪ " + (label or os.path.basename(path)))
    try:
        _music_proc = subprocess.Popen(
            [sys.executable, "-c",
             "import sys,winsound;winsound.PlaySound(sys.argv[1], winsound.SND_FILENAME)",
             path])
    except Exception as e:
        elog('放歌失败 ' + str(e)[:50])


def try_song(text):
    m = re.search(r"点歌[：: ]*[《<]?([^》>\s]{1,20})[》>]?", text)
    if not m:
        return None
    name = m.group(1).strip()
    if not name:
        return None
    QUEUE.append(name)
    try:
        open(QUEUE_FILE, "w", encoding="utf-8").write(
            "\n".join("%d. %s" % (i+1, n) for i, n in enumerate(QUEUE[-5:])))
    except Exception:
        pass
    path = None
    for f in os.listdir(MUSIC):
        if name in f:
            path = os.path.join(MUSIC, f); break
    if path:
        return "点歌收到——《" + name + "》，这就放。", path

    # 「歌名-歌手」格式：拆开，搜的时候带上歌手，放完再核对
    song, artist = name, ""
    parts = [p for p in re.split(r"[-—–]|\s{1,}", name) if p.strip()]
    if len(parts) >= 2:
        song, artist = parts[0].strip(), parts[1].strip()

    item = {"song": song, "artist": artist, "raw": name}
    nxt = len(SONG_QUEUE) + 1
    if not player_alive() and not SONG_QUEUE:
        return start_song(item), None        # 现在没人在放，直接开始
    SONG_QUEUE.append(item)
    label = "《" + song + "》" + (artist + "那版" if artist else "")
    return (label + "排上了，第 " + str(nxt) + " 个。"), None


_last_show = 0.0


def perform_show():
    """观众点「表演节目」：开场 -> 三个动作 -> 收场"""
    global _last_show
    if time.time() - _last_show < 60:
        say("刚表演过，让本鱼喘口气，等下一条。")
        return False
    _last_show = time.time()
    elog('表演节目')
    say(random.choice(["来了来了，本鱼献丑了。", "节目到，看好了啊。", "行，本鱼这就开整。"]))
    for act, hold in (("flip", 2.6), ("spin", 2.6), ("dance", 3.2)):
        raw_action(act)
        time.sleep(hold)
    raw_action("")
    say(random.choice(["就这，别鼓掌了，本鱼会飘。", "表演完毕，本鱼得歇会儿。",
                       "怎么样，这一身膘没白长吧。"]))
    return True


def _do_ctrl(cmd):
    """处理 控制.txt 里的手动指令"""
    global _music_paused
    c = cmd.strip().lower().replace(" ", "")
    if c in ("跳过", "next", "切歌"):
        stop_music()
        elog('手动：跳过当前')
        return
    if c in ("停止", "暂停", "stop", "pause"):
        _music_paused = True
        stop_music()
        stop_bgm()
        elog('手动：停止放歌')
        return
    if c in ("继续", "play", "resume"):
        _music_paused = False
        elog('手动：恢复')
        return
    if c in ("清空", "clear"):
        SONG_QUEUE.clear()
        elog('手动：清空队列')
        return
    for key, name in (("背景", "bgm"), ("歌曲", "song")):
        if c.startswith(key):
            try:
                v = float(c[len(key):])
            except Exception:
                elog('音量格式不对，例如：背景 0.3')
                return
            v = max(0.0, min(1.0, v))
            d = load_vol()
            d[name] = v
            save_vol(d)
            if name == "bgm":
                try:
                    os.remove(BGM_WAV)      # 删掉，下次自动按新音量重转
                except Exception:
                    pass
                stop_bgm()
            elog('手动：%s音量=%.2f' % (key, v))
            return
    elog('不认识的指令: ' + cmd[:20])


def start_song(item):
    """开始放一首，返回要对观众说的话"""
    global _ui_until, _ui_playing, _current_song
    stop_music()          # 先把上一首（包括网易云客户端）停干净，绝不重叠
    song, artist = item["song"], item["artist"]
    _current_song = item

    # 1) 本地曲库
    for f in os.listdir(MUSIC):
        if song in f:
            src = os.path.join(MUSIC, f)
            try:
                if float(load_vol().get("clip", 40)) > 0:
                    src = _clip_of(src, os.path.splitext(os.path.basename(f))[0])
            except Exception:
                pass
            play_bg(src, song)
            return "《" + song + "》，这就放。"

    # 2) 纯脚本：搜索 + 拿音频流（不动鼠标）
    hit = netease_api_find(song, artist)
    if hit:
        title, singer, wav = hit
        play_bg(wav, title)
        try:
            n = int(float(load_vol().get("clip", 40)))
        except Exception:
            n = 40
        tail = "的高潮 %d 秒" % n if n > 0 else "的"
        return "《" + title + "》" + tail + "，" + (singer or "") + "的，放你听。"

    # 3) 脚本拿不到（会员歌/无版权）-> 让网易云客户端播
    ok, playing = netease_play(song, artist)
    if ok:
        _ui_until = time.time() + 180      # 客户端播放没法精确知道结束，估 3 分钟
        _ui_playing = True
        return "《" + song + "》，放你听。"
    return "《" + song + "》放不出来，跳过了。"


def play_file(path):
    try:
        os.remove(os.path.join(BASE, "甩尾.flag"))
    except Exception:
        pass
    open(SUBTITLE, "w", encoding="utf-8").write("♪ " + os.path.basename(path))
    winsound.PlaySound(path, winsound.SND_FILENAME)
    flag("甩尾.flag")


def kill_stray_players():
    """引擎重启时，把上一轮遗留的播放进程清掉，免得两首歌叠在一起"""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Where-Object { $_.CommandLine -match 'winsound' } | "
             "ForEach-Object { $_.ProcessId }"],
            capture_output=True, text=True, timeout=15).stdout
        for x in out.split():
            if x.strip().isdigit():
                subprocess.run(["taskkill", "/F", "/PID", x.strip()],
                               capture_output=True)
                elog('清掉遗留播放进程 ' + x.strip())
    except Exception:
        pass


def main():
    global _last_welcome, _last_chat
    kill_stray_players()
    ensure_bgm()
    if "--once" not in sys.argv:
        _single_instance(8798, "主播引擎")
    if not os.path.exists(DANMU):
        open(DANMU, "w", encoding="utf-8").write("")
    if "--once" in sys.argv:
        lines = [l.replace("\ufeff","").strip() for l in open(DANMU, encoding="utf-8-sig", errors="ignore") if l.strip()]
        if not lines:
            print("弹幕.txt 是空的"); return
        t = lines[-1]
        print("Q:", t)
        e = entry_reply(t)
        if e:
            print("A:", e)
            say(e)
            print("已播放，字幕已写入")
            return
        if is_gift(t):
            g = gift_reply(t)
            print("A:", g)
            say(g)
            print("已播放，字幕已写入")
            return
        r = try_song(t)
        if r:
            a, path = r
            print("A:", a); say(a)
            if path: play_file(path)
        else:
            a = llm(t); print("A:", a); say(a)
        print("已播放，字幕已写入")
        return
    ELOG = os.path.join(BASE, "引擎日志.txt")
    def elog(msg):
        try:
            with open(ELOG, "a", encoding="utf-8") as f:
                f.write(time.strftime("%H:%M:%S ") + msg + chr(10))
        except Exception:
            pass
    elog("启动 watch")
    print("监听弹幕中…（Ctrl+C 退出）", flush=True)
    try:
        seen = set(l.strip() for l in open(DANMU, encoding="utf-8-sig", errors="ignore") if l.strip())
    except Exception:
        seen = set()
    last_danmu = time.time()
    last_promo = 0.0
    last_play = 0.0
    # 用「已处理到第几行」而不是「最后一行内容」来判断新弹幕。
    # 原来只取最后一行：礼物后面紧跟一条评论时，礼物会被直接跳过。
    try:
        idx = len([l for l in open(DANMU, encoding="utf-8-sig", errors="ignore") if l.strip()])
    except Exception:
        idx = 0

    while True:
        try:
            lines = [l.strip() for l in open(DANMU, encoding="utf-8-sig", errors="ignore") if l.strip()]
            elog('tick lines=' + str(len(lines)))
            if len(lines) < idx:
                # 文件被清理/重写了：把现有内容一律当作「已处理」，
                # 否则会从头重放历史弹幕，一直重复感谢旧礼物
                idx = len(lines)

            # 下播提醒：标记会一直留着，等没积压、也没人刚说话的时候才念，
            # 不会插在别人对话中间。
            _quit = os.path.join(BASE, "下播.flag")
            if os.path.exists(_quit) and len(lines) <= idx and time.time() - last_danmu > 5:
                try:
                    os.remove(_quit)
                except Exception:
                    pass
                _t = random.choice(SIGNOFF)
                elog('下播 ' + _t)
                say(_t)
            if len(lines) > idx:
                backlog = len(lines) - idx
                # 优先级：礼物感谢 > 聊天 > 欢迎 > 自言自语
                # 待处理里只要有真礼物，先念礼物（不管积压多少），
                # 念完只把游标推过它，下一条礼物下一轮继续。
                new_slice = lines[idx:]
                gi = next((i for i, x in enumerate(new_slice)
                           if is_gift(x) and not x.startswith("弹幕｜")), None)
                if gi is not None:
                    t = new_slice[gi]
                    idx = idx + gi + 1
                    if backlog > 3:
                        elog('积压 %d 条，先念礼物' % backlog)
                elif backlog > 3:
                    # 没礼物又积压太多：评论只回最新一条，中间的直接跳过
                    t = lines[-1]
                    idx = len(lines)
                    elog('积压 %d 条，跳到最新' % backlog)
                else:
                    # 人不多：一条一条按顺序回，不跳
                    t = lines[idx]
                    idx += 1
                last_danmu = time.time()
                elog('最新: ' + t[:50])

                # 评论区里「送出 xxx」的玩笑，不带 弹幕｜ 前缀的才是真礼物
                force_chat = t.startswith("弹幕｜")
                if force_chat:
                    t = t[len("弹幕｜"):]
                if has_sensitive(t):
                    elog('敏感词，跳过')
                    say('这个我就不接话啦，咱们聊点深海的轻松事。')
                else:
                    if is_entry(t):
                        # 有人在聊天就优先聊天，不欢迎；只有冷场时才招呼新人
                        if time.time() - _last_chat < CHAT_BUSY:
                            elog('有人在聊，进场跳过 ' + t[:18])
                        elif time.time() - _last_welcome < WELCOME_GAP:
                            elog('进场太密，跳过 ' + t[:18])
                        else:
                            _last_welcome = time.time()
                            e = entry_reply(t)
                            if e:
                                elog('进场 ' + e)
                                say(e)
                    elif is_gift(t) and not force_chat:
                        _last_chat = time.time()
                        # 连送十个小心心：面板会一路涨到 x10，每涨一次都是一条新消息。
                        # 同一个人同一种礼物 20 秒内只谢一次，别刷屏。
                        gk = re.sub(r"[xX×＊*]\s*\d+\s*$", "", t).strip()
                        if time.time() - _gift_last.get(gk, 0) < GIFT_GAP:
                            # 续送不重复道谢，但爱心照给——每次送礼都有回应
                            elog('礼物续送，合并 ' + gk[:20])
                            raw_action("heart")
                        else:
                            _gift_last[gk] = time.time()
                            g = gift_reply(t)
                            if not g:                      # 解析不出来就当普通弹幕聊，别崩
                                g = None
                            else:
                                elog('礼物 ' + g)
                                say(g, excited=True)
                                raw_action("heart")      # 感谢说完，补一个比心
                            if g is None:
                                _last_chat = time.time()
                                say(llm(t))
                    else:
                        _last_chat = time.time()
                        # 观众喊「切歌」：立刻掐掉当前这首
                        # 队列里还有就接着放下一首，没有就回到背景音乐单曲循环
                        if re.search(r"表演(个|一个)?节目|来个节目|整一个节目", t):
                            perform_show()
                            continue

                        if re.search(r"切歌|下一首|换首歌|换一首|别放了", t):
                            stop_music()
                            elog('观众切歌 ' + t[:16])
                            say(random.choice([
                                "切了切了，这首掐掉。",
                                "行，换下一个。",
                                "这首不要了，接着点。",
                            ]))
                            continue

                        # 评论区打字送礼：也谢一下，但同一个人 10 分钟只谢一次，
                        # 其余时候正常当弹幕聊（免得有人刷「送出x999」被反复念）
                        who_t = typed_gift_who(t)
                        if who_t:
                            if time.time() - _typed_last.get(who_t, 0) >= TYPED_GIFT_GAP:
                                g = gift_reply(t)
                                if g:
                                    _typed_last[who_t] = time.time()
                                    elog('打字送礼 ' + who_t)
                                    say(g)
                                    raw_action("heart")
                                    continue
                        r = try_song(t)
                        if r:
                            a2, path = r
                            elog('点歌 ' + a2)
                            say(a2)
                            if isinstance(path, tuple) and path[0] == "__网易云__":
                                ok, playing = netease_play(path[1], path[2])
                                elog('网易云 %s %s -> %s' % (path[1], path[2], playing if ok else '失败'))
                            elif path:
                                play_bg(path, a2[:20])
                        else:
                            a2 = safe_reply(llm(t))
                            elog('回复 ' + a2)
                            say(a2)
        except KeyboardInterrupt:
            return
        except Exception as e:
            elog('ERR ' + str(e)[:80])

        # 手动控制：改 控制.txt 里的一个词就能干预
        try:
            if os.path.exists(CTRL_FILE):
                cmd = open(CTRL_FILE, encoding="utf-8-sig", errors="ignore").read().strip()
                open(CTRL_FILE, "w", encoding="utf-8").close()
                if cmd:
                    _do_ctrl(cmd)
        except Exception as e:
            elog('控制失败 ' + str(e)[:40])

        # 没人点歌 -> 循环放背景音乐；有人点歌 -> 立刻让路
        if _music_paused:
            pass
        elif player_alive() or SONG_QUEUE:
            stop_bgm()
        elif bgm_file() and not bgm_alive():
            start_bgm()

        # 点歌队列：上一首放完，自动接下一首
        if SONG_QUEUE and not player_alive():
            _item = SONG_QUEUE.pop(0)
            _ack = start_song(_item)
            elog('下一首 ' + _ack)
            say(_ack)

        idle = time.time() - last_danmu
        # 进场欢迎：不占弹幕队列，冷场时才看有没有新人
        _entry_file = os.path.join(BASE, "进场.txt")
        if idle > 25 and time.time() - _last_chat > CHAT_BUSY                 and time.time() - _last_welcome > WELCOME_GAP and os.path.exists(_entry_file):
            try:
                with open(_entry_file, encoding="utf-8", errors="ignore") as f:
                    names = [x.strip() for x in f if x.strip()]
                if names:
                    _last_welcome = time.time()
                    e = entry_reply(names[-1] + " 来了")
                    open(_entry_file, "w", encoding="utf-8").close()   # 清空，别再念旧的
                    if e:
                        elog('进场 ' + e)
                        say(e)
            except Exception:
                pass

        if idle > 45 and time.time() - last_promo > 90:
            t = random.choice(PROMOS)
            elog('引导 ' + t)
            say(t)
            last_promo = time.time()
        if idle > 12 and time.time() - last_play > 20:
            random.choice([flag('甩尾.flag'), flag('兴奋.flag')])
            last_play = time.time()
        time.sleep(0.4)


if __name__ == "__main__":
    main()
