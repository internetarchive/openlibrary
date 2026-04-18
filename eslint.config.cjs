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
      "openlibrary/components/BarcodeScanner.vue",
      "openlibrary/components/BarcodeScanner/components/LazyBookCard.vue",
      "openlibrary/components/BarcodeScanner/utils/classes.js",
      "openlibrary/components/BulkSearch.vue",
      "openlibrary/components/BulkSearch/components/BookCard.vue",
      "openlibrary/components/BulkSearch/components/BulkSearchControls.vue",
      "openlibrary/components/BulkSearch/components/MatchRow.vue",
      "openlibrary/components/BulkSearch/components/MatchTable.vue",
      "openlibrary/components/BulkSearch/components/NoBookCard.vue",
      "openlibrary/components/BulkSearch/utils/classes.js",
      "openlibrary/components/BulkSearch/utils/searchUtils.js",
      "openlibrary/components/HelloWorld.vue",
      "openlibrary/components/IdentifiersInput.vue",
      "openlibrary/components/IdentifiersInput/utils/utils.js",
      "openlibrary/components/LibraryExplorer.vue",
      "openlibrary/components/LibraryExplorer/components/BookCover3D.vue",
      "openlibrary/components/LibraryExplorer/components/BookRoom.vue",
      "openlibrary/components/LibraryExplorer/components/BooksCarousel.vue",
      "openlibrary/components/LibraryExplorer/components/CSSBox.vue",
      "openlibrary/components/LibraryExplorer/components/ClassSlider.vue",
      "openlibrary/components/LibraryExplorer/components/DemoA.vue",
      "openlibrary/components/LibraryExplorer/components/FlatBookCover.vue",
      "openlibrary/components/LibraryExplorer/components/LibraryToolbar.vue",
      "openlibrary/components/LibraryExplorer/components/OLCarousel.vue",
      "openlibrary/components/LibraryExplorer/components/Shelf.vue",
      "openlibrary/components/LibraryExplorer/components/ShelfIndex.vue",
      "openlibrary/components/LibraryExplorer/components/ShelfLabel.vue",
      "openlibrary/components/LibraryExplorer/components/ShelfProgressBar.vue",
      "openlibrary/components/LibraryExplorer/utils.js",
      "openlibrary/components/LibraryExplorer/utils/lcc.js",
      "openlibrary/components/MergeUI/MergeTable.vue",
      "openlibrary/components/MergeUI/utils.js",
      "openlibrary/components/ObservationForm/ObservationService.js",
      "openlibrary/components/ObservationForm/Utils.js",
      "openlibrary/components/lit/OLChip.js",
      "openlibrary/components/lit/OLChipGroup.js",
      "openlibrary/components/lit/OLReadMore.js",
      "openlibrary/components/lit/OlPagination.js",
      "openlibrary/components/lit/OlPopover.js",
      "openlibrary/components/rollupInputCore.js",
      "openlibrary/plugins/openlibrary/js/Browser.js",
      "openlibrary/plugins/openlibrary/js/SearchBar.js",
      "openlibrary/plugins/openlibrary/js/SearchPage.js",
      "openlibrary/plugins/openlibrary/js/SearchUtils.js",
      "openlibrary/plugins/openlibrary/js/Toast.js",
      "openlibrary/plugins/openlibrary/js/add-book.js",
      "openlibrary/plugins/openlibrary/js/add_provider.js",
      "openlibrary/plugins/openlibrary/js/admin.js",
      "openlibrary/plugins/openlibrary/js/affiliate-links.js",
      "openlibrary/plugins/openlibrary/js/autocomplete.js",
      "openlibrary/plugins/openlibrary/js/banner/index.js",
      "openlibrary/plugins/openlibrary/js/bulk-tagger/BulkTagger.js",
      "openlibrary/plugins/openlibrary/js/carousel/Carousel.js",
      "openlibrary/plugins/openlibrary/js/carousel/index.js",
      "openlibrary/plugins/openlibrary/js/dialog.js",
      "openlibrary/plugins/openlibrary/js/edit.js",
      "openlibrary/plugins/openlibrary/js/goodreads_import.js",
      "openlibrary/plugins/openlibrary/js/i18n.js",
      "openlibrary/plugins/openlibrary/js/ile/index.js",
      "openlibrary/plugins/openlibrary/js/ile/utils/SelectionManager/SelectionManager.js",
      "openlibrary/plugins/openlibrary/js/markdown-editor/index.js",
      "openlibrary/plugins/openlibrary/js/merge-request-table/MergeRequestService.js",
      "openlibrary/plugins/openlibrary/js/merge.js",
      "openlibrary/plugins/openlibrary/js/modals/index.js",
      "openlibrary/plugins/openlibrary/js/my-books/MyBooksDropper/ReadingLogForms.js",
      "openlibrary/plugins/openlibrary/js/password-toggle.js",
      "openlibrary/plugins/openlibrary/js/service-worker-init.js"
    ],
    rules: {
      "semi": "off",
      "space-before-function-paren": "off",
      "comma-spacing": "off"
    }
  }
];
