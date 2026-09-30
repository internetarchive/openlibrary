import functools
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from datetime import datetime
from io import BytesIO
from pathlib import Path

import web
from babel.messages import Catalog, Message
from babel.messages.extract import (
    extract_from_dir,
    extract_from_file,
    extract_python,
)
from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po, write_po
from babel.support import Translations

from openlibrary.utils.request_context import req_context

from .validators import _parse_cfmt, validate

root = os.path.dirname(__file__)


def error_color_fn(text: str) -> str:
    """Styles the text for printing to console with error color."""
    return "\033[91m" + text + "\033[0m"


def success_color_fn(text: str) -> str:
    """Styles the text for printing to console with success color."""
    return "\033[92m" + text + "\033[0m"


def warning_color_fn(text: str) -> str:
    """Styles the text for printing to console with warning color."""
    return "\033[93m" + text + "\033[0m"


def get_untracked_files(dirs: list[str], extensions: tuple[str, ...] | str) -> set[Path]:
    """Returns a set of all currently untracked files with specified extension(s)."""
    untracked_files = {
        Path(line)
        for dir in dirs
        for line in subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", dir],
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        ).stdout.split("\n")
        if line.endswith(extensions)
    }

    return untracked_files


def _compile_translation(po, mo):
    try:
        with open(po, "rb") as po_file:
            catalog = read_po(po_file)

        with open(mo, "wb") as mo_file:
            write_mo(mo_file, catalog)
        print("compiled", po, file=web.debug)
    except Exception as e:
        print("failed to compile", po, file=web.debug)
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
        po_path = os.path.join(root, locale, "messages.po")

        if os.path.exists(po_path):
            num_errors = 0
            error_print: list[str] = []
            with open(po_path, "rb") as po_file:
                catalog = read_po(po_file)
            for message, warnings, errors in _validate_catalog(catalog):
                for w in warnings:
                    print(warning_color_fn(f"openlibrary/i18n/{locale}/messages.po:{message.lineno}: ") + w)

                    if errors:
                        num_errors += len(errors)
                        error_print.append(
                            error_color_fn(f"openlibrary/i18n/{locale}/messages.po:{message.lineno}: ") + repr(message.string),
                        )
                        error_print.extend(errors)

            if num_errors == 0:
                print(success_color_fn(f'Translations for locale "{locale}" are valid!'))
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
    return [d for d in os.listdir(root) if (os.path.isdir(os.path.join(root, d)) and os.path.exists(os.path.join(root, d, "messages.po")))]


def extract_templetor(fileobj, keywords, comment_tags, options):
    """Extract i18n messages from web.py templates."""
    try:
        instring = fileobj.read().decode("utf-8")
        # Replace/remove inline js '\$' which interferes with the Babel python parser:
        cleaned_string = instring.replace(r"\$", "")
        code = web.template.Template.generate_code(cleaned_string, fileobj.name)
        f = BytesIO(code.encode("utf-8"))  # Babel wants bytes, not strings
    except Exception as e:
        print("Failed to extract " + fileobj.name + ":", repr(e), file=web.debug)
        return []
    return extract_python(f, keywords, comment_tags, options)


# Babel wraps every line of messages.pot at 76 chars, including the ``#:`` location
# comments that list which templates use each string. When a string gains or loses one
# file, that wrapping re-flows the whole block and rewrites filenames that didn't change,
# turning unrelated edits into overlapping diffs and causing spurious merge conflicts.
# Writing with a very large width disables wrapping, so each location comment stays on a
# single line and adding a file just extends that line — unrelated changes no longer
# share, or conflict on, any lines. (``width=0`` does *not* work: Babel mirrors
# ``xgettext`` and always wraps comments at 76 regardless, while only unwrapping the
# message text — the opposite of what we want.)
POT_WIDTH = 1_000_000


