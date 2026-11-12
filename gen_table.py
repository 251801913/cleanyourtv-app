#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regenerate zh_translation_table.md from current repo state."""
import glob, re, os
from lxml import etree
from collections import OrderedDict

cjk = re.compile(r"[\u4e00-\u9fff]")
alpha = re.compile(r"[A-Za-z]")


def load(p):
    d = {}
    try:
        t = etree.parse(p)
    except Exception:
        return d
    for el in t.getroot().iter():
        if el.tag in ("string", "item"):
            n = el.get("name")
            if n is not None:
                d[n] = "".join(el.itertext())
    return d


def mod_of(zhf):
    parts = [p for p in zhf.replace("\\", "/").split("/") if p not in ("", ".", "..")]
    try:
        si = parts.index("src")
        return "/".join(parts[:si]) or "(root)"
    except ValueError:
        return zhf


trans = []
remain = []
summ = []
for f in sorted(glob.glob("**/values-zh-rCN/*.xml", recursive=True)):
    if "/fixtures/" in f.replace("\\", "/"):
        continue
    enf = f.replace("/values-zh-rCN/", "/values/")
    mod = mod_of(f)
    en = load(enf) if os.path.exists(enf) else {}
    zh = load(f)
    tr = 0
    un = 0
    for name, zt in zh.items():
        if zt and cjk.search(zt):
            tr += 1
            trans.append((mod, name, en.get(name, ""), zt))
        elif zt and alpha.search(zt) and not cjk.search(zt):
            un += 1
            if "plural" in zt or "%" in zt:
                reason = "ICU复数/printf格式串"
            elif not re.search(r"\{", zt):
                reason = "品牌名"
            else:
                reason = "纯变量模板"
            remain.append((mod, name, en.get(name, zt), reason))
    summ.append((mod, tr, un))

by_mod = OrderedDict()
for r in trans:
    by_mod.setdefault(r[0], []).append(r)

out = []
out.append("# 译文对照表 (zh-rCN) — cleanyourtv-app\n")
out.append("> 机翻基线(讯飞 XFTrans + uapis)，已做占位符校验；建议按模块人工校对。\n")
for mod, items in by_mod.items():
    out.append(f"## 模块: {mod} (已译 {len(items)})\n")
    out.append("| Key | English | 中文 |")
    out.append("| --- | --- | --- |")
    for (m, name, e, z) in items:
        e = e.replace("|", "\\|").replace("\n", " ").strip()
        z = z.replace("|", "\\|").replace("\n", " ").strip()
        out.append(f"| {name} | {e} | {z} |")
    out.append("")

out.append("## 统计 (已译 / 仍英文)\n")
out.append("| 模块 | 已译 | 仍英文 |")
out.append("| --- | --- | --- |")
tt = tu = 0
for (mod, t, u) in summ:
    out.append(f"| {mod} | {t} | {u} |")
    tt += t
    tu += u
out.append(f"| **合计** | **{tt}** | **{tu}** |")

out.append("")
out.append("## 仍英文条目 (均安全保留)\n")
note = ("这些条目的占位符名 / ICU plural / printf 格式符若被机翻改写，会导致 App "
        "运行时取不到值而崩溃，故按设计保留英文（运行时由系统填充）。其内部散文可手动翻译。")
out.append("> " + note + "\n")
out.append("| 模块 | Key | English | 类型 |")
out.append("| --- | --- | --- | --- |")
for (mod, name, e, reason) in remain:
    e = e.replace("|", "\\|").replace("\n", " ").strip()
    out.append(f"| {mod} | {name} | {e} | {reason} |")

with open("zh_translation_table.md", "w", encoding="utf-8") as fh:
    fh.write("\n".join(out))
print("translated:", tt, "remaining:", tu, "modules:", len(summ))
