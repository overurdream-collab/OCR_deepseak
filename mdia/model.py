"""Layout model shared by reader, extractors and exporters. Coordinates are page-relative (0..1)."""
from dataclasses import dataclass, field, asdict
from typing import List, Optional

import re
from typing import Optional

from .textutil import has_ar, ar_ratio, match_key, LAT_RE


@dataclass
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    conf: float = 1.0
    method: str = "text-layer"     # text-layer | ocr
    key: str = ""
    rtl_hint: Optional[bool] = None   # reading direction of the table/line this word belongs to
    box: Optional[list] = None        # bbox in ORIGINAL page space when layout was analysed on a deskewed image

    def __post_init__(self):
        if not self.key:
            self.key = match_key(self.text)

    @property
    def cx(self):
        return (self.x0 + self.x1) / 2

    @property
    def cy(self):
        return (self.y0 + self.y1) / 2


def union_bbox(words):
    if not words:
        return None
    if all(w.box for w in words):           # deskewed OCR: report positions on the original (preview) image
        return [round(min(w.box[0] for w in words), 5), round(min(w.box[1] for w in words), 5),
                round(max(w.box[2] for w in words), 5), round(max(w.box[3] for w in words), 5)]
    return [round(min(w.x0 for w in words), 5), round(min(w.y0 for w in words), 5),
            round(max(w.x1 for w in words), 5), round(max(w.y1 for w in words), 5)]


def logical_order(words_asc, rtl: bool):
    """Words given left->right; return them in reading (logical) order.
    In RTL context each Arabic word and each stand-alone number is its own run (runs read right->left),
    while a run containing Latin letters (e.g. "Complete Blood Count", "Type 2") keeps its own order."""
    if not rtl:
        return list(words_asc)
    lat = [bool(LAT_RE.search(w.text)) for w in words_asc]
    groups, cur_lat = [], False
    for i, w in enumerate(words_asc):
        latin_run = (not has_ar(w.text)) and (lat[i] or (i > 0 and lat[i - 1] and not has_ar(words_asc[i - 1].text))
                                              or (i + 1 < len(words_asc) and lat[i + 1] and not has_ar(words_asc[i + 1].text)))
        if latin_run and groups and cur_lat:
            groups[-1].append(w)
        else:
            groups.append([w])
        cur_lat = latin_run
    return [w for g in reversed(groups) for w in g]


def join_words(words_asc, rtl=None):
    if rtl is None:
        hints = [w.rtl_hint for w in words_asc if w.rtl_hint is not None]
        rtl = hints[0] if hints else ar_ratio(" ".join(w.text for w in words_asc)) > 0.5
    return " ".join(w.text for w in logical_order(words_asc, rtl))


@dataclass
class Line:
    page: int
    idx: int
    words: List[Word]            # ascending x
    rtl: bool = False

    @property
    def text(self):
        return join_words(self.words, self.rtl)

    @property
    def bbox(self):
        return union_bbox(self.words)

    @property
    def y(self):
        return sum(w.cy for w in self.words) / len(self.words)

    @property
    def height(self):
        return max(w.y1 - w.y0 for w in self.words)

    @property
    def conf(self):
        return sum(w.conf for w in self.words) / len(self.words)


@dataclass
class Page:
    number: int
    width: float
    height: float
    method: str = "text-layer"          # text-layer | ocr | none
    words: List[Word] = field(default_factory=list)
    lines: List[Line] = field(default_factory=list)
    flags: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    text_hash: str = ""
    image: str = ""

    @property
    def text(self):
        return "\n".join(l.text for l in self.lines)

    def to_cache(self):
        return {"number": self.number, "width": self.width, "height": self.height, "method": self.method,
                "flags": self.flags, "warnings": self.warnings, "text_hash": self.text_hash, "image": self.image,
                "words": [asdict(w) for w in self.words]}

    @staticmethod
    def from_cache(d):
        p = Page(d["number"], d["width"], d["height"], d["method"], [Word(**w) for w in d["words"]],
                 flags=d["flags"], warnings=d["warnings"], text_hash=d["text_hash"], image=d["image"])
        p.lines = build_lines(p.words, p.number)
        return p


def build_lines(words: List[Word], page_no: int) -> List[Line]:
    if not words:
        return []
    hs = sorted(w.y1 - w.y0 for w in words)
    med = hs[len(hs) // 2]
    tol = max(med * 0.55, 0.002)
    ws = sorted(words, key=lambda w: w.cy)
    groups, cur = [], [ws[0]]
    for w in ws[1:]:
        mean = sum(x.cy for x in cur) / len(cur)
        if abs(w.cy - mean) <= tol:
            cur.append(w)
        else:
            groups.append(cur)
            cur = [w]
    groups.append(cur)
    lines = []
    for i, g in enumerate(groups):
        g.sort(key=lambda w: w.x0)
        txt = " ".join(w.text for w in g)
        lines.append(Line(page_no, i, g, rtl=ar_ratio(txt) > 0.5))
    return lines
