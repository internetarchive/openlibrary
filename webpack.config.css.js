/*
 * Webpack config for compiling CSS entry points to independent CSS files in static/build/
 *
 * All page-*.css entry points use native CSS with custom properties (var(--token)).
 * css-loader resolves @import statements, and css-minimizer-webpack-plugin handles
 * minification.
 *
 * Design tokens (tokens.css) and site-wide web component styles
 * (ol-components.css) are compiled as separate entries and loaded
 * directly in <head> so they cache independently of the per-page bundles.
 */
const path = require('path');
const glob = require('glob');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');
const CssMinimizerPlugin = require('css-minimizer-webpack-plugin');
const distDir = path.resolve(__dirname, process.env.BUILD_DIR || 'static/build/css');

// Find all CSS entry files matching static/css/page-*.css
const cssFiles = glob.sync('./static/css/page-*.css');
const entries = {
    // Design tokens — compiled from static/css/tokens/ into a single file
    tokens: './static/css/tokens.css',
    // Site-wide web component styles (light-DOM CSS + pre-hydration FOUC fixes)
    'ol-components': './static/css/ol-components.css',
};

cssFiles.forEach(file => {
    const name = path.basename(file, '.css');
    entries[name] = file;
});

module.exports = {
    context: __dirname,
    entry: entries,
    output: {
        path: distDir,
        // Output only CSS, JS is not needed
        filename: '[name].css.js', // dummy, CSS will be extracted
        clean: true,
    },
    module: {
        rules: [
            {
                test: /\.css$/,
                use: [
                    MiniCssExtractPlugin.loader,
                    {
                        loader: 'css-loader',
                        options: {
                            url: false,
                            import: true // Enable @import resolution
                        }
                    }
                ]
            }
        ]
    },
    plugins: [
        new MiniCssExtractPlugin({
            filename: '[name].css',
        }),
        // Inline plugin to remove intermediary JS assets
        {
            apply: (compiler) => {
                compiler.hooks.thisCompilation.tap('RemoveJSAssetsPlugin', (compilation) => {
                    compilation.hooks.processAssets.tap(
                        {
                            name: 'RemoveJSAssetsPlugin',
                            stage: compiler.webpack.Compilation.PROCESS_ASSETS_STAGE_ADDITIONS,
                        },
                        (assets) => {
                            Object.keys(assets)
                                .filter((asset) => asset.endsWith('.js'))
                                .forEach((asset) => {
                                    compilation.deleteAsset(asset);
                                });
                        }
                    );
                });
            }
        }
    ],
    optimization: {
        minimizer: [
            new CssMinimizerPlugin(),
        ],
        runtimeChunk: false,
        splitChunks: false,
    },
    // Useful for developing in docker/windows, which doesn't support file watchers
    watchOptions: process.env.FORCE_POLLING === 'true' ? {
        poll: 1000, // Check for changes every second
        aggregateTimeout: 300, // Delay before rebuilding
        ignored: /node_modules/
    } : undefined,
};
