import { defineConfig, globalIgnores } from "eslint/config";
import noJquery from "eslint-plugin-no-jquery";
import globals from "globals";
import path from "node:path";
import { fileURLToPath } from "node:url";
import js from "@eslint/js";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const compat = new FlatCompat({
    baseDirectory: __dirname,
    recommendedConfig: js.configs.recommended,
    allConfig: js.configs.all
});

export default defineConfig([globalIgnores([
    ".*",
    "**/conf/",
    "**/config/",
    "**/docker/",
    "**/infogami/",
    "**/node_modules/",
    "**/scripts/",
    "static/build/",
    "static/js/",
    "static/build/vendor.js",
    "**/provisioning/",
    "**/vendor/",
    "tests/screenshots/",
    "**/venv/",
]), {
    files: ["**/*.js", "**/*.vue"],
    // Eventually we may want to stop ignoring some of these but for the migration it seems necessary
    ignores: [
        "**/webpack.config.js",
        "**/vue.config.js",
        "**/stories/**/*.js",
        "openlibrary/components/dev/serve-component.js",
        "**/tests/**/*.js",// we need to setup a custom config for this one that used to be in tests/unit/.eslintrc.json
    ],
    extends: compat.extends("plugin:vue/vue3-recommended", "plugin:no-jquery/deprecated"),

    plugins: {
        "no-jquery": noJquery,
    },

    languageOptions: {
        globals: {
            ...globals.browser,
            ...globals.jquery,
        },

        ecmaVersion: 6,
        sourceType: "module",

        parserOptions: {
            parser: "@babel/eslint-parser",

            babelOptions: {
                configFile: "./.babelrc",
            },
        },
    },

    rules: {
        "prefer-template": "error",
        eqeqeq: ["error", "always"],
        quotes: ["error", "single"],
        "eol-last": ["error", "always"],
        indent: 2,
        "no-console": "error",
        "no-extra-semi": "error",
        "no-mixed-spaces-and-tabs": "error",
        "no-redeclare": "error",
        "no-trailing-spaces": "error",
        "no-undef": "error",
        "no-unused-vars": "error",
        "no-useless-escape": "error",
        "space-in-parens": "error",
        "vars-on-top": "error",
        "prefer-const": "error",
        "template-curly-spacing": "error",
        "quote-props": ["error", "as-needed"],

        "keyword-spacing": ["error", {
            before: true,
            after: true,
        }],

        "key-spacing": ["error", {
            mode: "strict",
        }],

        "vue/no-mutating-props": "off",

        "vue/multi-word-component-names": ["error", {
            ignores: ["Bookshelf", "Shelf"],
        }],
    },
}]);