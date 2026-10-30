# -*- coding: utf-8 -*-
"""识别文字：优先 RapidOCR（中文小字更准），退而用 Windows OCR
返回按行整合好的文本（同一行的多个框会横向拼起来）
"""
import asyncio
import numpy as np

_rapid = None
_tried = False


def _get_rapid():
    global _rapid, _tried
    if not _tried:
        _tried = True
        try:
            # RapidOCR 构造函数里的 intra_op_num_threads 根本没传给 onnxruntime，
            # 默认会用满所有核（实测吃 10 核，把 OBS 挤到掉帧）。
            # 这里在会话选项层直接限死。
            import rapidocr_onnxruntime.utils as _oru
            _RealSO = _oru.SessionOptions

            class _LimitedSO(_RealSO):
                def __init__(self, *a, **kw):
                    super().__init__(*a, **kw)
                    self.intra_op_num_threads = 2
                    self.inter_op_num_threads = 1

            _oru.SessionOptions = _LimitedSO
            from rapidocr_onnxruntime import RapidOCR
            _rapid = RapidOCR()
        except Exception:
            _rapid = None
    return _rapid


def _group(items, H=None, with_pos=False):
    """items: [(cx, cy, h, x0, text, y0, y1)] -> 按行合并"""
    if not items:
        return []
    items.sort(key=lambda t: t[1])
    rows = []
    for it in items:
        placed = False
        for row in rows:
            if abs(row["cy"] - it[1]) < max(8, row["h"] * 0.6):
                row["items"].append(it)
                row["cy"] = (row["cy"] * (len(row["items"]) - 1) + it[1]) / len(row["items"])
                placed = True
                break
        if not placed:
            rows.append({"cy": it[1], "h": it[2], "items": [it]})
    rows.sort(key=lambda r: r["cy"])
    out = []
    for r in rows:
        r["items"].sort(key=lambda t: t[3])
        # 贴边的行多半被切了一半，丢掉
        if H is not None:
            y0 = min(t[5] for t in r["items"])
            y1 = max(t[6] for t in r["items"])
            if y0 < 6 or y1 > H - 6:
                continue
        text = "".join(t[4] for t in r["items"])
        out.append((text, r["cy"]) if with_pos else text)
    return out


def rows_of(img):
    """识别并带上纵向位置：[(文本, 该行中心 y)]，用来区分上下两个区域"""
    eng = _get_rapid()
    if eng is not None:
        arr = np.array(img.convert("RGB"))
        try:
            res, _ = eng(arr)
        except Exception:
            res = None
        if res:
            items = []
            for box, text, score in res:
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                items.append((sum(xs) / 4, sum(ys) / 4, max(ys) - min(ys), min(xs), text, min(ys), max(ys)))
            return _group(items, arr.shape[0], with_pos=True)
    try:
        import winocr
        big = img.resize((img.width * 3, img.height * 3))
        r = asyncio.run(winocr.recognize_pil(big, "zh-Hans"))
        items = []
        for l in (r.lines or []):
            ws = getattr(l, "words", None) or []
            if ws:
                ys = [w.bounding_rect.y for w in ws]
                xs = [w.bounding_rect.x for w in ws]
                items.append((sum(xs) / len(xs) / 3, sum(ys) / len(ys) / 3, 12, min(xs) / 3, l.text, min(ys) / 3, max(ys) / 3))
            else:
                items.append((0, 0, 12, 0, l.text, 0, 0))
        return _group(items, big.height, with_pos=True)
    except Exception:
        return []


def lines_of(img):
    """只要文本（老接口）"""
    return [t for t, _ in rows_of(img)]


if __name__ == "__main__":
    import sys
    from PIL import ImageGrab
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    box = tuple(map(int, sys.argv[1:5])) if len(sys.argv) >= 5 else (1338, 340, 1712, 832)
    im = ImageGrab.grab(bbox=box).convert("RGB")
    for t in lines_of(im):
        print(t)
