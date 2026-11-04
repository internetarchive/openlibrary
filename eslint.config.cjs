const js = require('@eslint/js');
const prettierConfig = require('eslint-config-prettier/flat');
const vuePlugin = require('eslint-plugin-vue');
const globals = require('globals');

// ESLint is only used for Vue files (see .pre-commit-config.yaml). JS is
// linted by oxlint (.oxlintrc.json), and JS and Vue are formatted by oxfmt
// (.oxfmtrc.json).
/** @type {import('eslint').Linter.Config[]} */
module.exports = [
    {
        ignores: [
            // Keep editor integrations and a bare `eslint .` off non-Vue files;
            // without this, the recommended configs below apply to all JS.
            '**/*.{js,mjs,cjs,ts}',
            '.*',
            'conf/',
            'config/',
            'docker/',
            'docs/wiki/',
            'infogami/',
            'node_modules/',
            'scripts/gh_scripts/',
            'static/build/',
            'build/',
            'coverage/',
            'provisioning/',
            'vendor/',
            'tests/screenshots/',
            'venv/',
            '.venv/'
        ]
    },

    // Base recommended config
    js.configs.recommended,

    // Vue plugin configuration
    ...vuePlugin.configs['flat/recommended'],

    {
        files: ['**/*.vue'],
        languageOptions: {
            parserOptions: {
                sourceType: 'module',
                ecmaVersion: 'latest'
            },
            globals: {
                ...globals.browser
            }
        },
        rules: {
            'prefer-template': 'error',
            eqeqeq: ['error', 'always'],
            'no-console': 'error',
            'no-redeclare': 'error',
            'no-undef': 'error',
            'no-unused-vars': [
                'error',
                {
                    caughtErrors: 'none'
                }
            ],
            'no-useless-escape': 'error',
            'no-warning-comments': [
                'error',
                {
                    // The webpackChunkName magic comments were removed in the Vite
                    // migration; they are dead under Vite (chunks are named after
                    // their imported file). Flag any that slip back in so the
                    // cleanup stays enforced.
                    terms: ['webpackChunkName'],
                    location: 'anywhere'
                }
            ],
            'vars-on-top': 'error',
            'prefer-const': 'error',

            'vue/no-mutating-props': 'off',
            'vue/multi-word-component-names': [
                'error',
                {
                    ignores: ['Bookshelf', 'Shelf']
                }
            ],
            'vue/require-prop-types': 'error',
            'vue/require-explicit-emits': 'error',
            'vue/require-default-prop': 'error',
            'vue/no-v-html': 'error',
            'vue/no-template-shadow': 'error',
            'vue/no-unused-refs': 'error',
            'vue/no-unused-properties': 'error',
            'vue/no-unused-emit-declarations': 'error',
            'vue/no-useless-v-bind': 'error',
            'vue/no-import-compiler-macros': 'error',
            'vue/no-undef-components': [
                'error',
                {
                    // Lit components, treated as custom elements by the Vue
                    // build's isCustomElement (tag.startsWith('ol-')).
                    ignorePatterns: ['^ol-']
                }
            ]
        }
    },

    // Last, so it switches off every formatting rule enabled above (including
    // eslint-plugin-vue's layout rules); oxfmt owns formatting, and the eslint
    // hook's --fix would otherwise undo its output.
    prettierConfig
];
