#!/usr/bin/env bash
#
# Parity harness: webpack vs Vite JS build.
#
# Verifies that the Vite build (vite-js.config.mjs + vite-js-iife.config.mjs)
# preserves the *contract* webpack produced, before webpack.config.js is deleted.
#
# The webpack side is built from the config recovered from git (this script is
# expected to run before/around the webpack removal). The two builds use
# different code-splitting (webpack extracts a giant shared "vendor" chunk;
# Vite inlines per-chunk deps), so sizes are compared structurally, not
# byte-for-byte.
#
# Usage: scripts/js-build-parity.sh [webpack_out_dir] [vite_out_dir] [git_ref]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

WP_DIR="${1:-/tmp/js_wp}"
VITE_DIR="${2:-/tmp/js_vite}"
# Default to the most recent commit that still contained webpack.config.js
# (works before merge, after merge, and in shallow clones with --all).
# `git log --follow` includes the deletion commit itself, so walk the list and
# pick the first ref at which the file still exists.
WP_GIT_REF="${3:-}"
if [ -z "$WP_GIT_REF" ]; then
    for r in $(git log --all --follow --format=%H -- webpack.config.js); do
        if git cat-file -e "$r:webpack.config.js" 2>/dev/null; then
            WP_GIT_REF="$r"
            break
        fi
    done
fi

if [ -z "$WP_GIT_REF" ]; then
    echo "Error: could not determine a git ref containing webpack.config.js" >&2
    exit 1
fi

echo "== Recovering webpack.config.js from git ref ${WP_GIT_REF} =="
# webpack.config.js uses `context: __dirname`, so it must sit in the repo root
# for the relative entry paths to resolve.
WP_CONFIG="$REPO_ROOT/webpack.config.parity.tmp.js"
git show "${WP_GIT_REF}:webpack.config.js" > "$WP_CONFIG"

# webpack was removed from devDependencies after the migration, so install it
# (plus its loaders) into a throwaway prefix to rebuild the baseline.
WP_DEPS="$(mktemp -d)"
trap 'rm -rf "$WP_DEPS" "$WP_CONFIG"' EXIT
echo "== Installing webpack into a throwaway prefix (for the baseline build) =="
npm install --prefix "$WP_DEPS" --no-save --no-audit --no-fund --no-package-lock \
    webpack@5.106.2 webpack-cli@5.1.4 babel-loader@10.0.0 style-loader@4.0.0 css-loader@7.1.4 >/dev/null 2>&1

# webpack resolves loaders from the config's context (the repo root), which no
# longer has them installed. Wrap the recovered config so resolveLoader points
# at the throwaway prefix instead.
WP_WRAPPER="$WP_DEPS/webpack.parity.wrapper.cjs"
cat > "$WP_WRAPPER" <<'WRAPPER'
const base = require(process.env.WP_CONFIG);
base.resolveLoader = { modules: [process.env.WP_DEPS + '/node_modules', 'node_modules'] };
module.exports = base;
WRAPPER

echo "== Building webpack -> $WP_DIR =="
rm -rf "$WP_DIR" && mkdir -p "$WP_DIR"
# NODE_PATH lets the recovered config's `require("webpack")` resolve from the
# prefix (the wrapper only fixes webpack's own loader resolution).
NODE_PATH="$WP_DEPS/node_modules" WP_CONFIG="$WP_CONFIG" WP_DEPS="$WP_DEPS" \
    BUILD_DIR="$WP_DIR" NODE_ENV=production \
    "$WP_DEPS/node_modules/.bin/webpack" --config "$WP_WRAPPER" >/dev/null 2>&1

echo "== Building Vite -> $VITE_DIR =="
rm -rf "$VITE_DIR" && mkdir -p "$VITE_DIR"
BUILD_DIR="$VITE_DIR" npx vite build -c vite-js.config.mjs >/dev/null 2>&1
BUILD_DIR="$VITE_DIR" IIFE_ENTRY=sw npx vite build -c vite-js-iife.config.mjs >/dev/null 2>&1
BUILD_DIR="$VITE_DIR" IIFE_ENTRY=partnerLib npx vite build -c vite-js-iife.config.mjs >/dev/null 2>&1
# The AGPL license header/footer is added by the Vite configs themselves
# (output.postBanner/postFooter) — no post-processing here.

fail=0
check() { # check <description> <command...>
    local desc="$1"; shift
    if "$@" >/dev/null 2>&1; then echo "  ✓ $desc"; else echo "  ✗ $desc"; fail=1; fi
}

echo
echo "== 1. Entry files =="
for f in all.js sw.js partnerLib.js; do
    check "$f present in Vite output" test -f "$VITE_DIR/$f"
done

echo "== 2. Named chunk parity (every webpack name must exist in Vite) =="
wp_names=$(ls "$WP_DIR"/*.js | sed "s#$WP_DIR/##; s#\.[a-f0-9]\{20\}\.js##; s#\.js##" | grep -vE '^[0-9]+$' | sort -u)
vite_names=$(ls "$VITE_DIR"/*.js | sed "s#$VITE_DIR/##; s#\.[A-Za-z0-9_-]\{8\}\.js##; s#\.js##" | sort -u)
for name in $wp_names; do
    if echo "$vite_names" | grep -qxF "$name"; then
        echo "  ✓ chunk '$name' preserved"
    else
        echo "  ✗ chunk '$name' MISSING from Vite output"
        fail=1
    fi
done

echo "== 3. License header on every JS file =="
for js in "$VITE_DIR"/*.js; do
    check "license header: $(basename "$js")" grep -q '^// @license magnet:' "$js"
done

echo "== 4. Sourcemap present wherever referenced =="
for js in "$VITE_DIR"/*.js; do
    # The synthetic rolldown shared-runtime chunk (chunk.*.js) has no original
    # source, so it legitimately carries no sourceMappingURL and no .map.
    if grep -q 'sourceMappingURL' "$js"; then
        check "sourcemap: $(basename "$js").map" test -f "$js.map"
    fi
done

echo "== 5. sw.js shape (self-contained classic script) =="
check "sw.js has no import/export" sh -c "! grep -qE '^(import|export) ' '$VITE_DIR/sw.js'"
check "sw.js is an IIFE" grep -q '^(function' "$VITE_DIR/sw.js"
check "sw.js bundles workbox" grep -q 'workbox:core:' "$VITE_DIR/sw.js"

echo
echo "== gzip sizes (informational; Vite inlines per-chunk deps) =="
for f in all.js sw.js partnerLib.js; do
    w=$(gzip -c "$WP_DIR/$f" | wc -c | tr -d ' ')
    v=$(gzip -c "$VITE_DIR/$f" | wc -c | tr -d ' ')
    printf "  %-14s webpack %8s B   vite %8s B\n" "$f" "$w" "$v"
done
printf "  %-14s webpack %8s B   vite %8s B (total, all JS)\n" "(total)" \
    "$(cat "$WP_DIR"/*.js | gzip -c | wc -c | tr -d ' ')" \
    "$(cat "$VITE_DIR"/*.js | gzip -c | wc -c | tr -d ' ')"

echo
if [ "$fail" -eq 0 ]; then echo "PARITY OK"; else echo "PARITY FAILED"; fi
exit "$fail"