def extract_messages(sources: list[str], verbose: bool, skip_untracked: bool):
    # The creation date is hard-coded to prevent merge conflicts from i18n auto-updates.
    # Occasional manual bumps are fine to make it more up-to-date
    fixed_creation_date = datetime.fromisoformat("2026-04-28 18:58-0400")
    catalog = Catalog(
        project="Open Library",
        copyright_holder="Internet Archive",
        creation_date=fixed_creation_date,
    )
    METHODS = [
        ("**.py", "python"),
        ("**.html", "openlibrary.i18n:extract_templetor"),
        ("**.jinja", "jinja2.ext:babel_extract"),
    ]
    COMMENT_TAGS = ["NOTE:"]

    skipped_files = set()
    if skip_untracked:
        skipped_files = get_untracked_files(sources, (".py", ".html", ".jinja"))

    for source in map(Path, sources):
        counts: dict[Path, int] = {}

        if source.is_file():
            extracted = extract_from_file(
                next(method for (glb, method) in METHODS if source.match(glb)),
                source,
                comment_tags=COMMENT_TAGS,
                strip_comment_tags=True,
            )

            # Make it have the same shape as extract_from_dir
            extracted = ((source, source, *x) for x in extracted)
        else:
            extracted = extract_from_dir(
                source,
                METHODS,
                comment_tags=COMMENT_TAGS,
                strip_comment_tags=True,
            )

            # Make it have the same shape as extract_from_file
            extracted = ((source / x[0], x[0], *x[1:]) for x in extracted)

        for file_path, partial_path, lineno, message, comments, context in extracted:
            if file_path in skipped_files:
                continue
            counts[file_path] = counts.get(file_path, 0) + 1
            catalog.add(message, None, [(str(partial_path), lineno)], auto_comments=comments)

        if verbose:
            for file_path, count in counts.items():
                print(f"{count}\t{file_path}", file=sys.stderr)

    path = os.path.join(root, "messages.pot")
    with open(path, "wb") as f:
        write_po(f, catalog, include_lineno=False, width=POT_WIDTH)

    print("Updated strings written to", path)


def compile_translations(locales: list[str]):
    locales_to_update = locales or get_locales()

    for locale in locales_to_update:
        po_path = os.path.join(root, locale, "messages.po")
        mo_path = os.path.join(root, locale, "messages.mo")

        if os.path.exists(po_path):
            _compile_translation(po_path, mo_path)


def _format_args(message: Message) -> dict | tuple:
    """Build stand-in arguments shaped like the ones the msgid expects at runtime.

    GetText/ungettext apply ``value % args`` (or ``% kwargs``) to whichever string
    they resolve, so a translation must accept the same arguments as its msgid.
    A msgid with no placeholders gets ``{}``: Jinja's newstyle gettext applies
    ``% variables`` even when there are none. Ints are used because they satisfy
    %s, %d and %f alike, so a %d applied to a runtime str is not caught.
    """
    if not message.python_format:
        return {}
    ids = message.id if isinstance(message.id, (list, tuple)) else [message.id]
    names: set[str] = set()
    positional = 0
    for msgid in ids:
        pieces = [p for p in _parse_cfmt(str(msgid)) if p != "%%"]
        names.update(p[2 : p.index(")")] for p in pieces if p.startswith("%("))
        positional = max(positional, sum(1 for p in pieces if not p.startswith("%(")))
    if names:
        return dict.fromkeys(names, 1)
    if positional:
        return (1,) * positional
    return {}


def _render_errors(message: Message) -> list[str]:
    """Errors that formatting this translation would raise at render time."""
    args = _format_args(message)
    strings = message.string if isinstance(message.string, (list, tuple)) else [message.string]
    errors = []
    for msgstr in strings:
        if not msgstr:
            continue
        try:
            msgstr % args
        except (TypeError, ValueError, KeyError) as e:
            errors.append(f"line {message.lineno}: {msgstr!r}: {type(e).__name__}: {e}")
            continue
        # `"%s" % {...}` does not raise; it renders the dict's repr.
        if isinstance(args, dict) and any(p != "%%" and not p.startswith("%(") for p in _parse_cfmt(msgstr)):
            errors.append(f"line {message.lineno}: {msgstr!r}: positional placeholder where the msgid has none")
    return errors


def check_po_file(po_path: str) -> list[str]:
    """Reasons this .po file is unsafe to ship, or an empty list if it is safe.

    Unsafe means it would break ``make i18n`` (does not parse or compile), the
    compiled .mo would not load the way ``load_translations`` loads it (e.g. a
    malformed Plural-Forms header), or a translation that gets compiled would
    raise when rendered. Fuzzy entries are skipped because ``write_mo`` leaves
    them out of the .mo.
    """
    try:
        with open(po_path, "rb") as po_file:
            catalog = read_po(po_file, abort_invalid=True)
        mo = BytesIO()
        write_mo(mo, catalog)
        mo.seek(0)
        translations = Translations(mo)
        for n in range(1000):
            translations.plural(n)
    except Exception as e:
        return [f"does not parse/compile/load: {type(e).__name__}: {e}"]

    errors = []
    for message in catalog:
        if message.id and not message.fuzzy:
            errors.extend(_render_errors(message))
    return errors


