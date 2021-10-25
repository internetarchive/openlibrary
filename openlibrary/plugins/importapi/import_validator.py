from typing import List, Dict, Any

# Set of the import object's required fields:
REQUIRED_KEYS = {
    'title',
    'source_records',
    'authors',
    'publishers',
    'publish_date'
}

# List of validation types and their validator functions:
OPERATIONS_ORDER = [
    ('type', '_validate_type'),
    ('min_length', '_validate_length'),
    ('item_type', '_validate_list_items'),
    ('has_keys', '_validate_required_keys')
]

# Validation configurations for types related to import objects.
# Keys are the validation types, and the values are objects defining
# what needs validation.
VALIDATIONS = {
    'title': {
        'type': str,
        'min_length': 1
    },
    'source_records': {
        'type': list,
        'min_length': 1
    },
    'authors': {
        'type': list,
        'min_length': 1,
        'item_type': 'author'
    },
    'publishers': {
        'type': list,
        'min_length': 1,
        'item_type': 'publisher'
    },
    'publish_date': {
        'type': str,
        'min_length': 1
    },
    'author': {
        'type': dict,
        'has_keys': [
            {
                # Required field:
                'key': 'name',
                # Validation type of field:
                'type': 'author_name'
            }
        ]
    },
    'author_name': {
        'type': str,
        'min_length': 1
    },
    'publisher': {
        'type': str,
        'min_length': 1
    }
}


class RequiredFieldError(Exception):
    """Defines errors related to missing required fields."""

    def __init__(self, f: List[str]):
        self.f = ", ".join(f)

    def __str__(self):
        return f"Missing required fields: {self.f}"


class InvalidValueError(Exception):
    """Defines errors in which a value is invalid."""

    def __init__(self, f: List[str]):
        self.f = ", ".join(f)

    def __str__(self):
        return f"Invalid values for the following fields: {self.f}"


class import_validator(object):

    def validate(self, data: Dict[str, Any]):
        """Validates the given import data.

        Performs two passes of validation for an import object.  First,
        we check that all required fields are present in the object.
        Next, we validate the required values based on configurations
        found in the VALIDATIONS object.

        If any required fields are missing, a RequiredFieldError containing
        the missing keys is raised and this method terminates without
        further validation.

        Returns True if the import object is valid.
        """

        missing_keys = [key for key in REQUIRED_KEYS if key not in data]
        if len(missing_keys):
            raise RequiredFieldError(missing_keys)

        invalid_values = []
        for key in REQUIRED_KEYS:
            is_valid = self._validate(data[key], key)
            if not is_valid:
                invalid_values.append(key)
        if len(invalid_values):
            raise InvalidValueError(invalid_values)
        return True

    def _validate(self, value, key) -> bool:
        """Validates a value based on the configuration.

        Runs all required validations in order for the
        given key and value.  If any validation fails,
        this method returns False without running further
        necessary validations.

        Returns True if all validations for a value pass.
        """

        validations = VALIDATIONS[key]
        for v in OPERATIONS_ORDER:
            type = v[0]
            func = v[1]
            if type in validations:
                f = getattr(self, func)
                if not f(value, validations[type]):
                    return False
        return True

    def _validate_length(self, target, min_length) -> bool:
        """Validates the minimum length of a target string or list.

        Returns True if the given target's length is equal to or
        greater than the given min_length.
        """

        return len(target) >= min_length

    def _validate_type(self, target: Any, expected_type: type) -> bool:
        """Validates the type of the given target value

        Returns True if the target's type matches the given expected_type.
        """

        return type(target) == expected_type

    def _validate_list_items(self, list, type) -> bool:
        """Validates each item in a list.

        Uses the validation requirements of the given type to validate
        each item in the list. If any item fails validation, this method
        returns False without validating remaining list items.

        Returns True if all list items are valid.
        """

        for item in list:
            if not self._validate(item, type):
                return False
        return True

    def _validate_required_keys(self, target: Dict, keys: List[Dict[str, str]]) -> bool:
        """Validates required keys for the given dict.

        This method determines if the given target dict has each required key, and
        whether the corresponding value is valid. Each item in the keys list
        represents a required field and its optional validation type:

        item['key'] is the required field.  If present, item['type'] is the validation
        type.

        Returns True if the target dict is valid.
        """
        for entry in keys:
            if entry['key'] not in target:
                return False
            if 'type' in entry and not self._validate(
                target[entry['key']], entry['type']):
                return False
        return True
