# -*- coding: utf-8 -*-
"""把 WssBarrageServer 推送的弹幕流转成 弹幕.txt（替代截屏 OCR）

数据来源：ws://127.0.0.1:8888
格式：{"Type":1,"ProcessName":"直播伴侣","Data":"<json 字符串>"}
  1 弹幕 / 3 进房 / 5 礼物
"""
import json, os, sys, time, threading
import websocket

BASE = os.path.dirname(os.path.abspath(__file__))
DANMU = os.path.join(BASE, "弹幕.txt")
HB = os.path.join(BASE, "监听心跳.txt")
LOG = os.path.join(BASE, "转接日志.txt")
WS = "ws://127.0.0.1:8899"

seen = {}
lock = threading.Lock()


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + msg + "\n")
    except Exception:
        pass


def beat():
    while True:
        try:
            with open(HB, "w", encoding="utf-8") as f:
                f.write(str(time.time()))
        except Exception:
            pass
        time.sleep(1)


def write(line):
    try:
        with open(os.path.join(BASE, "监听数据.txt"), "w", encoding="utf-8") as f:
            f.write(str(time.time()))
    except Exception:
        pass
    with lock:
        with open(DANMU, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    print("+", line, flush=True)


def handle(pack):
    t = pack.get("Type")
    data = pack.get("Data")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            return
    if not isinstance(data, dict):
        return

    user = data.get("User") or {}
    nick = (user.get("Nickname") or "").strip()
    if not nick:
        return

    # 同一个 MsgId 只处理一次（断线重连时会被重复推送）
    mid = data.get("MsgId") or 0
    if mid:
        if mid in seen:
            return
        seen[mid] = time.time()
        if len(seen) > 3000:
            now = time.time()
            for k in [k for k, v in seen.items() if now - v > 3600]:
                seen.pop(k, None)

    if t == 1:                      # 普通弹幕
        content = (data.get("Content") or "").strip()
        if content:
            write(nick + "：" + content)
    elif t == 5:                    # 礼物
        gift = (data.get("GiftName") or "礼物").strip()
        cnt = int(data.get("GiftCount") or 1)
        write("%s 送出 %s x%d" % (nick, gift, cnt))
    elif t == 3:                    # 进房
        write(nick + " 来了")
    else:
        log("其它类型 %s 来自 %s" % (t, pack.get("ProcessName")))


def main():
    threading.Thread(target=beat, daemon=True).start()
    log("START")
    while True:
        try:
            ws = websocket.create_connection(WS, timeout=10)
            ws.settimeout(30)
            log("已连接 " + WS)
            while True:
                raw = ws.recv()
                if not raw:
                    continue
                try:
                    handle(json.loads(raw))
                except Exception as e:
                    log("解析失败 " + type(e).__name__ + " " + str(e)[:60])
        except Exception as e:
            log("断线 " + type(e).__name__ + " " + str(e)[:60])
            time.sleep(3)


if __name__ == "__main__":
    main()
