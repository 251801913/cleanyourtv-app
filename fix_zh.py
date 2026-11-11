#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Finish the zh-rCN translation of this repo.

Translates only entries still in English (no CJK) in every
res/values-zh-rCN/*.xml. Idempotent: re-running only fills gaps.

Backends (in order, after a one-time reachability probe):
  - Google Translate (gtx, no key)   -> used if reachable
  - MyMemory (free, no key)           -> always tried as fallback

On a China sandbox Google is often blocked while MyMemory is reachable
(but daily-quota limited). A startup probe detects gtx reachability so we
don't waste ~40s per string on dead timeouts. Every translation is checked
for placeholder integrity (ICU {name}, %s, HTML tags); failures keep the
English source instead of writing a corrupt string.

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

GTX_OK = True  # refined by probe()


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


def _get(url, timeout, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def gtx(q):
    url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode(
        {"client": "gtx", "sl": "en", "tl": "zh-CN", "dt": "t", "q": q})
    data = json.loads(_get(url, 10, {"User-Agent": "Mozilla/5.0"}))
    return "".join(seg[0] for seg in data[0] if seg[0])


def mymem(q):
    params = {"q": q, "langpair": "en|zh-CN"}
    if MYMEMORY_EMAIL:
        params["de"] = MYMEMORY_EMAIL
    url = "https://api.mymemory.translated.net/get?" + urllib.parse.urlencode(params)
    data = json.loads(_get(url, 12, {"User-Agent": "cytv-fix/1.0"}))
    text = (data.get("responseData") or {}).get("translatedText", "")
    # MyMemory returns the quota warning *inside* translatedText on exhaustion.
    if "MYMEMORY WARNING" in text or "QUOTA" in text.upper():
        raise RuntimeError("mymemory quota/warning: " + text[:80])
    if data.get("responseStatus") != 200:
        raise RuntimeError(data.get("responseDetails", "mymemory error"))
    return text


def probe_gtx():
    """Return True only if gtx answers a trivial request quickly."""
    try:
        return bool(gtx("hi"))
    except Exception:
        return False


def tr(t):
    if not t.strip() or not alpha.search(t):
        return t
    backends = ([gtx] if GTX_OK else []) + [mymem]
    for fn in backends:
        for attempt in range(2):
            try:
                cand = fn(t)
                if cand and validate(t, cand):
                    return cand
            except Exception:
                pass
            time.sleep(0.8)
    return t


def main():
    global GTX_OK
    GTX_OK = probe_gtx()
    print(f"[probe] Google gtx reachable: {GTX_OK}  (will use MyMemory fallback regardless)")
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
                    time.sleep(0.35)  # gentle pace for MyMemory free rate limit
        if changed:
            tree.write(f, xml_declaration=True, encoding="utf-8")
    print(f"DONE. translated {total} entries this run.")


if __name__ == "__main__":
    main()
