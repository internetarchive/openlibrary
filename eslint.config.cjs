const js = require('@eslint/js');
const vuePlugin = require('eslint-plugin-vue');
const globals = require('globals');

// ESLint is only used for Vue files (see .pre-commit-config.yaml). JS is
// linted by oxlint (.oxlintrc.json) and formatted by oxfmt (.oxfmtrc.json).
/** @type {import('eslint').Linter.Config[]} */
module.exports = [
    {
        ignores: [
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

            // Formatting rules: Vue script blocks are not covered by oxfmt
            quotes: ['error', 'single'],
            'eol-last': ['error', 'always'],
            indent: 2,
            'no-mixed-spaces-and-tabs': 'error',
            'no-extra-semi': 'error',
            'no-trailing-spaces': 'error',
            'space-in-parens': 'error',
            'template-curly-spacing': 'error',
            'quote-props': ['error', 'as-needed'],
            'keyword-spacing': ['error', { before: true, after: true }],
            'key-spacing': ['error', { mode: 'strict' }],
            semi: ['error', 'always'],
            'space-before-function-paren': ['error', 'never'],
            'comma-spacing': ['error', { before: false, after: true }],

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
            'vue/no-template-shadow': 'error'
        }
    }
];
