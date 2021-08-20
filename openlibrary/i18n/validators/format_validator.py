from babel.messages.catalog import TranslationError
from babel.messages.checkers import python_format

from ..validation_decorator import ValidationDecorator

class FormatValidator(ValidationDecorator):

  def __init__(self, validator, catalog):
    super().__init__(validator, catalog)

  def validate(self):
    errors = self.validator.validate()

    if self.validator.message.python_format:
      try:
        python_format(self.catalog, self.validator.message)
      except TranslationError as e:
        if errors:
          errors.append(f'    {e}')
        else:
          errors = [f'    {e}']

    return errors if errors else []

