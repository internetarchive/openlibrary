from abc import ABCMeta, abstractmethod

from .validator import Validator

class ValidationDecorator(Validator, metaclass=ABCMeta):

  @abstractmethod
  def __init__(self, validator, catalog):
    super().__init__(validator.message)
    self.validator = validator
    self.catalog = catalog
