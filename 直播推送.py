# -*- coding: utf-8 -*-
"""把小鲸鱼说的话推给 OBS：渲染字幕卡 + 让 OBS 重载"""
import base64, hashlib, json, os
import websocket
import 字幕卡


def _pwd():
    import json as _j, os as _o
    try:
        c = _j.load(open(_o.path.join(_o.path.dirname(_o.path.abspath(__file__)), "config.json"),
                         encoding="utf-8-sig"))
        return c.get("obs_password") or ""
    except Exception:
        return ""


PWD = _pwd()
HOST = "ws://127.0.0.1:4455"


def push(text, source="气泡底"):
    img = 字幕卡.render(text)
    try:
        ws = websocket.create_connection(HOST, timeout=4)
        h = json.loads(ws.recv()); d = h["d"]
        salt = d["authentication"]["salt"]; chal = d["authentication"]["challenge"]
        secret = base64.b64encode(hashlib.sha256((PWD + salt).encode()).digest()).decode()
        auth = base64.b64encode(hashlib.sha256((secret + chal).encode()).digest()).decode()
        ws.send(json.dumps({"op": 1, "d": {"rpcVersion": 1, "authentication": auth}}))
        ws.recv()
        ws.send(json.dumps({"op": 6, "d": {"requestType": "SetInputSettings", "requestId": "1",
                                           "requestData": {"inputName": source,
                                                           "inputSettings": {"file": img},
                                                           "overlay": True}}}))
        ws.recv()
        ws.close()
        return True
    except Exception as e:
        print("OBS 推送失败:", e)
        return False
