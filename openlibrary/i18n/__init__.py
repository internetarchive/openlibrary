import sys
from typing import Iterator

import web
import os
import shutil

import babel
from babel._compat import BytesIO
from babel.support import Translations
from babel.messages import Catalog, Message
from babel.messages.pofile import read_po, write_po
from babel.messages.mofile import write_mo
from babel.messages.extract import extract_from_file, extract_from_dir, extract_python

from .validators import validate

root = os.path.dirname(__file__)


def error_color_fn(text: str) -> str:
    """Styles the text for printing to console with error color."""
    return '\033[91m' + text + '\033[0m'


def success_color_fn(text: str) -> str:
    """Styles the text for printing to console with success color."""
    return '\033[92m' + text + '\033[0m'


def warning_color_fn(text: str) -> str:
    """Styles the text for printing to console with warning color."""
    return '\033[93m' + text + '\033[0m'


def _compile_translation(po, mo):
    try:
        catalog = read_po(open(po, 'rb'))

        f = open(mo, 'wb')
        write_mo(f, catalog)
        f.close()
        print('compiled', po, file=web.debug)
    except Exception as e:
        print('failed to compile', po, file=web.debug)
        raise e


def _validate_catalog(
    catalog: Catalog,
) -> Iterator[tuple[Message, list[str], list[str]]]:
    for message in catalog:
        if message.lineno:
            warnings: list[str] = []
            errors: list[str] = validate(message, catalog)

            if message.fuzzy:
                warnings.append(f'"{message.string}" is fuzzy')

            if warnings or errors:
                yield message, warnings, errors


def validate_translations(args: list[str]):
    """Validates all locales passed in as arguments.

    If no arguments are passed, all locales will be validated.

    Returns a dictionary of locale-validation error count
    key-value pairs.
    """
    locales = args or get_locales()
    results = {}

    for locale in locales:
        po_path = os.path.join(root, locale, 'messages.po')

        if os.path.exists(po_path):
            num_errors = 0
            error_print: list[str] = []
            catalog = read_po(open(po_path, 'rb'))
            for message, warnings, errors in _validate_catalog(catalog):
                for w in warnings:
                    print(
                        warning_color_fn(
                            f'openlibrary/i18n/{locale}/messages.po:{message.lineno}: '
                        )
                        + w
                    )

                    if errors:
                        num_errors += len(errors)
                        error_print.append(
                            error_color_fn(
                                f'openlibrary/i18n/{locale}/messages.po:{message.lineno}: '
                            )
                            + repr(message.string),
                        )
                        error_print.extend(errors)

            if num_errors == 0:
                print(
                    success_color_fn(f'Translations for locale "{locale}" are valid!')
                )
            else:
                for e in error_print:
                    print(e)
                print(error_color_fn("\nValidation failed..."))
                print(error_color_fn("Please correct the errors before proceeding."))
            results[locale] = num_errors
        else:
            print(f'Portable object file for locale "{locale}" does not exist.')

    return results


def get_locales():
    return [
        d
        for d in os.listdir(root)
        if (
            os.path.isdir(os.path.join(root, d))
            and os.path.exists(os.path.join(root, d, 'messages.po'))
        )
    ]


def extract_templetor(fileobj, keywords, comment_tags, options):
    """Extract i18n messages from web.py templates."""
    try:
        instring = fileobj.read().decode('utf-8')
        # Replace/remove inline js '\$' which interferes with the Babel python parser:
        cleaned_string = instring.replace(r'\$', '')
        code = web.template.Template.generate_code(cleaned_string, fileobj.name)
        f = BytesIO(code.encode('utf-8'))  # Babel wants bytes, not strings
    except Exception as e:
        print('Failed to extract ' + fileobj.name + ':', repr(e), file=web.debug)
        return []
    return extract_python(f, keywords, comment_tags, options)


def extract_messages(dirs: list[str]):
    catalog = Catalog(project='Open Library', copyright_holder='Internet Archive')
    METHODS = [("**.py", "python"), ("**.html", "openlibrary.i18n:extract_templetor")]
    COMMENT_TAGS = ["NOTE:"]

    for d in dirs:
        extracted = extract_from_dir(
            d, METHODS, comment_tags=COMMENT_TAGS, strip_comment_tags=True
        )

        counts: dict[str, int] = {}
        for filename, lineno, message, comments, context in extracted:
            counts[filename] = counts.get(filename, 0) + 1
            catalog.add(message, None, [(filename, lineno)], auto_comments=comments)

        for filename, count in counts.items():
            path = filename if d == filename else os.path.join(d, filename)
            print(f"{count}\t{path}", file=sys.stderr)

    path = os.path.join(root, 'messages.pot')
    f = open(path, 'wb')
    write_po(f, catalog)
    f.close()

    print('wrote template to', path)


def compile_translations(locales: list[str]):
    locales_to_update = locales or get_locales()

    for locale in locales_to_update:
        po_path = os.path.join(root, locale, 'messages.po')
        mo_path = os.path.join(root, locale, 'messages.mo')

        if os.path.exists(po_path):
            _compile_translation(po_path, mo_path)


