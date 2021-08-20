from ..validation_decorator import ValidationDecorator

class FuzzyValidator(ValidationDecorator):

  def __init__(self, validator, catalog):
    super().__init__(validator, catalog)

  def validate(self):
    errors = self.validator.validate()
    if self.validator.message.fuzzy:
      errors = self.validator.validate()

      if self.validator.message.lineno:
        errors.append('    Is fuzzy')
      else:
        errors.append('File is fuzzy.  Remove line containing "#, fuzzy" found near the beginning of the file.')

    return errors if errors else []
