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
import urllib.parse, urllib.request, urllib.error
from lxml import etree

REPO = sys.argv[1] if len(sys.argv) > 1 else "."
MYMEMORY_EMAIL = os.environ.get("MYMEMORY_EMAIL", "")  # optional, raises MyMemory quota

cjk = re.compile(r"[\u4e00-\u9fff]")
alpha = re.compile(r"[A-Za-z]")
FMT = re.compile(r"%(?:\d+\$)?[sd]")
TAG = re.compile(r"<[^>]+>")
SIMPLE = re.compile(r"\{(\w+)\}")

GTX_OK = True  # refined by probe()
UAPIS_OK = True  # refined by probe(); uapis.cn (free, no key, China-reachable)
MYMEM_OK = True  # refined by fast probe; MyMemory fallback
QUOTA_EXHAUSTED = False  # set True once MyMemory daily quota is hit


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


def _request(url, timeout=15, headers=None, data=None, max_retries=5):
    """GET/POST with 429/5xx exponential backoff. Raises after retries."""
    h = headers or {"User-Agent": "Mozilla/5.0"}
    last = None
    for i in range(max_retries):
        try:
            req = urllib.request.Request(url, data=data, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503, 504):
                wait = min(4 * (2 ** i), 45) + (i % 3)
                print(f"    [429/5xx] retry {i+1}/{max_retries} after {wait}s")
                time.sleep(wait)
                continue
            raise
        except Exception as e:
            last = e
            if i < max_retries - 1:
                time.sleep(3)
                continue
            raise
    raise last


def gtx(q):
    url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode(
        {"client": "gtx", "sl": "en", "tl": "zh-CN", "dt": "t", "q": q})
    data = json.loads(_request(url, 10, {"User-Agent": "Mozilla/5.0"}))
    return "".join(seg[0] for seg in data[0] if seg[0])


def mymem(q):
    params = {"q": q, "langpair": "en|zh-CN"}
    if MYMEMORY_EMAIL:
        params["de"] = MYMEMORY_EMAIL
    url = "https://api.mymemory.translated.net/get?" + urllib.parse.urlencode(params)
    data = json.loads(_request(url, 12, {"User-Agent": "cytv-fix/1.0"}, max_retries=3))
    text = (data.get("responseData") or {}).get("translatedText", "")
    # MyMemory returns the quota warning *inside* translatedText on exhaustion.
    if "MYMEMORY WARNING" in text or "QUOTA" in text.upper():
        global QUOTA_EXHAUSTED
        QUOTA_EXHAUSTED = True
        raise RuntimeError("mymemory quota/warning: " + text[:80])
    if data.get("responseStatus") != 200:
        raise RuntimeError(data.get("responseDetails", "mymemory error"))
    return text


def uapis(q):
    """Free streaming translator at uapis.cn (no key, China-reachable).

    POSTs to /api/v1/translate/stream and concatenates the SSE `content`
    chunks. Returns the first synonym-candidate (uapis emits dictionary-style
    alternatives separated by ；). Retries on 429/5xx with backoff.
    """
    url = "https://uapis.cn/api/v1/translate/stream"
    body = json.dumps({"query": q, "from_lang": "英文", "to_lang": "中文"}).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "cleanyourtv-zh/1.0"}
    last = None
    for i in range(4):
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as r:
                parts = []
                for raw in r:
                    line = raw.decode("utf-8", "ignore").rstrip("\n").rstrip("\r")
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data:
                        continue
                    try:
                        obj = json.loads(data)
                    except Exception:
                        continue
                    if "error" in obj:
                        raise RuntimeError("uapis error: " + str(obj.get("error")))
                    if obj.get("content"):
                        parts.append(obj["content"])
                text = "".join(parts).strip()
                # uapis returns dictionary-style synonyms split by ；; keep first
                if "；" in text:
                    text = text.split("；")[0].strip()
                if not text:
                    raise RuntimeError("uapis empty result")
                return text
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503, 504):
                wait = min(5 * (2 ** i), 25)
                print(f"    [uapis 429] retry {i+1}/4 after {wait}s")
                time.sleep(wait)
                continue
            raise
        except Exception as e:
            last = e
            if i < 5:
                time.sleep(3)
                continue
            raise
    raise last