def update_translations(locales: list[str]):
    locales_to_update = locales or get_locales()
    print(f"Updating {locales_to_update}")

    pot_path = os.path.join(root, 'messages.pot')
    template = read_po(open(pot_path, 'rb'))

    for locale in locales_to_update:
        po_path = os.path.join(root, locale, 'messages.po')
        mo_path = os.path.join(root, locale, 'messages.mo')

        if os.path.exists(po_path):
            catalog = read_po(open(po_path, 'rb'))
            catalog.update(template)

            f = open(po_path, 'wb')
            write_po(f, catalog)
            f.close()
            print('updated', po_path)
        else:
            print(f"ERROR: {po_path} does not exist...")

    compile_translations(locales_to_update)


def check_status(locales: list[str]):
    locales_to_update = locales or get_locales()
    pot_path = os.path.join(root, 'messages.pot')

    with open(pot_path, 'rb') as f:
        message_ids = {message.id for message in read_po(f)}

    for locale in locales_to_update:
        po_path = os.path.join(root, locale, 'messages.po')

        if os.path.exists(po_path):
            with open(po_path, 'rb') as f:
                catalog = read_po(f)
                ids_with_translations = {
                    message.id for message in catalog if ''.join(message.string).strip()
                }

            ids_completed = message_ids.intersection(ids_with_translations)
            validation_errors = _validate_catalog(catalog)
            total_warnings = 0
            total_errors = 0
            for message, warnings, errors in validation_errors:
                total_warnings += len(warnings)
                total_errors += len(errors)

            percent_complete = len(ids_completed) / len(message_ids) * 100
            all_green = (
                percent_complete == 100 and total_warnings == 0 and total_errors == 0
            )
            total_color = success_color_fn if all_green else lambda x: x
            warnings_color = (
                warning_color_fn if total_warnings > 0 else success_color_fn
            )
            errors_color = error_color_fn if total_errors > 0 else success_color_fn
            percent_color = (
                success_color_fn
                if percent_complete == 100
                else warning_color_fn
                if percent_complete > 25
                else error_color_fn
            )
            print(
                total_color(
                    '\t'.join(
                        [
                            locale,
                            percent_color(f'{percent_complete:6.2f}% complete'),
                            warnings_color(f'{total_warnings:2d} warnings'),
                            errors_color(f'{total_errors:2d} errors'),
                            f'openlibrary/i18n/{locale}/messages.po',
                        ]
                    )
                )
            )

            if len(locales) == 1:
                print(f'---- validate {locale} ----')
                validate_translations(locales)
        else:
            print(f"ERROR: {po_path} does not exist...")


def generate_po(args):
    if args:
        po_dir = os.path.join(root, args[0])
        pot_src = os.path.join(root, 'messages.pot')
        po_dest = os.path.join(po_dir, 'messages.po')

        if os.path.exists(po_dir):
            if os.path.exists(po_dest):
                print(f"Portable object file already exists at {po_dest}")
            else:
                shutil.copy(pot_src, po_dest)
                os.chmod(po_dest, 0o666)
                print(f"File created at {po_dest}")
        else:
            os.mkdir(po_dir)
            os.chmod(po_dir, 0o777)
            shutil.copy(pot_src, po_dest)
            os.chmod(po_dest, 0o666)
            print(f"File created at {po_dest}")
    else:
        print("Add failed. Missing required locale code.")


@web.memoize
def load_translations(lang):
    po = os.path.join(root, lang, 'messages.po')
    mo_path = os.path.join(root, lang, 'messages.mo')

    if os.path.exists(mo_path):
        return Translations(open(mo_path, 'rb'))


@web.memoize
def load_locale(lang):
    try:
        return babel.Locale(lang)
    except babel.UnknownLocaleError:
        pass


class GetText:
    def __call__(self, string, *args, **kwargs):
        """Translate a given string to the language of the current locale."""
        # Get the website locale from the global ctx.lang variable, set in i18n_loadhook
        translations = load_translations(web.ctx.lang)
        value = (translations and translations.ugettext(string)) or string

        if args:
            value = value % args
        elif kwargs:
            value = value % kwargs

        return value

    def __getattr__(self, key):
        from infogami.utils.i18n import strings

        # for backward-compatability
        return strings.get('', key)


class LazyGetText:
    def __call__(self, string, *args, **kwargs):
        """Translate a given string lazily."""
        return LazyObject(lambda: GetText()(string, *args, **kwargs))


class LazyObject:
    def __init__(self, creator):
        self._creator = creator

    def __str__(self):
        return web.safestr(self._creator())

    def __repr__(self):
        return repr(self._creator())

    def __add__(self, other):
        return self._creator() + other

    def __radd__(self, other):
        return other + self._creator()


def ungettext(s1, s2, _n, *a, **kw):
    # Get the website locale from the global ctx.lang variable, set in i18n_loadhook
    translations = load_translations(web.ctx.lang)
    value = translations and translations.ungettext(s1, s2, _n)
    if not value:
        # fallback when translation is not provided
        if _n == 1:
            value = s1
        else:
            value = s2

    if a:
        return value % a
    elif kw:
        return value % kw
    else:
        return value


def gettext_territory(code):
    """Returns the territory name in the current locale."""
    # Get the website locale from the global ctx.lang variable, set in i18n_loadhook
    locale = load_locale(web.ctx.lang)
    return locale.territories.get(code, code)


gettext = GetText()
ugettext = gettext
lgettext = LazyGetText()
_ = gettext
