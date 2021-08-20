from abc import ABCMeta, abstractmethod


class Validator(object, metaclass=ABCMeta):
    """Defines a validator for a Babel message.

    Attributes:
      message - The Babel message to be validated
      catalog - The catalog in which the message is found
    """

    @abstractmethod
    def __init__(self, message, catalog):
        self.message = message
        self.catalog = catalog

    @abstractmethod
    def validate(self):
        """Validates a single message.

        Returns a list of error strings, or an empty list if valid
        """
        pass
