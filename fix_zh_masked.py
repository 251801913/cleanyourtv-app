#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Safe masked translation for the remaining simple-template strings.

xfyun translates placeholder NAMES too (e.g. {version} -> {版本}), which would
break the app at runtime. This script masks every {placeholder} with a sentinel
xfyun leaves untouched (ZZPH{n}ZZ), translates the prose, then restores the
exact original placeholders. Strings containing ICU `plural`/`#` or printf `%`
tokens are skipped (left in English) because their structure must not be
altered. Only entries that still contain Latin text (untranslated) are touched.
"""
import os, re, sys, glob
from lxml import etree
import fix_zh as F

F.XFYUN_APPID = os.environ.get("XFYUN_APPID", "")
F.XFYUN_API_KEY = os.environ.get("XFYUN_API_KEY", "")
F.XFYUN_API_SECRET = os.environ.get("XFYUN_API_SECRET", "")

REPO = sys.argv[1] if len(sys.argv) > 1 else "."
cjk = re.compile(r"[\u4e00-\u9fff]")
alpha = re.compile(r"[A-Za-z]")
BRACE = re.compile(r"\{[^}]*\}")
SENT = "ZZPH{}ZZ"


def mask(s):
    mapping = []
    def repl(m):
        mapping.append(m.group(0))
        return SENT.format(len(mapping) - 1)
    return BRACE.sub(repl, s), mapping


def translatable(masked):
    stripped = re.sub(r"ZZPH\d+ZZ", "", masked)
    return bool(re.search(r"[a-z]{3,}", stripped))


def restore(masked, mapping):
    for i, orig in enumerate(mapping):
        masked = masked.replace(SENT.format(i), orig)
    return masked


def main():
    total = 0
    files = sorted(glob.glob(f"{REPO}/**/values-zh-rCN/*.xml", recursive=True))
    for f in files:
        if "/fixtures/" in f.replace("\\", "/"):
            continue
        try:
            tree = etree.parse(f)
        except Exception as e:
            print("parse fail", f, e)
            continue
        changed = False
        for el in tree.getroot().iter():
            if el.tag not in ("string", "item"):
                continue
            t = el.text or ""
            if not (t and alpha.search(t) and not cjk.search(t)):
                continue  # already Chinese / empty
            if "plural" in t or "%" in t:
                continue  # ICU plural / printf: unsafe to auto-translate
            masked, mapping = mask(t)
            if not mapping:
                continue  # no placeholders (brand/all-caps) -> leave
            if not translatable(masked):
                continue  # only placeholders, nothing to translate
            try:
                tr = F.xfyun(masked)
            except Exception as e:
                print("  [skip xfyun err]", el.get("name"), e)
                continue
            if not all(SENT.format(i) in tr for i in range(len(mapping))):
                print("  [skip sentinel lost]", el.get("name"))
                continue
            out = restore(tr, mapping)
            if out != t:
                el.text = out
                changed = True
                total += 1
                print(f"  +{total} {el.get('name')}")
        if changed:
            tree.write(f, xml_declaration=True, encoding="utf-8")
    print(f"DONE. masked-translated {total} entries.")


if __name__ == "__main__":
    main()
