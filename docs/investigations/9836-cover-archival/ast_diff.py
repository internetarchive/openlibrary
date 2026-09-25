#!/usr/bin/env python3
"""Report which functions in a Python file changed behaviour between two git refs.

Compares the AST of every function and method, so formatting, quote style and
comment edits are ignored. Changed functions are printed via ast.unparse so a
human can judge whether each change alters behaviour.

Usage (from the repo root):
    python docs/investigations/9836-cover-archival/ast_diff.py \\
        16681e1d2 origin/master openlibrary/coverstore/archive.py

16681e1d2 is the merge of #9296, the last substantive change to archive.py
before the 2024 loss.

Caveat: docstrings are part of the AST, so a docstring-only edit shows as a
change. Read the unparsed diff before calling anything a behaviour change.
"""

import ast
import difflib
import subprocess
import sys


def functions(source: str) -> tuple[dict[str, ast.AST], list[str]]:
    tree = ast.parse(source)
    out: dict[str, ast.AST] = {}

    def walk(node, prefix=""):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                out[prefix + child.name] = child
            elif isinstance(child, ast.ClassDef):
                walk(child, prefix + child.name + ".")

    walk(tree)
    top = sorted(ast.unparse(s) for s in tree.body if not isinstance(s, ast.FunctionDef | ast.ClassDef))
    return out, top


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    ref_a, ref_b, path = sys.argv[1:]

    def show(ref: str) -> str:
        return subprocess.run(["git", "show", f"{ref}:{path}"], check=True, capture_output=True, text=True).stdout

    fa, ta = functions(show(ref_a))
    fb, tb = functions(show(ref_b))

    names = sorted(set(fa) | set(fb))
    changed = [n for n in names if n not in fa or n not in fb or ast.dump(fa[n]) != ast.dump(fb[n])]
    print(f"# {len(names)} functions compared, {len(changed)} differ ({ref_a} -> {ref_b}, {path})")
    for name in changed:
        a = ast.unparse(fa[name]).splitlines() if name in fa else []
        b = ast.unparse(fb[name]).splitlines() if name in fb else []
        print(f"\n## {name}")
        print("\n".join(difflib.unified_diff(a, b, lineterm="", n=1)))
    top_note = "same" if ta == tb else "differ"
    print(f"\n# top-level statements (imports, constants), order-insensitive: {top_note}")
    if ta != tb:
        print("\n".join(difflib.unified_diff(ta, tb, lineterm="", n=0)))


if __name__ == "__main__":
    main()
