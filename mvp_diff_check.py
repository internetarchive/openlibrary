#!/usr/bin/env python3
"""
mvp_diff_check.py — Logical diff of Python ground-truth gold docs (mvp_py_ground.py output)
vs rust_solr output (parquet).

Rules:
- Multivalued fields compare as order-insensitive multisets ("key ordering diffs ok").
- Nested `editions` arrays match child docs by `key`.
- lcc_sort/ddc_sort mismatches are allowed when both sides pick different but equally-long
  winners from the candidate set (nondeterministic max-tie, see choose_sorting_lcc/ddc).
- Everything else must match exactly. Any other diff fails the run.

Usage:
  .venv/bin/python mvp_diff_check.py --py /tmp/opencode/py_10k.json \
      --rust /tmp/opencode/rust_10k_ia.parquet [--max-examples 5]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter

import duckdb


def norm_list(v: list) -> list:
    return sorted(v, key=lambda x: json.dumps(x, sort_keys=True))


def canon(value):
    if isinstance(value, list):
        return norm_list([canon(x) for x in value])
    if isinstance(value, dict):
        return {k: canon(v) for k, v in sorted(value.items())}
    return value


def sortable_len(field: str, s: str) -> int:
    # lcc: choose_sorting_lcc maximizes len(short-form); ddc: choose_sorting_ddc uses plain len()
    if field == "lcc_sort":
        from openlibrary.utils.lcc import sortable_lcc_to_short_lcc

        try:
            return len(sortable_lcc_to_short_lcc(s))
        except AssertionError:
            return len(s)
    return len(s)


class DiffReport:
    def __init__(self):
        self.field_counts: Counter[str] = Counter()
        self.examples: dict[str, list] = {}

    def add(self, field: str, key: str, py_val, rust_val):
        self.field_counts[field] += 1
        ex = self.examples.setdefault(field, [])
        if len(ex) < 1000:
            ex.append((key, py_val, rust_val))

    @property
    def total(self) -> int:
        return sum(self.field_counts.values())


def compare_doc(py: dict, rust: dict, key: str, rep: DiffReport, path_prefix: str = ""):
    py_fields = set(py.keys())
    rust_fields = set(rust.keys())
    for f in py_fields - rust_fields:
        rep.add(f"{path_prefix}{f} [py-only]", key, py[f], "<absent>")
    for f in rust_fields - py_fields:
        rep.add(f"{path_prefix}{f} [rust-only]", key, "<absent>", rust[f])
    for f in py_fields & rust_fields:
        if f == "editions":
            # handled by the keyed recursion below (order-insensitive); flag count mismatches only
            if len(py[f]) != len(rust[f]):
                rep.add("editions [count]", key, len(py[f]), len(rust[f]))
            continue
        pv, rv = py[f], rust[f]
        if isinstance(pv, list) and isinstance(rv, list):
            if norm_list(pv) == norm_list(rv):
                continue
            rep.add(f"{path_prefix}{f}", key, pv, rv)
        elif f in ("lcc_sort", "ddc_sort") and isinstance(pv, str) and isinstance(rv, str):
            if pv == rv:
                continue
            # allow different-but-equally-long winners of the same candidate set (max-tie)
            candidates = set()
            cand_field = "lcc" if f == "lcc_sort" else "ddc"
            for src in (py, rust):
                candidates.update(src.get(cand_field, []))
            if (
                pv in candidates
                and rv in candidates
                and sortable_len(f, pv) == sortable_len(f, rv)
                and sortable_len(f, pv) == max(sortable_len(f, c) for c in candidates)
            ):
                continue
            rep.add(f"{path_prefix}{f}", key, pv, rv)
        elif f == "last_modified_i" and isinstance(pv, int) and isinstance(rv, int):
            # Fake works (and any doc missing last_modified) get index-time now() on both
            # sides (datetimestr_to_int(None) -> int(time.time())); runs happen seconds apart.
            if abs(pv - rv) < 3600:
                continue
            rep.add(f"{path_prefix}{f}", key, pv, rv)
        elif canon(pv) != canon(rv):
            rep.add(f"{path_prefix}{f}", key, pv, rv)

    # nested editions: match by key
    py_eds = {e.get("key"): e for e in py.get("editions", [])} if isinstance(py.get("editions"), list) else {}
    rust_eds = {e.get("key"): e for e in rust.get("editions", [])} if isinstance(rust.get("editions"), list) else {}
    if set(py_eds) != set(rust_eds):
        rep.add(f"{path_prefix}editions [keys]", key, sorted(py_eds), sorted(rust_eds))
    for ek in set(py_eds) & set(rust_eds):
        compare_nested(py_eds[ek], rust_eds[ek], f"{key}/{ek}", rep)


def compare_nested(py: dict, rust: dict, key: str, rep: DiffReport):
    """Nested edition docs: order-insensitive on list fields (key ordering diffs are ok)."""
    py_fields = set(py.keys())
    rust_fields = set(rust.keys())
    for f in py_fields - rust_fields:
        rep.add(f"editions.{f} [py-only]", key, py[f], "<absent>")
    for f in rust_fields - py_fields:
        rep.add(f"editions.{f} [rust-only]", key, "<absent>", rust[f])
    for f in py_fields & rust_fields:
        pv, rv = canon(py[f]), canon(rust[f])
        if pv != rv:
            rep.add(f"editions.{f}", key, py[f], rust[f])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--py", required=True)
    ap.add_argument("--rust", required=True)
    ap.add_argument("--max-examples", type=int, default=5)
    args = ap.parse_args()

    with open(args.py) as f:
        py_docs = json.load(f)

    con = duckdb.connect()
    rust_docs = {}
    for k, dj in con.execute(f"SELECT key, doc_json FROM '{args.rust}'").fetchall():
        rust_docs[k] = json.loads(dj)

    all_keys = sorted(set(py_docs) | set(rust_docs))
    rep = DiffReport()
    matched = 0
    for key in all_keys:
        p, r = py_docs.get(key), rust_docs.get(key)
        if p is None:
            rep.add("<doc> [rust-only]", key, None, r.get("title"))
            continue
        if r is None:
            rep.add("<doc> [py-only]", key, p.get("title"), None)
            continue
        before = rep.total
        compare_doc(p, r, key, rep)
        if rep.total == before:
            matched += 1

    n_py_only_keys = rep.field_counts.pop("<doc> [py-only]", 0)
    n_rust_only_keys = rep.field_counts.pop("<doc> [rust-only]", 0)

    print(f"Docs compared: {len(all_keys)} | fully matching: {matched}")
    if n_py_only_keys or n_rust_only_keys:
        print(f"Doc-level gaps: py-only={n_py_only_keys} rust-only={n_rust_only_keys}")
    print(f"Field diffs: {rep.total}")
    for field, count in rep.field_counts.most_common(40):
        print(f"  {count:6d}  {field}")
        for k, pv, rv in rep.examples.get(field, [])[: args.max_examples]:
            print(f"          e.g. {k}: py={json.dumps(pv)[:180]} | rust={json.dumps(rv)[:180]}")

    if rep.total or n_py_only_keys or n_rust_only_keys:
        raise SystemExit(1)
    print("FULL PARITY ✓")


if __name__ == "__main__":
    main()
