Want to get started contributing a language towards Open Library internationalization (i18n)?

Kindly take a look at this [Issue thread](https://github.com/internetarchive/openlibrary/issues/871) for more information.

## About

Open Library i18n is handled via the [python Babel library](http://babel.pocoo.org/en/latest/), GNU `gettext`, and the message lists located https://github.com/internetarchive/openlibrary/tree/master/openlibrary/i18n

The messages file format used by the `gettext` toolset is described [here](http://pology.nedohodnik.net/doc/user/en_US/ch-poformat.html), and in the [gettext manual](https://www.gnu.org/software/gettext/manual/html_node/PO-Files.html#PO-Files).

The codebase has now deprecated code and strings located here: https://github.com/internetarchive/openlibrary/tree/master/openlibrary/plugins/openlibrary/i18n

There are a small number of messages in the following languages:

* es Spanish
* hi Hindi
* it Italian
* kn Kannada
* mr Marathi

In case you want to get started here are the following steps:

## Step 1: Clone the Repository from Github
Install git and run the following command on the command line:
```
git clone https://github.com/internetarchive/openlibrary/
cd openlibrary/
```

## Step 2: Create a new folder for your language
At the end of this document is a detailed table of languages and their code. Create a new folder in `/openlibrary/i18n/` with the code name of the language that you wish to translate to.

## Step 3: Make a copy of the latest messages to translate
The messages template file, `/openlibrary/i18n/messages.pot` should be copied as `messages.po` (note the difference in extension, the `t` for template is dropped for the copy) to your newly created folder.

## Step 4: Make the translations and send a PR
You can edit the `message.po` file using your favourite editor, or a .po specific tool such as [poedit](https://poedit.net/), and send in a Pull Request. Pull Request Guidelines can be found on our [README](https://github.com/internetarchive/openlibrary/blob/master/Readme.md) and [CONTRIBUTING](https://github.com/internetarchive/openlibrary/blob/master/CONTRIBUTING.md) guide.

## Viewing and testing your changes:
To view Open Library in a preferred language, you will need to adjust your browser language preferences. To force a page to appear in a language, you can also user the lang= parameter on the URL with a two character language code, e.g. https://openlibrary.org/?lang=fr

## Introduction
To add i18n support to Open Library, templates and macros are modified to use gettext function calls. For brevity, the gettext function is abbreviated as :

    <a href="..">$_("More search options")</a>
    
The messages in the the templates and macros are extracted and .pot file is created:
    
    $ ./scripts/i18n-messages extract
    created openlibrary/i18n/messages.pot
    $ cat openlibrary/i18n/messages.pot

    #: templates/site.html:29
    msgid "Open Library"
    msgstr ""
    #: templates/site.html:52
    msgid "Search"
    msgstr ""
    
The .pot file contains msgid and msgstr for each translation used. The `msgstr` field for each entry is filled with the translation of the required language and that file is placed at openlibrary/i18n/$locale/messages.po:

    $ mkdir openlibrary/i18n/te
    $ cp openlibrary/i18n/messages.pot openlibrary/i18n/te/messages.po
    $ # edit openlibrary/i18n/te/messages.po and fill the translations
    
The .po files needs to be compiled to .mo files to be able to use them by gettext system:

 $ ./scripts/i18n-messages compile
    compiling openlibrary/i18n/te/messages.po
    compiling openlibrary/i18n/it/messages.po
    
## Glossary:
.po - portable object

.pot - portable object template

.mo - machine object
