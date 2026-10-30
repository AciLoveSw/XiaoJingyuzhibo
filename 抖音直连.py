# -*- coding: utf-8 -*-
"""抖音直播弹幕直连（纯 Python，不需要管理员）

原理：连抖音网页版直播间的 WebSocket，直接拿结构化消息。
比截屏 OCR 快得多，也不会认错字。任何一步失败，会自动让位给 OCR（见 弹幕采集.py）。
"""
import os, re, subprocess, sys, time, threading

# 给所有 HTTP 请求加硬超时：不加的话，房间状态一变请求会永远卡住，
# 进程还活着但一条消息都收不到（就是之前的"假死"）。
try:
    import requests as _rq
    _orig_req = _rq.Session.request

    def _req_with_timeout(self, method, url, **kw):
        kw.setdefault("timeout", 15)
        return _orig_req(self, method, url, **kw)

    _rq.Session.request = _req_with_timeout
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = HERE
FETCHER = os.path.join(HERE, "_弹幕直连", "DouyinLiveWebFetcher-main")
def _live_id():
    """直播间短号：优先读 房间号.txt（换账号只改这个文件）"""
    p = os.path.join(KIT, "房间号.txt")
    try:
        v = open(p, encoding="utf-8-sig").read().strip()
        if v and v.isdigit():
            return v
    except Exception:
        pass
    return "741627968813"            # 默认：白饭鲸鱼娘


LIVE_ID = _live_id()                 # 直播间短号：live.douyin.com/<这段>

DANMU = os.path.join(KIT, "弹幕.txt")
DATA_HB = os.path.join(KIT, "监听数据.txt")
LOG = os.path.join(KIT, "直连日志.txt")

LAST_EVENT = time.time()
HB = os.path.join(KIT, "直连心跳.txt")
_recent = {}
_gift_seen = {}
_lock = threading.Lock()


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + msg + "\n")
    except Exception:
        pass


