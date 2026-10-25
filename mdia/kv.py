"""Label -> value detection that works for LTR, RTL and mixed lines.

Words arrive left->right (visual). An English label owns the words to its right; an Arabic label
owns the words to its left (they are printed right-to-left). Gaps between two labels go to the
label that "reads into" them. All labels (any group) delimit each other, so values never leak."""
from dataclasses import dataclass
from typing import List

from .lexicon import LABEL_TABLE
from .model import Line, Page, Word, logical_order
from .textutil import LAT_RE, ar_ratio

_NOISE = {":", "-", "–", "|", "؛", ";", "/", "\\"}


@dataclass
class Match:
    s: int
    e: int
    id: str
    rtl: bool


@dataclass
class KV:
    id: str
    label_words: List[Word]
    value_words: List[Word]           # logical order
    line: Line
    layout: str = "inline"            # inline | below

    @property
    def value_text(self):
        return " ".join(w.text for w in self.value_words).strip()


def find_matches(keys, table) -> List[Match]:
    out, i = [], 0
    while i < len(keys):
        hit = None
        for toks, _id, rtl in table:
            n = len(toks)
            seq = keys[i:i + n]
            if len(seq) < n:
                continue
            if (list(reversed(toks)) if rtl else list(toks)) == seq:
                hit = Match(i, i + n, _id, rtl)
                break
        if hit:
            # Same-id labels repeated inside a value ("Name: Test Patient Four") are
            # ordinary value words, not a second instruction to truncate the name.
            if hit.id != "patient.name" or not any(previous.id == hit.id for previous in out):
                out.append(hit)
            i = hit.e
        else:
            i += 1
    return out


def _owner(a: Match, b: Match):
    """Which of two adjacent labels owns the words between them."""
    if not a.rtl:
        return a          # LTR label on the left reads to its right
    if b.rtl:
        return b          # RTL label on the right reads to its left
    return None           # RTL then LTR: gap belongs to nobody


def _ocr_junk(w: Word) -> bool:
    """Tiny low-confidence OCR fragments / pure symbols are scan noise, not values."""
    if w.method != "ocr":
        return False
    return (not any(c.isalnum() for c in w.text)) or (len(w.text) <= 2 and w.conf < 0.5)


def line_pairs(line: Line) -> List[KV]:
    V = line.words
    ms = find_matches([w.key for w in V], LABEL_TABLE)
    if not ms:
        return []
    owned = {id(m): [] for m in ms}
    first, last = ms[0], ms[-1]
    if first.rtl:
        owned[id(first)] += V[:first.s]
    if not last.rtl:
        owned[id(last)] += V[last.e:]
    for a, b in zip(ms, ms[1:]):
        gap = V[a.e:b.s]
        o = _owner(a, b)
        if o is not None:
            owned[id(o)] += gap
    out = []
    for m in ms:
        vw = [w for w in sorted(owned[id(m)], key=lambda w: w.x0) if w.text not in _NOISE and not _ocr_junk(w)]
        vt = " ".join(w.text for w in vw)
        rtl = ar_ratio(vt) > 0.5 or (line.rtl and not LAT_RE.search(vt))
        for w in vw:
            w.rtl_hint = rtl
        vw = logical_order(vw, rtl)
        if vw and vw[0].text.startswith(":") and len(vw[0].text) > 1:
            pass
        out.append(KV(m.id, V[m.s:m.e], vw, line))
    return out


def page_pairs(page: Page, skip=frozenset()) -> List[KV]:
    pairs = []
    for i, ln in enumerate(page.lines):
        if ln.idx in skip:
            continue
        ps = line_pairs(ln)
        for p in ps:
            if not p.value_words and len(ps) == 1 and i + 1 < len(page.lines):
                nxt = page.lines[i + 1]
                if nxt.idx not in skip and not line_pairs(nxt):
                    lx0 = min(w.x0 for w in p.label_words) - 0.03
                    lx1 = max(w.x1 for w in p.label_words) + 0.20
                    ws = [w for w in nxt.words if lx0 <= w.cx <= lx1]
                    gap = nxt.y - ln.y
                    if ws and gap < ln.height * 3.2:
                        p.value_words, p.layout = ws, "below"
            pairs.append(p)
    return pairs
