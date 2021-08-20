from openlibrary.i18n.validator import Validator

class FuzzyValidator(Validator):

  def __init__(self, message, catalog):
    super().__init__(message, catalog)

  def validate(self):
    errors = []
    if self.message.fuzzy:
      if self.message.lineno:
        errors.append('    Is fuzzy')
      else:
        errors.append('File is fuzzy.  Remove line containing "#, fuzzy" found near the beginning of the file.')

    return errors
