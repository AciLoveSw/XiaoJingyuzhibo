# -*- coding: utf-8 -*-
"""直播素材服务：/state 给情绪信号，其余路径给网页和图片（同源，避免 CORS）"""
import http.server, json, os, socketserver, time

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = {"talking": "说话中.flag", "excited": "兴奋.flag", "wag": "甩尾.flag"}
ACTION = "动作.txt"
TTL = {"talking": 0.08, "excited": 2.2, "wag": 0.9}


def fresh(name):
    p = os.path.join(BASE, FLAGS[name])
    if name == "talking":
        # 说话期间文件一直存在，直接看存在性
        return os.path.exists(p)
    try:
        dt = time.time() - os.path.getmtime(p)
        return 0 <= dt < TTL[name]
    except Exception:
        return False


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=BASE, **kw)

    def recent_lines(self, n=3):
        try:
            lines = [l.strip() for l in open(os.path.join(BASE, "弹幕.txt"),
                     encoding="utf-8-sig", errors="ignore") if l.strip()]
            # 「弹幕｜」是内部标记（区分评论区玩笑和真礼物），画面上不用露出来
            return [l.replace("弹幕｜", "") for l in lines[-n:]]
        except Exception:
            return []

    def current_action(self):
        p = os.path.join(BASE, ACTION)
        try:
            if time.time() - os.path.getmtime(p) < 2.5:
                return open(p, encoding="utf-8").read().strip()
        except Exception:
            pass
        return ""

    def do_GET(self):
        if self.path.startswith("/state"):
            data = {k: fresh(k) for k in FLAGS}
            data["action"] = self.current_action()
            data["recent"] = self.recent_lines()
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", 8788), H) as s:
        print("http://127.0.0.1:8788/形象.html")
        s.serve_forever()
