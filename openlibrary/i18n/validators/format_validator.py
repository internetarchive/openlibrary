from babel.messages.catalog import TranslationError
from babel.messages.checkers import python_format

from openlibrary.i18n.validator import Validator

class FormatValidator(Validator):

  def __init__(self, message, catalog):
    super().__init__(message, catalog)

  def validate(self):
    errors = []

    if self.message.python_format:
      try:
        python_format(self.catalog, self.message)
      except TranslationError as e:
        if errors:
          errors.append(f'    {e}')
        else:
          errors = [f'    {e}']

    return errors