def install_translations(source: str, dest: str = root) -> dict[str, list[str]]:
    """Copy ``<source>/<locale>/messages.po`` over ``<dest>/<locale>/messages.po``
    for every locale whose file passes ``check_po_file``.

    A locale that fails keeps whatever file ``dest`` already has. Returns each
    locale's problems; an empty list means it was installed.
    """
    locales = sorted(d for d in os.listdir(source) if os.path.isfile(os.path.join(source, d, "messages.po")))
    if not locales:
        raise ValueError(f"no locales with a messages.po found in {source}")

    results = {}
    for locale in locales:
        src_po = os.path.join(source, locale, "messages.po")
        results[locale] = check_po_file(src_po)
        if not results[locale]:
            os.makedirs(os.path.join(dest, locale), exist_ok=True)
            shutil.copyfile(src_po, os.path.join(dest, locale, "messages.po"))
    return results


def update_translations(locales: list[str]):
    locales_to_update = locales or get_locales()
    print(f"Updating {locales_to_update}")

    pot_path = os.path.join(root, "messages.pot")
    with open(pot_path, "rb") as pot_file:
        template = read_po(pot_file)

    for locale in locales_to_update:
        po_path = os.path.join(root, locale, "messages.po")

        if os.path.exists(po_path):
            with open(po_path, "rb") as po_file:
                catalog = read_po(po_file)
            catalog.update(template)
            with open(po_path, "wb") as f:
                write_po(f, catalog)
            print("updated", po_path)
        else:
            print(f"ERROR: {po_path} does not exist...")

    compile_translations(locales_to_update)


def check_status(locales: list[str]):
    locales_to_update = locales or get_locales()
    pot_path = os.path.join(root, "messages.pot")

    with open(pot_path, "rb") as f:
        message_ids = {message.id for message in read_po(f)}

    for locale in locales_to_update:
        po_path = os.path.join(root, locale, "messages.po")

        if os.path.exists(po_path):
            with open(po_path, "rb") as f:
                catalog = read_po(f)
                ids_with_translations = {message.id for message in catalog if "".join(message.string or "").strip()}

            ids_completed = message_ids.intersection(ids_with_translations)
            validation_errors = _validate_catalog(catalog)
            total_warnings = 0
            total_errors = 0
            for message, warnings, errors in validation_errors:
                total_warnings += len(warnings)
                total_errors += len(errors)

            percent_complete = len(ids_completed) / len(message_ids) * 100
            all_green = percent_complete == 100 and total_warnings == 0 and total_errors == 0
            total_color = success_color_fn if all_green else lambda x: x
            warnings_color = warning_color_fn if total_warnings > 0 else success_color_fn
            errors_color = error_color_fn if total_errors > 0 else success_color_fn
            percent_color = success_color_fn if percent_complete == 100 else warning_color_fn if percent_complete > 25 else error_color_fn
            print(
                total_color(
                    "\t".join(
                        [
                            locale,
                            percent_color(f"{percent_complete:6.2f}% complete"),
                            warnings_color(f"{total_warnings:2d} warnings"),
                            errors_color(f"{total_errors:2d} errors"),
                            f"openlibrary/i18n/{locale}/messages.po",
                        ]
                    )
                )
            )

            if len(locales) == 1:
                print(f"---- validate {locale} ----")
                validate_translations(locales)
        else:
            print(f"ERROR: {po_path} does not exist...")


def generate_po(args):
    if args:
        po_dir = os.path.join(root, args[0])
        pot_src = os.path.join(root, "messages.pot")
        po_dest = os.path.join(po_dir, "messages.po")

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


@functools.cache
def load_translations(lang: str):
    mo_path = os.path.join(root, lang, "messages.mo")

    if os.path.exists(mo_path):
        return Translations(open(mo_path, "rb"))


class GetText:
    def __call__(self, string, *args, **kwargs):
        """Translate a given string to the language of the current locale."""
        # Get the website locale from the global ctx.lang variable, set in i18n_loadhook
        try:
            lang = req_context.get().lang
        except LookupError:
            lang = None

        if not lang:
            print(
                "Warning: No language set in request context. Returning untranslated string.",
                file=web.debug,
            )
            lang = "en"

        translations = load_translations(lang)
        value = (translations and translations.ugettext(string)) or string

        if args:
            value = value % args
        elif kwargs:
            value = value % kwargs

        return value

    def __getattr__(self, key):
        from infogami.utils.i18n import strings

        # for backward-compatability
        return strings.get("", key)


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
    translations = load_translations(req_context.get().lang)
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


gettext = GetText()
ugettext = gettext
lgettext = LazyGetText()
_ = gettext
