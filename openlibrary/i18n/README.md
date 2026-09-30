# i18n Contributor's Guide

**To add or fix a translation, edit [internetarchive/openlibrary-i18n](https://github.com/internetarchive/openlibrary-i18n), not this directory.**

That repository holds the translations for Open Library, one `locale/<lang>/messages.po` per language. Starting with [#13070](https://github.com/internetarchive/openlibrary/pull/13070), the production image copies each of those files over the matching `<lang>/messages.po` here, so a `messages.po` change merged in this directory for a language openlibrary-i18n has is overwritten and never reaches openlibrary.org.

Until [#13070](https://github.com/internetarchive/openlibrary/pull/13070) ships, production still reads this directory, so a change made in openlibrary-i18n reaches openlibrary.org when #13070 ships, not before. That delay is expected, and the change is not lost.

A new language needs changes in both repositories, so start by opening an issue on [openlibrary-i18n](https://github.com/internetarchive/openlibrary-i18n/issues).

`messages.pot` in this directory is still the source template. It is regenerated here by the `generate-pot` pre-commit hook, and openlibrary-i18n picks up each change automatically.

For how to write translatable strings in templates and code, see https://docs.openlibrary.org/everyone/internationalization.html
