const js = require("@eslint/js");
const vuePlugin = require("eslint-plugin-vue");
const globals = require("globals");
const babelParser = require("@babel/eslint-parser");

/** @type {import('eslint').Linter.Config[]} */
module.exports = [
  // Ignore patterns from .eslintignore
  {
    ignores: [
      ".*",
      "*.config.js",
      "*.config.mjs",
      "conf/",
      "config/",
      "docker/",
      "infogami/",
      "node_modules/",
      "scripts/",
      "static/build/",
      "build/",
      "coverage/",
      "provisioning/",
      "vendor/",
      "tests/screenshots/",
      "venv/",
      "eslint.config.cjs",
    ],
  },

  // Configuration for build and config files (CommonJS)
  {
    files: [
      "webpack.config.js",
      "webpack.config.css.js",
      "vue.config.js",
      "openlibrary/components/dev/serve-component.js",
      "conf/svgo.config.js",
      "stories/.storybook/main.js",
    ],
    languageOptions: {
      sourceType: "script",
      ecmaVersion: "latest",
      globals: {
        ...globals.node,
      },
    },
    rules: {
      "no-console": "off",
    },
  },

  // Configuration for Vite config files (ES modules)
  {
    files: [
      "openlibrary/components/vite.config.mjs",
      "openlibrary/components/vite-lit.config.mjs",
    ],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        ...globals.node,
      },
    },
    rules: {
      "no-console": "off",
    },
  },

  // Configuration for Storybook preview files (ES modules)
  {
    files: ["stories/.storybook/preview.js"],
    languageOptions: {
      sourceType: "module",
      ecmaVersion: "latest",
      globals: {
        ...globals.node,
      },
    },
    rules: {
      "no-console": "off",
    },
  },

  // Base recommended config
  js.configs.recommended,

  // Vue plugin configuration
  ...vuePlugin.configs["flat/recommended"],

  // Base configuration for all JS/Vue files
  {
    files: ["**/*.js", "**/*.vue"],
    plugins: {
      "no-jquery": require("eslint-plugin-no-jquery"),
    },
    languageOptions: {
      parserOptions: {
        sourceType: "module",
        ecmaVersion: "latest",
        babelOptions: {
          configFile: "./.babelrc",
        },
      },
      globals: {
        ...globals.browser,
        $: "readonly",
        jQuery: "readonly",
      },
    },
    rules: {
      "prefer-template": "error",
      eqeqeq: ["error", "always"],
      quotes: ["error", "single"],
      "eol-last": ["error", "always"],
      indent: 2,
      "no-console": "error",
      "no-mixed-spaces-and-tabs": "error",
      "no-extra-semi": "error",
      "no-redeclare": "error",
      "no-trailing-spaces": "error",
      "no-undef": "error",
      "no-unused-vars": [
        "error",
        {
          caughtErrors: "none",
        },
      ],
      "no-useless-escape": "error",
      "space-in-parens": "error",
      "vars-on-top": "error",
      "prefer-const": "error",
      "template-curly-spacing": "error",
      "quote-props": ["error", "as-needed"],
      "keyword-spacing": ["error", { before: true, after: true }],
      "key-spacing": ["error", { mode: "strict" }],

      // GLOBALLY ENFORCED FORMATTING RULES
      "semi": ["error", "always"],
      "space-before-function-paren": ["error", "never"],
      "comma-spacing": ["error", { "before": false, "after": true }],

      "vue/no-mutating-props": "off",
      "vue/multi-word-component-names": [
        "error",
        {
          ignores: ["Bookshelf", "Shelf"],
        },
      ],
      // jQuery deprecated rules
      "no-jquery/no-box-model": "warn",
      "no-jquery/no-browser": "warn",
      "no-jquery/no-live": "warn",
      "no-jquery/no-sub": "warn",
      "no-jquery/no-selector-prop": "warn",
      "no-jquery/no-and-self": "warn",
      "no-jquery/no-error-shorthand": "warn",
      "no-jquery/no-load-shorthand": "warn",
      "no-jquery/no-on-ready": "warn",
      "no-jquery/no-size": "warn",
      "no-jquery/no-unload-shorthand": "warn",
      "no-jquery/no-support": "warn",
      "no-jquery/no-context-prop": "warn",
      "no-jquery/no-bind": "warn",
      "no-jquery/no-delegate": "warn",
      "no-jquery/no-fx-interval": "warn",
      "no-jquery/no-parse-json": "warn",
      "no-jquery/no-ready-shorthand": "warn",
      "no-jquery/no-unique": "warn",
      "no-jquery/no-hold-ready": "warn",
      "no-jquery/no-is-array": "warn",
      "no-jquery/no-node-name": "warn",
      "no-jquery/no-camel-case": "warn",
      "no-jquery/no-event-shorthand": ["warn", {}],
      "no-jquery/no-is-function": "warn",
      "no-jquery/no-is-numeric": "warn",
      "no-jquery/no-is-window": "warn",
      "no-jquery/no-now": "warn",
      "no-jquery/no-proxy": "warn",
      "no-jquery/no-type": "warn",
      "no-jquery/no-sizzle": [
        "warn",
        { allowPositional: false, allowOther: true },
      ],
      "no-jquery/no-trim": "warn",
    },
  },

  // Vue-specific configuration
  {
    files: ["**/*.vue"],
    languageOptions: {
      parserOptions: {
        parser: babelParser,
        sourceType: "module",
        ecmaVersion: "latest",
        babelOptions: {
          configFile: "./.babelrc",
        },
      },
    },
  },

  // JavaScript-specific configuration
  {
    files: ["**/*.js"],
    languageOptions: {
      parser: babelParser,
      parserOptions: {
        sourceType: "module",
        ecmaVersion: "latest",
        babelOptions: {
          configFile: "./.babelrc",
        },
      },
    },
  },

  // Configuration for test files
  {
    files: ["tests/unit/**/*.{js,vue}", "tests/unit/js/setup.js"],
    languageOptions: {
      globals: {
        ...globals.es2021,
        ...globals.jest,
        ...globals.node,
      },
    },
  },

// TEMPORARY EXEMPTIONS: Turn off new formatting rules for files locked in active PRs
  {
    files: [
      "openlibrary/components/lit/OLChip.js",
      "openlibrary/plugins/openlibrary/js/SearchBar.js",
      "openlibrary/plugins/openlibrary/js/add-book.js",
      "openlibrary/plugins/openlibrary/js/carousel/Carousel.js",
      "openlibrary/plugins/openlibrary/js/dialog.js",
      "openlibrary/plugins/openlibrary/js/my-books/MyBooksDropper/ReadingLogForms.js",
      "openlibrary/plugins/openlibrary/js/service-worker-init.js"
    ],
    rules: {
      "semi": "off",
      "space-before-function-paren": "off",
      "comma-spacing": "off"
    }
  }
];
