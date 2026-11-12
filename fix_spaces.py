#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Restore spaces around {placeholders} dropped by MT (idempotent).

Some MT engines return "删除{count}项" instead of "删除 {count} 项". This
walks every translated zh-rCN string, and for each {arg} that was flanked by
whitespace in the English source, ensures a single space sits before/after the
brace in the Chinese text. Already-correct entries are left untouched.
"""
import glob, re, os, sys
from lxml import etree

REPO = sys.argv[1] if len(sys.argv) > 1 else "."
cjk = re.compile(r"[\u4e00-\u9fff]")
SIMPLE = re.compile(r"\{(\w+)\}")


def en_flanks(name, en):
    """Return (need_before_space, need_after_space) per the English source."""
    before = after = False
    pat = re.compile(r"\{" + re.escape(name) + r"\}")
    for m in pat.finditer(en):
        i, j = m.start(), m.end()
        if i > 0 and en[i - 1].isspace():
            before = True
        if j < len(en) and en[j].isspace():
            after = True
    return before, after


def fix_text(en, zh):
    if not SIMPLE.search(zh):
        return zh
    for name in dict.fromkeys(SIMPLE.findall(en)):
        need_b, need_a = en_flanks(name, en)
        if not (need_b or need_a):
            continue
        token = "{" + name + "}"
        start = 0
        res = []
        while True:
            idx = zh.find(token, start)
            if idx == -1:
                res.append(zh[start:])
                break
            res.append(zh[start:idx])
            if need_b and (idx == 0 or zh[idx - 1] != " "):
                res.append(" ")
            res.append(token)
            if need_a and (idx + len(token) >= len(zh) or zh[idx + len(token)] != " "):
                res.append(" ")
            start = idx + len(token)
        zh = "".join(res)
    return zh


def load(path):
    d = {}
    try:
        t = etree.parse(path)
    except Exception:
        return d
    for el in t.getroot().iter():
        if el.tag in ("string", "item"):
            n = el.get("name")
            if n is not None:
                d[n] = "".join(el.itertext())
    return d


def main():
    total = 0
    files = sorted(glob.glob(f"{REPO}/**/values-zh-rCN/*.xml", recursive=True))
    for f in files:
        if "/fixtures/" in f.replace("\\", "/"):
            continue
        enf = os.path.join(os.path.dirname(os.path.dirname(f)), "values", os.path.basename(f))
        if not os.path.exists(enf):
            continue
        en = load(enf)
        try:
            tree = etree.parse(f)
        except Exception as e:
            print("parse fail", f, e)
            continue
        changed = False
        for el in tree.getroot().iter():
            if el.tag in ("string", "item"):
                name = el.get("name")
                zh = el.text or ""
                if not zh or not cjk.search(zh) or name not in en:
                    continue
                new = fix_text(en[name], zh)
                if new != zh:
                    el.text = new
                    changed = True
                    total += 1
                    print(f"  ~{total} {name}")
        if changed:
            tree.write(f, xml_declaration=True, encoding="utf-8")
    print(f"DONE. restored spacing on {total} entries.")


if __name__ == "__main__":
    import sys
    main()
