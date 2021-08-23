from babel.messages.catalog import TranslationError
from babel.messages.checkers import python_format


def validate(message, catalog):
    errors = _validate_fuzzy(message)
    errors.extend(_validate_format(message, catalog))

    return errors


def _validate_format(message, catalog):
        """Returns an error list if the format strings are mismatched.

        Relies on Babel's built-in python format checker.
        """
        errors = []

        if message.python_format:
            try:
                python_format(catalog, message)
            except TranslationError as e:
                errors.append(f'    {e}')

        return errors

def _validate_fuzzy(message):
        """Returns an error list if the message is fuzzy.

        If a fuzzy flag is found above the header of a `.po`
        file, the message will have `None` as its line number.
        """
        errors = []
        if message.fuzzy:
            if message.lineno:
                errors.append('    Is fuzzy')
            else:
                errors.append(
                    'File is fuzzy.  Remove line containing "#, fuzzy"'
                    ' found near the beginning of the file.'
                )

        return errors