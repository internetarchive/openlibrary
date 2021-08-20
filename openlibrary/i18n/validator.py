from abc import ABCMeta, abstractmethod

class Validator(object, metaclass=ABCMeta):

  @abstractmethod
  def __init__(self, message):
    self.message = message
    self.errors = []

  @abstractmethod
  def validate(self):
    pass
