# i18n Contributor's Guide

Want to get started contributing a language towards Open Library internationalization (i18n)?

**Step 1:** Please kindly reach out to us via the volunteer page [https://openlibrary.org/volunteer#translator](https://openlibrary.org/volunteer#translator)

**Step 2:** Watch this overview

[![archive org_details_openlibrary-tour-2020_openlibrary-i18n mp4](https://user-images.githubusercontent.com/978325/122978288-33343700-d34b-11eb-858c-774151af4e87.png)](https://archive.org/embed/openlibrary-tour-2020/openlibrary-i18n.mp4?start=8)

Open Library i18n is handled via the [python Babel library](http://babel.pocoo.org/en/latest/), GNU `gettext`, and the message lists located https://github.com/internetarchive/openlibrary/tree/master/openlibrary/i18n

The messages file format used by the `gettext` toolset is described [here](http://pology.nedohodnik.net/doc/user/en_US/ch-poformat.html), and in the [gettext manual](https://www.gnu.org/software/gettext/manual/html_node/PO-Files.html#PO-Files).

In case you want to get started here are the following steps:

**Step 3:**
To contribute a translation,

Option 1. [Locate the right target language within the project](https://github.com/internetarchive/openlibrary/tree/master/openlibrary/i18n) (e.g. `es` for Spanish) and then click on the `po` file (the raw file where translation strings are contributed), e.g. [this one for Spanish](https://github.com/internetarchive/openlibrary/tree/master/openlibrary/i18n/es). Click on the pencil (edit) option which will bring you to an [editable page like this](https://github.com/internetarchive/openlibrary/edit/master/openlibrary/i18n/es/messages.po) where you can add or edit translations. When you're satisfied with your translations, scroll down to the bottom of the page where it shows **Commit Changes**, leave a description of your changes and make sure to select the radio button of Create a **new branch**. You can call "translations-es" or dash whatever language you're working with. Then, click `Propose Changes` button and you're done! We can follow up if there are any validation issues which may need to be addressed.

Option 2. If you prefer working with `git` you may instead [fork / clone the repository from Github](https://github.com/internetarchive/openlibrary/fork). Install git and follow the instructions on our [Git Cheat Sheet](https://github.com/internetarchive/openlibrary/wiki/Git-Cheat-Sheet) to get set up.

## Adding a new language
A new directory containing a translation template file must be created for each new language.  These can be automatically generated if your Docker environment is set up (see our [Docker README](https://github.com/internetarchive/openlibrary/blob/master/docker/README.md)), or created manually.

Before creating the new directory, you will need to know your language's two-letter ISO 639-1 code.  Make a note of the code once you have found it here: https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes

### Adding a language in a Docker environment
1. Run `docker-compose up -d`

2. Run `docker-compose exec -uroot web ./scripts/i18n-messages add [CODE]`, replacing `[CODE]` with your two-letter ISO 639-1 code.

### Adding a language manually

1. **Create a new folder for your language.** Create a new folder in `/openlibrary/i18n/`, using your two-letter ISO 639-1 code as the folder's name.

2. **Make a copy of the latest messages to translate.** The messages template file, `/openlibrary/i18n/messages.pot` should be copied as `messages.po` (note the difference in extension, the `t` for template is dropped for the copy) to your newly created folder.

### Updating UI to include new language
In order for a new language option to be available in our language drop-down and footer, the [language_list.html](https://github.com/internetarchive/openlibrary/blob/master/openlibrary/templates/languages/language_list.html) template must be updated to include the new language.  An Open Library staff member can do this if you are unfamiliar with HTML.

## Submitting translations
You can edit the `message.po` file using your favourite editor, or a .po specific tool such as [poedit](https://poedit.net/), and send in a Pull Request. Pull Request Guidelines can be found on our [CONTRIBUTING](https://github.com/internetarchive/openlibrary/blob/master/CONTRIBUTING.md) guide and our [Git Cheat Sheet](https://github.com/internetarchive/openlibrary/wiki/Git-Cheat-Sheet).

## Viewing and testing your changes
In order to open your language version of the website in the browser, you will need to setup your docker environment (see our [Docker README](https://github.com/internetarchive/openlibrary/blob/master/docker/README.md)). After having run `docker-compose up -d`, run `docker-compose run --rm -uroot home make i18n` to build the translation files; then e.g. http://localhost:8080/?lang=fr should work.
To view production Open Library in a preferred language, you will need to [adjust your browser language preferences]( https://www.w3.org/International/questions/qa-lang-priorities). You can also use the `lang=` parameter on the URL with a two character language code, e.g. https://openlibrary.org/?lang=fr

## Updating an existing language

If changes have been made to the `.pot` file, to reflect those changes to a given language you need to merge the two files. After setting up your docker environment (see our [Docker README](https://github.com/internetarchive/openlibrary/blob/master/docker/README.md), run the following, replacing `[CODE]` with your two-letter language code:

```bash
docker-compose run --rm -uroot home ./scripts/i18n-messages update [CODE]
```

See our [i18n guideline in the wiki](https://github.com/internetarchive/openlibrary/wiki/Frontend-Guide#internationalization-i18n---for-translators) for important and useful tips.

## Validating your translations

Before submitting a PR with your translations, we recommend correcting any validation errors identified by the following script (replace `[CODE]` with your language code):

```bash
docker-compose exec -uroot web ./scripts/i18n-messages validate [CODE]
```

## Extracting strings from HTML/python files (generating the `.pot` file)

To add i18n support to Open Library, templates and macros are modified to use gettext function calls. For brevity, the gettext function is abbreviated as:

```html
<a href="..">$_("More search options")</a>
```

The messages in the the templates and macros are extracted and `.pot` file is created. After setting up your docker environment (see our [Docker README](https://github.com/internetarchive/openlibrary/blob/master/docker/README.md), run:

```bash
docker-compose run --rm -uroot home ./scripts/i18n-messages extract
```

The `.pot` file contains a `msgid` and a `msgstr` for each translation used. The `msgstr` field for each entry is filled with the translation of the required language and that file is placed at `openlibrary/i18n/$locale/messages.po`:

```bash
mkdir openlibrary/i18n/te
cp openlibrary/i18n/messages.pot openlibrary/i18n/te/messages.po
# edit openlibrary/i18n/te/messages.po and fill the translations
```

The `.po` files are compiled to `.mo` files to be able to use them by gettext system. This is done by `make i18n` automatically when the code is deployed, but needs to be done manually by a maintainer when deploying to dev.openlibrary.org .

## Glossary
- `.po` - Portable object file: This is the file where you will translators will add translations to.
- `.pot` - Portable object template file: This is the file that lists all the strings in Open Library _before_ translation.
- `.mo` - Machine object file: This file is generated by `make i18n`, and is what is used by the actual site.

## Deprecated messages that need updating to the new babel/gettext method:

The codebase has deprecated translations in the [/openlibrary/i18n](https://github.com/internetarchive/openlibrary/tree/master/openlibrary/i18n) directory. In directories of older translations, the `messages.po` file will be replaced with a `legacy-strings.{ISO 639-1 Code}.yml` file.

Languages with deprecated translations:

* hi Hindi
* it Italian
* kn Kannada
* mr Marathi
* nl Dutch

## Internationalizing Infogami Pages

@cdrini has a script to help automate the creation if i18n versions of openlibrary.org infogami pages (e.g. https://openlibrary.org/about v. https://openlibrary.org/about.es):

https://gist.github.com/cdrini/615d75653e1e47115930fa394e83ab17
