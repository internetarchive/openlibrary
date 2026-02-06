/* eslint-env node, es6 */
/*
 * Webpack config for compiling Less files to independent CSS files in static/build/
 */
const path = require('path');
const glob = require('glob');
const { execSync } = require('child_process');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');
const LessPluginCleanCss = require('less-plugin-clean-css');
const distDir = path.resolve(__dirname, process.env.BUILD_DIR || 'static/build/css');

// Find all Less files matching static/css/page-*.less
const lessFiles = glob.sync('./static/css/page-*.less');
const entries = {};
lessFiles.forEach(file => {
    // e.g. page-home.less -> page-home
    const name = path.basename(file, '.less');
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
                test: /\.less$/,
                use: [
                    MiniCssExtractPlugin.loader,
                    {
                        loader: 'css-loader',
                        options: { url: false }
                    },
                    {
                        loader: 'less-loader',
                        options: {
                            lessOptions: {
                                paths: [
                                    path.resolve(__dirname, 'static/css'),
                                    path.resolve(__dirname, 'static/css/components'),
                                ],
                                plugins: [
                                    new LessPluginCleanCss({
                                        advanced: true,
                                        compatibility: '*',
                                        keepSpecialComments: 0
                                    })
                                ]
                            }
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
