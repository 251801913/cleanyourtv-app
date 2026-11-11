#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify that placeholders survived translation: ICU braces balance,
printf %s/%d tokens, and HTML tags. Reports any mismatch per key.

Usage (run from this repo's root directory):
  python3 verify_zh.py
"""
import os, re, sys
from lxml import etree

REPO = sys.argv[1] if len(sys.argv) > 1 else "."
FMT = re.compile(r"%(?:\d+\$)?[sd]")
TAG = re.compile(r"<[^>]+>")
SIMPLE = re.compile(r"\{(\w+)\}")


def collect(path):
    d = {}
    try:
        tree = etree.parse(path)
    except Exception:
        return None
    for el in tree.getroot().iter():
        if el.tag in ("string", "item"):
            name = el.get("name")
            if name is None:
                continue
            d[name] = el.text or ""
    return d


issues = []
for base, _, fs in os.walk(REPO):
    if "/fixtures/" in base.replace("\\", "/"):
        continue
    for f in fs:
        if f.startswith("strings") and f.endswith(".xml"):
            if not re.search(r"[/\\]res[/\\]values", base):
                continue
            en = os.path.join(base, f)
            zh = os.path.abspath(os.path.join(base, "..", "values-zh-rCN", f))
            if not os.path.exists(zh):
                issues.append(f"(missing zh file) {en}")
                continue
            de, dz = collect(en), collect(zh)
            if de is None or dz is None:
                continue
            for k in de:
                if k not in dz:
                    issues.append(f"(missing key) {k}  in {en}")
                    continue
                e, z = de[k], dz[k]
                if FMT.findall(e) != FMT.findall(z):
                    issues.append(f"(printf) {k}: EN={e!r} | ZH={z!r}")
                if sorted(TAG.findall(e)) != sorted(TAG.findall(z)):
                    issues.append(f"(tag) {k}: EN={e!r} | ZH={z!r}")
                if e.count("{") != z.count("{") or e.count("}") != z.count("}"):
                    issues.append(f"(icu-brace) {k}: EN={e!r} | ZH={z!r}")
                if sorted(SIMPLE.findall(e)) != sorted(SIMPLE.findall(z)):
                    issues.append(f"(icu-arg) {k}: EN={e!r} | ZH={z!r}")
            for k in dz:
                if k not in de:
                    issues.append(f"(extra key) {k}  in {zh}")

print(f"Placeholder/key issues found: {len(issues)}")
for i in issues[:300]:
    print("  " + i)
