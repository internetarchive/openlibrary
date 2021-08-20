import xml.etree.ElementTree as etree

from ..validation_decorator import ValidationDecorator

class HTMLValidator(ValidationDecorator):

  def __init__(self, validator, catalog):
    super().__init__(validator, catalog)

  def validate(self):
    errors = self.validator.validate()

    if self.validator.message.lineno:
      results = self._validate(f'{self.validator.message.id}', f'{self.validator.message.string}')

      if results:
        if errors:
          errors.append(f'    {results}')
        else:
          errors = [f'    {results}']

    return errors if errors else []

  def _validate(self, msgid, msgstr):
    try:
      id_tree = etree.fromstring(f'<root>{self._html_encode(msgid)}</root>')
      str_tree = etree.fromstring(f'<root>{self._html_encode(msgstr)}</root>')
    
      result =  self.trees_equal(id_tree, str_tree)
      if result:
        return 'HTML mismatch'
    except Exception as e:
      return f'{e}'

  def _html_encode(self, str):
    str = str.replace('&', '&amp;')

    return str

  def trees_equal(self, el1: etree.Element, el2: etree.Element, error=False):
    """
    Check if the tree data is the same
    >>> trees_equal(etree.fromstring('<root />'), etree.fromstring('<root />'))
    True
    >>> trees_equal(etree.fromstring('<root x="3" />'),
    ...               etree.fromstring('<root x="7" />'))
    True
    >>> trees_equal(etree.fromstring('<root x="3" y="12" />'),
    ...               etree.fromstring('<root x="7" />'), error=False)
    False
    >>> trees_equal(etree.fromstring('<root><a /></root>'),
    ...               etree.fromstring('<root />'), error=False)
    False
    >>> trees_equal(etree.fromstring('<root><a /></root>'),
    ...               etree.fromstring('<root><a>Foo</a></root>'), error=False)
    True
    >>> trees_equal(etree.fromstring('<root><a href="" /></root>'),
    ...               etree.fromstring('<root><a>Foo</a></root>'), error=False)
    False
    """
    try:
        assert el1.tag == el2.tag
        assert set(el1.attrib.keys()) == set(el2.attrib.keys())
        assert len(el1) == len(el2)
        for c1, c2 in zip(el1, el2):
            self.trees_equal(c1, c2)
    except AssertionError as e:
        if error:
            return True
        else:
            return False
    return False