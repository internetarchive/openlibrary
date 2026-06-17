/**
 * SVGO config for the build-time icon sprite (scripts/build_icon_sprite.mjs).
 *
 * Distinct from config/svgo.config.js (which optimizes standalone files in
 * place and deliberately preserves width/height/ids). For sprite symbols we
 * want the opposite: drop width/height so CSS governs size, keep viewBox, and
 * leave stroke/fill presentation attributes alone so each glyph keeps its
 * `currentColor` drawing. IDs are namespaced per-glyph in the build script via
 * prefixIds to avoid collisions once every symbol shares one document.
 */
module.exports = {
    plugins: [
        {
            name: "preset-default",
            params: {
                overrides: {
                    // preset-default keeps the viewBox by default in SVGO v4.
                    // Glyphs draw with stroke="currentColor"; never let SVGO
                    // decide a stroke/fill is "useless" and drop it.
                    removeUselessStrokeAndFill: false,
                    // We namespace IDs ourselves (prefixIds), so don't rewrite them.
                    cleanupIds: false,
                },
            },
        },
        // Strip width/height; sizing comes from CSS / the <use> wrapper.
        "removeDimensions",
    ],
};
