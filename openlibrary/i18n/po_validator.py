from .validator import Validator
from .validators.fuzzy_validator import FuzzyValidator

class POValidator(Validator):
  
  def __init__(self, message):
    super().__init__(message)

  def validate(self):
    return self.errors