def _alive(url, data=None, headers=None, timeout=8):
    """One-shot liveness check: True only if the endpoint answers HTTP 200.

    Deliberately does NOT use the backoff-heavy translators, so a rate-limited
    backend is detected in ~timeout seconds instead of after many retries.
    """
    try:
        req = urllib.request.Request(url, data=data, headers=headers or {"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


UAPIS_PROBE_URL = "https://uapis.cn/api/v1/translate/stream"
UAPIS_PROBE_BODY = json.dumps({"query": "hi", "from_lang": "英文", "to_lang": "中文"}).encode("utf-8")
MYMEM_PROBE_URL = "https://api.mymemory.translated.net/get?" + urllib.parse.urlencode(
    {"q": "hi", "langpair": "en|zh-CN"})


def probe_gtx():
    """Fast liveness check for Google gtx (no long backoff)."""
    url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode(
        {"client": "gtx", "sl": "en", "tl": "zh-CN", "dt": "t", "q": "hi"})
    return _alive(url, timeout=6)


def probe_uapis():
    """Return True only if uapis.cn answers a trivial request quickly."""
    try:
        return bool(uapis("hi"))
    except Exception:
        return False


def tr(t):
    if not t.strip() or not alpha.search(t):
        return t
    if QUOTA_EXHAUSTED:
        return t
    backends = ([uapis] if UAPIS_OK else []) + ([gtx] if GTX_OK else []) + ([mymem] if MYMEM_OK else [])
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
    global GTX_OK, UAPIS_OK, MYMEM_OK
    GTX_OK = probe_gtx()
    # Fast, non-backoff liveness probes so a rate-limited backend is detected
    # quickly instead of after many slow retries.
    uapis_alive = _alive(UAPIS_PROBE_URL, data=UAPIS_PROBE_BODY,
                         headers={"Content-Type": "application/json", "User-Agent": "cleanyourtv-zh/1.0"})
    mymem_alive = _alive(MYMEM_PROBE_URL, headers={"User-Agent": "cytv-fix/1.0"})
    UAPIS_OK = uapis_alive
    MYMEM_OK = mymem_alive
    print(f"[probe] gtx={GTX_OK} | uapis.cn={uapis_alive} | mymem={mymem_alive}")
    if not uapis_alive and not mymem_alive:
        print("[abort] both uapis.cn and MyMemory are rate-limited right now; "
              "exiting so the cooldown loop can wait out the window.")
        return
    total = 0
    files = sorted(glob.glob(f"{REPO}/**/values-zh-rCN/*.xml", recursive=True))
    for f in files:
        if "/fixtures/" in f.replace("\\", "/"):
            continue
        if QUOTA_EXHAUSTED:
            print("[abort] MyMemory quota exhausted; stopping to avoid wasted time.")
            break
        try:
            tree = etree.parse(f)
        except Exception as e:
            print("parse fail", f, e); continue
        changed = False
        for el in tree.getroot().iter():
            if QUOTA_EXHAUSTED:
                break
            if el.tag in ("string", "item"):
                t = el.text or ""
                if t and alpha.search(t) and not cjk.search(t):
                    new = tr(t)
                    if new != t:
                        el.text = new
                        changed = True
                        total += 1
                        print(f"  +{total} {el.get('name')}")
                    time.sleep(1.2)  # gentle pace to avoid tripping free-rate limits
        if changed:
            tree.write(f, xml_declaration=True, encoding="utf-8")
    print(f"DONE. translated {total} entries this run.")


if __name__ == "__main__":
    main()
