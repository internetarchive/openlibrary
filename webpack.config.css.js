/* eslint-env node, es6 */
/*
 * Webpack config for compiling CSS entry points to independent CSS files in static/build/
 *
 * All page-*.css entry points use native CSS with custom properties (var(--token)).
 * css-loader resolves @import statements, and css-minimizer-webpack-plugin handles
 * minification.
 *
 * CSS custom properties are auto-generated from the LESS variable definition files
 * in static/css/less/ by scripts/generate-css-custom-properties.js before each build.
 */
const path = require('path');
const glob = require('glob');
const { execSync } = require('child_process');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');
const CssMinimizerPlugin = require('css-minimizer-webpack-plugin');
const distDir = path.resolve(__dirname, process.env.BUILD_DIR || 'static/build/css');

// Find all CSS entry files matching static/css/page-*.css
const cssFiles = glob.sync('./static/css/page-*.css');
const entries = {};

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
        // Re-generate CSS custom properties from LESS variables before each build.
        // Ensures generated-custom-properties.css stays in sync during watch mode.
        {
            apply: (compiler) => {
                compiler.hooks.beforeCompile.tap('GenerateCSSVarsPlugin', () => {
                    try {
                        execSync('node scripts/generate-css-custom-properties.js', {
                            stdio: 'inherit',
                            cwd: __dirname,
                        });
                    } catch (e) {
                        // eslint-disable-next-line no-console
                        console.error('Failed to generate CSS custom properties:', e.message);
                    }
                });
            }
        },
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
