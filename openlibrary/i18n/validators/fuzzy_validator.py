from openlibrary.i18n.validator import Validator

class FuzzyValidator(Validator):
  """Validator used to find fuzzy messages"""
  def __init__(self, message, catalog):
    super().__init__(message, catalog)

  def validate(self):
    """Returns an error list if the message is fuzzy.
    
    If a fuzzy flag is found above the header of a `.po`
    file, the message will have `None` as its line number.
    """
    errors = []
    if self.message.fuzzy:
      if self.message.lineno:
        errors.append('    Is fuzzy')
      else:
        errors.append('File is fuzzy.  Remove line containing "#, fuzzy" found near the beginning of the file.')

    return errors
