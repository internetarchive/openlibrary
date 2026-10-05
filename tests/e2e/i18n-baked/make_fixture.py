#!/usr/bin/env python
"""Pick the strings tests/e2e/i18n-baked.spec.ts asserts on.

    make_fixture.py candidates --committed DIR --baked DIR --langs es,pl,hr,ja --kept az > candidates.json
    make_fixture.py select --candidates candidates.json --visible visible.json > fixture.json

DIR is an openlibrary/i18n-shaped directory (<lang>/messages.po). The run script
extracts both from images, so the fixture describes what the images actually contain:
--committed from the image built without the pull step, --baked from the candidate.

Classes, per language:
  english_before  translated in baked, English in committed (empty, fuzzy or absent).
                  Baked path must show the translation; committed path the English.
  both            translated identically in both. Proves a path's translations are
                  live at all, so "shows English" cannot mean "no .mo loaded".
  kept            (--kept languages, which openlibrary-i18n does not change) translated
                  identically in both; the baked path must still show it.

`select` keeps only msgids whose English text appears exactly once in some page's
English rendering (visible.json: {url: document.body.innerText}), so an assertion
on a page is about a string that page really shows.
"""

import argparse
import json
import os
import re
import sys

from babel.messages.pofile import read_po


def _load(path: str) -> dict[str, str]:
    """msgid -> msgstr for compiled (non-fuzzy, non-empty) singular entries."""
    if not os.path.exists(path):
        return {}
    with open(path, "rb") as f:
        catalog = read_po(f)
    return {m.id: m.string for m in catalog if m.id and isinstance(m.id, str) and not m.context and not m.fuzzy and m.string and m.string != m.id}


def _plain(msgid: str) -> bool:
    # At least two words: matching a page's English text to a msgid does not prove that
    # msgid rendered it, and a single generic word ("Create") often comes from elsewhere.
    return " " in msgid.strip() and "%" not in msgid and "<" not in msgid and "&" not in msgid and "\n" not in msgid


def candidates(committed_dir: str, baked_dir: str, langs: list[str], kept: list[str]) -> dict:
    out: dict = {}
    for lang in langs + kept:
        committed = _load(os.path.join(committed_dir, lang, "messages.po"))
        baked = _load(os.path.join(baked_dir, lang, "messages.po"))
        both = [{"msgid": k, "msgstr": v} for k, v in committed.items() if _plain(k) and baked.get(k) == v]
        entry: dict = {"both" if lang in langs else "kept": both}
        if lang in langs:
            entry["english_before"] = [{"msgid": k, "msgstr": v} for k, v in baked.items() if _plain(k) and k not in committed]
        out[lang] = entry
    return out


def _shown_once(msgid: str, text: str) -> bool:
    """msgid appears exactly once on the page, and not inside a longer word:
    "Collection" must not match a page whose only occurrence is "Collections"."""
    whole_word = re.findall(rf"(?<!\w){re.escape(msgid)}(?!\w)", text)
    return len(whole_word) == 1 and text.count(msgid) == 1


def select(cands: dict, visible: dict[str, str], per_class: int = 3) -> dict:
    fixture: dict = {}
    for lang, classes in cands.items():
        fixture[lang] = {}
        for cls, items in classes.items():
            chosen = []
            for item in sorted(items, key=lambda i: -len(i["msgid"])):
                page = next((url for url, text in visible.items() if _shown_once(item["msgid"], text) and item["msgstr"] not in text), None)
                if page and item["msgid"] not in item["msgstr"] and item["msgstr"] not in item["msgid"]:
                    chosen.append({**item, "page": page})
                if len(chosen) == per_class:
                    break
            fixture[lang][cls] = chosen
    return fixture


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("candidates")
    c.add_argument("--committed", required=True)
    c.add_argument("--baked", required=True)
    c.add_argument("--langs", required=True)
    c.add_argument("--kept", default="")
    s = sub.add_parser("select")
    s.add_argument("--candidates", required=True)
    s.add_argument("--visible", required=True)
    args = parser.parse_args()

    empty = []
    if args.cmd == "candidates":
        result = candidates(args.committed, args.baked, args.langs.split(","), [k for k in args.kept.split(",") if k])
    else:
        with open(args.candidates) as f, open(args.visible) as g:
            result = select(json.load(f), json.load(g))
        empty = [f"{lang}.{cls}" for lang, classes in result.items() for cls, items in classes.items() if not items]
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    if empty:
        print(f"no visible string for: {', '.join(empty)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