def emit(line):
    """写进 弹幕.txt，顺便更新"数据流活着"的时间戳"""
    now = time.time()
    with _lock:
        key = re.sub(r"\s+", "", line)
        last = _recent.get(key)
        if last and now - last < 2:      # 两秒内同样的内容只写一次
            return
        _recent[key] = now
        if len(_recent) > 500:
            for k in [k for k, v in _recent.items() if now - v > 120]:
                _recent.pop(k, None)
        with open(DANMU, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        try:
            with open(DATA_HB, "w", encoding="utf-8") as f:
                f.write(str(now))
        except Exception:
            pass
    print("+", line, flush=True)


RE_CHAT = re.compile(r"^\[(\d+)\](.+?):\s?(.*)$")
RE_GIFT = re.compile(r"^(.+?)\s*送出了\s*(.+?)x(\d+)$")
RE_ENTER = re.compile(r"^\[(\d+)\]\[([^\]]*)\](.+?)\s*进入了直播间$")


def handle(line):
    if "【聊天msg】" in line or "【礼物msg】" in line or "【进场msg】" in line:
        log("收到 " + line[:60])          # 调试：确认消息真的进到处理函数了
    if "【聊天msg】" in line:
        m = RE_CHAT.match(line.split("】", 1)[1].strip())
        if m and m.group(3).strip():
            name, content = m.group(2).strip(), m.group(3).strip()
            text = "%s：%s" % (name, content)
            # 评论区里说「送出小心心x999」是玩梗，不是真礼物：打标记让引擎当弹幕聊
            if any(k in content for k in ("送出", "投喂", "打赏")):
                text = "弹幕｜" + text
            emit(text)
        return
    if "【礼物msg】" in line:
        m = RE_GIFT.match(line.split("】", 1)[1].strip())
        if m:
            who, gift = m.group(1).strip(), m.group(2).strip()
            # 连击时抖音会一条条推过来，同一个人同一种礼物 10 秒内只记一次
            kk = "礼物|" + who + "|" + gift
            now = time.time()
            with _lock:
                if now - _gift_seen.get(kk, 0) < 10:
                    return
                _gift_seen[kk] = now
            emit("%s 送出 %s x%s" % (who, gift, m.group(3)))
        return
    if "【进场msg】" in line:
        m = RE_ENTER.match(line.split("】", 1)[1].strip())
        if m:
            # 进场单独记：一晚上几百人进来，写进弹幕队列会把真弹幕挤掉
            try:
                with _lock:
                    with open(os.path.join(KIT, "进场.txt"), "a", encoding="utf-8") as f:
                        f.write(m.group(3).strip() + "\n")
            except Exception:
                pass
        return


class Tap:
    """拦截子模块的 print：屏幕照旧打印，同时把有用的行抽出来写文件"""
    def __init__(self, real):
        self.real = real
        self.buf = ""

    def write(self, s):
        try:
            self.real.write(s)
        except Exception:
            pass
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            t = line.strip()
            if t.startswith("【"):
                global LAST_EVENT
                LAST_EVENT = time.time()      # 任何一条推送都算"连接还活着"
            try:
                handle(t)
            except Exception as e:
                log("解析失败 %s" % e)

    def flush(self):
        try:
            self.real.flush()
        except Exception:
            pass

    def isatty(self):
        return False


def run_once():
    os.chdir(FETCHER)          # 它按当前目录找 sign.js / webmssdk.js
    sys.path.insert(0, FETCHER)
    from liveMan import DouyinLiveWebFetcher
    room = DouyinLiveWebFetcher(LIVE_ID)
    room.start()


STALE = 90                  # 90 秒收不到任何推送（连统计都没有）就判定连接死了


def _idle():
    try:
        return time.time() - os.path.getmtime(DATA_HB)
    except Exception:
        return 1e9


def child_main():
    """子进程：真正连抖音。父进程会盯着它。"""
    global LAST_EVENT
    LAST_EVENT = time.time()
    sys.stdout = Tap(sys.stdout)

    def beat():
        while True:
            try:
                with open(HB, "w", encoding="utf-8") as f:
                    f.write(str(LAST_EVENT))
            except Exception:
                pass
            time.sleep(10)
    threading.Thread(target=beat, daemon=True).start()

    while True:
        try:
            run_once()
        except Exception as e:
            log("异常 %s %s" % (type(e).__name__, str(e)[:80]))
        log("断开，5 秒后重连")
        time.sleep(5)


def _single_instance(port=8797, name="抖音直连"):
    """防止重复启动（重复连会写两份弹幕）"""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        s.listen(1)
        globals()["_LOCK_SOCK"] = s
        return True
    except OSError:
        print("已经有一个「%s」在运行，本进程退出。" % name)
        return False


def supervisor_main():
    """父进程：房间没开播就反复重试；子进程假死就杀掉重启"""
    log("START live_id=%s" % LIVE_ID)
    while True:
        p = None
        try:
            p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--child"])
            # 盯着：子进程还活着，但超过 STALE 秒没有任何消息 -> 判定连接死了
            while p.poll() is None:
                time.sleep(15)
                try:
                    last = float(open(HB, encoding="utf-8").read().strip())
                except Exception:
                    continue
                # ① 连推送都没有了 -> 连接死了
                if time.time() - last > STALE:
                    log("连接假死（%d 秒无任何推送），重启" % int(time.time() - last))
                    p.kill()
                    break
                # ② 推送还在，但一条消息都没写进 弹幕.txt -> 处理链断了
                #    （这种情况心跳看不出来，只能看输出文件有没有更新）
                try:
                    wrote = os.path.getmtime(os.path.join(KIT, "监听数据.txt"))
                except Exception:
                    wrote = 0
                if wrote and time.time() - wrote > 150:
                    log("有推送但 %d 秒没写出消息，重启" % int(time.time() - wrote))
                    p.kill()
                    break

        except Exception as e:
            log("拉起子进程失败 %s" % e)
        if p is not None:
            try:
                p.wait(timeout=10)
            except Exception:
                pass
        log("子进程退出，5 秒后重启")
        time.sleep(5)


if __name__ == "__main__":
    if "--child" in sys.argv:
        child_main()
    elif _single_instance():
        supervisor_main()
