#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Finish the zh-rCN translation of this repo.

Translates only entries still in English (no CJK) in every
res/values-zh-rCN/*.xml. Idempotent: re-running only fills gaps.

Backends (in order): Google Translate (gtx, no key) -> MyMemory.
On the sandbox Google is blocked and MyMemory may be quota-limited; on your
own machine Google gtx usually works and will finish all strings in one pass.

Usage (run from this repo's root directory):
  python3 fix_zh.py
"""
import os, re, sys, json, time, glob
import urllib.parse, urllib.request
from lxml import etree

REPO = sys.argv[1] if len(sys.argv) > 1 else "."
MYMEMORY_EMAIL = os.environ.get("MYMEMORY_EMAIL", "")  # optional, raises MyMemory quota

cjk = re.compile(r"[\u4e00-\u9fff]")
alpha = re.compile(r"[A-Za-z]")
FMT = re.compile(r"%(?:\d+\$)?[sd]")
TAG = re.compile(r"<[^>]+>")
SIMPLE = re.compile(r"\{(\w+)\}")


def validate(src, dst):
    if not dst:
        return False
    if FMT.findall(src) != FMT.findall(dst):
        return False
    if sorted(TAG.findall(src)) != sorted(TAG.findall(dst)):
        return False
    if src.count("{") != dst.count("{") or src.count("}") != dst.count("}"):
        return False
    if sorted(SIMPLE.findall(src)) != sorted(SIMPLE.findall(dst)):
        return False
    return True


def gtx(q):
    url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode(
        {"client": "gtx", "sl": "en", "tl": "zh-CN", "dt": "t", "q": q})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    return "".join(seg[0] for seg in data[0] if seg[0])


def mymem(q):
    params = {"q": q, "langpair": "en|zh-CN"}
    if MYMEMORY_EMAIL:
        params["de"] = MYMEMORY_EMAIL
    url = "https://api.mymemory.translated.net/get?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "cytv-fix/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    if data.get("responseStatus") == 200:
        return data["responseData"]["translatedText"]
    raise RuntimeError(data.get("responseDetails", "mymemory error"))


def tr(t):
    if not t.strip() or not alpha.search(t):
        return t
    out = t
    for fn in (gtx, mymem):
        for attempt in range(2):
            try:
                cand = fn(t)
                if cand and validate(t, cand):
                    return cand
            except Exception:
                pass
            time.sleep(1.0)
    return out


def main():
    total = 0
    files = sorted(glob.glob(f"{REPO}/**/values-zh-rCN/*.xml", recursive=True))
    for f in files:
        if "/fixtures/" in f.replace("\\", "/"):
            continue
        try:
            tree = etree.parse(f)
        except Exception as e:
            print("parse fail", f, e); continue
        changed = False
        for el in tree.getroot().iter():
            if el.tag in ("string", "item"):
                t = el.text or ""
                if t and alpha.search(t) and not cjk.search(t):
                    new = tr(t)
                    if new != t:
                        el.text = new
                        changed = True
                        total += 1
                        print(f"  +{total} {el.get('name')}")
        if changed:
            tree.write(f, xml_declaration=True, encoding="utf-8")
    print(f"DONE. translated {total} entries this run.")


if __name__ == "__main__":
    main()
