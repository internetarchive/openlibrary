# Goal: Create a program that can separate Jsons out into diffs. Here's what I need:

# I need to know all keys added in the second commit.  (Keys of set B that are not in set A.)
# I need all keys added in that commit. (Keys of A that are not in the set of keys of B)
# I need all keys changed. Now, changes can have specific qualities, based on the types of key:
# Potential types of the key: Single Value (Boolean, String, Number, null)-- these can only be deleted or changed.
#                             Array (convert the values into sets, and compare them.)
#                           Dict: Recurse.
# Therefore, I need to define a few elements/operations. INSERT KEY (value) and DELETE KEY( value).
#
# So, let's examine this in cases. What does it actually mean to undo an action? We have 3 types of values.
# STAGES FOR UNDOING:
#       undoing an add
#               -simple case: delete if not changed or deleted in a later diff.
#               -add an element to a list- search that list for that element, and if it's there, delete it.
#               - adding a dictionary- delete all keys that were added with the new dict.  If said dict is then empty, delete it.
#        undoing a delete:
#               simple case: add back the key:value pair that was deleted, if it was not added again by a later dict
#               deleted from a list: append that element back to the list.
#               deleted a key from a dict: add that key and value back, if it does not already exist.
#       undoing a replace
#               simple case: return to the previous version's value
#               lists: ???? if all goes well, a list changing should never occur, it will only have elements of it being added or deleted.
#               dicts: revert all key:Values within the dict back to normal, if they are not touched by the later commit.
# Replace:
#       Do I want a recursive definition? Quite possibly. After all, if it's recursive, it will properly allow me to deal with all sorts of potential structures. Now, problem-- how do I handle this data?
# How do I have the paths properly?
# Thought -> Pass the appropriate prefix into the function. Then-- Okay, let's just Haskell it.
# On internal dict: [f'{prefix}/{newKey}' for newKey in diffDict()]


# Stages for recording changes: Simple keys/values, easyy.
# Let's see about lists now. We have two types, ordered and unordered. This will be tricky-ish. How will I accomplish this?  Let's assume that people aren't (usually) manually created,
# And usually only function from diff_dicts, and the like. This way, we have an easy pipeline to go to work with, and can potentially ignore some inconveniences.
# So let's see. Desired behavior when performing the Add operation:
#              - If adding a simple key value, check if the key already exists.  If it doesn't exist, add it.
#              - If adding a value to a list, check to see if there's an index argument. If not, append it to the end of the list.
#              - If navigating to a value that doesn't exist, create keys on the way to what doesn't exist.  This begs the question, should it be a different type
#                             to add to arrays? I think maybe, yes actually-- I like the idea of that.
# Yeah, the elegant way to do this is to remove Replace, and instead use a variety of insert keys, but is that invertible? Let's think about it this way.
#              - Is the insert method invertible? It certainly is, it is undone by pop.
# Alright, I think I need to bite the bullet, and use the 'path' method. Okay.  This way, each add is responsible for a single data point.
# This is a pitfall. Alright, I think I need to be careful, because the problem with this, is that 'adding to a dict is an intrinsically separate operation from adding to a list.
# But both use the same way of indexing in. How can I avoid ambiguity, here? Do I need to avoid it?
#    Let's say that I'm adding to it with a key.
# Alright, back to breaking down the types of adding.
#         - Adding a dict key and value.
#         - Adding an element to a list (orderless)
#         - Adding an element to a list (ordered)
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal


@dataclass
class Change:
    def __init__(
        self, path: str, value: str | list | int = "", old_value: str | list | int = ""
    ):
        self.path = path
        self.old_value = old_value
        self.value = value

    def apply(self, doc: dict):
        pass

    def invert(self):
        pass


# Inverting an Add means that it deletes.
class Add(Change):
    def __init__(
        self, path: str, value: str | list | int = "", old_value: str | list | int = ""
    ):
        super().__init__(path, value, old_value)

    def apply(self, document: dict) -> dict:
        doc = deepcopy(document)
        entry = doc
        key_list = self.path.split("/")
        for key in key_list[:-1]:
            try:
                entry = entry[key]
            except:
                entry[key] = {}
                entry = entry[key]
        # If the value is a list, and there exists a key:value pair at the full end of the path, we want to instead
        # add the elements of the value into the list.
        if isinstance(entry, list):
            if key_list[-1] == "*" or int(key_list[-1]) > len(entry) - 1:
                entry.append(self.value)
            else:
                entry.insert(int(key_list[-1]), self.value)
        else:
            entry.setdefault(key_list[-1], self.value)
        return doc

    def invert(self):
        return Delete(self.path, "", old_value=self.value)

    def __repr__(self):
        return f'Add({self.path}, {self.value}, {self.old_value})'


# The Delete class does not need a value, normally. However, when deleting elements from a list, the value equals
# the value of the element to be deleted.
# So, Delete's path needs to record the index for re-adding. Does this mean a recursive function is best?????
# Add's information: key, value, and path. The path for a list includes the index after the /.
# Delete's old value is the value that was deleted. This is not necessary when it has a singular value, as in deleting an element from a list.
class Delete(Change):
    def __init__(
        self, path: str, value: str | list | int = "", old_value: str | list | int = ""
    ):
        super().__init__(path, value, old_value)

    def apply(self, document: dict | list):
        doc = deepcopy(document)
        entry = doc
        key_list = self.path.split("/")
        for key in key_list[:-1]:
            try:
                entry = entry[key]
            except:
                return doc
        # If the value is a list, then we want to delete based off of the index provided at the end of the path.
        if isinstance(entry, list):
            if key_list[-1] == "*" or int(key_list[-1]) > len(entry) - 1:
                entry.pop()
            else:
                entry.pop(int(key_list[-1]))
        else:
            try:
                entry.pop(key_list[-1])
            except:
                pass
        return doc

    def invert(self):
        return Add(self.path, self.value)

    def __repr__(self):
        return f'Delete({self.path}, {self.value}, {self.old_value})'


@dataclass
class Patch:

    def __init__(self, change_list: list[Change] | None = None):
        self.change_list = change_list if change_list else []

    def append(self, change: Change):
        self.change_list.append(change)

    # Python won't let me typehint this as a 'Patch' object.
    def extend(self, changes):
        self.change_list.extend(changes.change_list)

    def apply(self, doc):
        changed_doc = doc
        for change in self.change_list:
            change.apply(changed_doc)
        return changed_doc

    # out of place operation, returns a new Patch object.
    def invert(self):
        return Patch([change.invert() for change in reversed(self.change_list)])

    def __repr__(self):
        return f'Patch({self.change_list!s})'


def find_key_by_value(find_value, index: dict):
    for key, value in index.items():
        if value == find_value:
            return key
    return None


def diff_unordered_list(list1: list, list2: list, path: str = "") -> Patch:
    item_id_to_count: dict = {}
    item_id_to_item: dict = {}
    item_id: int = 0
    change_list = Patch([])
    for elem in list2:
        if elem not in item_id_to_item.values():
            item_id_to_item[item_id] = elem
            item_id += 1
        if item_id := find_key_by_value(elem, item_id_to_item):
            item_id_to_count[item_id] = item_id_to_count.get(item_id, 0) + 1
    for elem in list1:
        if elem not in item_id_to_item.values():
            item_id_to_item[item_id] = elem
            item_id += 1
        if item_id := find_key_by_value(elem, item_id_to_item):
            item_id_to_count[item_id] = item_id_to_count.get(item_id, 0) - 1

    for key, value in item_id_to_count.items():
        if value > 0:
            for i in range(value):
                change_list.append(Add(f'{path}/*', key))
        elif value < 0:
            for i in range(abs(value)):
                change_list.append(Delete(f'{path}/*', value="", old_value=key))
    return change_list


# What do I prioritize, in
def diff_ordered_list(input1: list, input2: list, path: str = "") -> Patch:
    changelist = Patch([])
    shared_values = find_shared_sequences(input1, input2)
    deleted_indices = [x for x in range(len(input1)) if x not in shared_values[0]]
    added_indices = [y for y in range(len(input2)) if y not in shared_values[1]]
    for i in range(len(deleted_indices)):
        changelist.append(
            Delete(
                f'{path + "/" if path else ""}{deleted_indices[i] -i}',
                "",
                old_value=input1[deleted_indices[i]],
            )
        )
    for addition in added_indices:
        changelist.append(
            Add(f'{path + "/" if path else ""}{addition}', input2[addition])
        )
    return changelist


# Alright, this is a problem. From the microscopic view (only seeing if two indices of a list are different), there's
# no actual way to determine if the operation was
# An add or a delete.  This means that any solution I have will have to
# examine other pieces of the list, as well. This means a recursive method might not be ideal.
# Now, here's a thought. Okay. Let's actually define a 'Swap' change, maybe? No, alright, this is going to be a problem. Let's figure it out.
# So my current issue has to do with figuring out a way to efficiently diff sections of a list.
# step 1, match if the same, adding the index object to the shared_values array.
# step 2, if not the same, increment the right until they are the same, and continue. If right goes over the
# step 3: To handle duplicates;  do I need to run  this multiple times, for each possible configuration? That feels like the best way, but also like it could get
# expensive to manage.
# Alright, let's think of it this way.   There's a, per repetition of a^x b^y c^z, etc, it'll be a total of x*y*z combinations.  How often  will this occur?
# Probably not often. However, this will lead to issues in situations of......  Alright, let's consider the possibility of
def find_shared_sequences(input1: list, input2: list):
    right_pointer = 0
    left_pointer = 0
    shared_doc1_indices = []
    shared_doc2_indices = []
    while left_pointer < len(input1):
        if (
            right_pointer < len(input2)
            and input1[left_pointer] == input2[right_pointer]
        ):
            shared_doc1_indices.append(left_pointer)
            shared_doc2_indices.append(right_pointer)
            left_pointer += 1
            right_pointer += 1
        else:
            pointer_buffer = right_pointer
            while right_pointer < len(input2):
                if input1[left_pointer] == input2[right_pointer]:
                    break
                right_pointer += 1
            if right_pointer >= len(input2):
                left_pointer += 1
                right_pointer = pointer_buffer
    return (shared_doc1_indices, shared_doc2_indices)


def diff_dicts(
    doc1: dict,
    doc2: dict,
    prefix="",
    default_list_handler: Literal["ordered", "unordered"] = "ordered",
    overrides: dict[str, Literal['ordered', 'unordered']] | None = None,
):
    if not overrides:
        overrides = {}
    doc1_keys = set(doc1.keys())
    doc2_keys = set(doc2.keys())
    shared = doc1_keys.intersection(doc2_keys)
    print(shared)
    deleted = doc1_keys.difference(doc2_keys)
    added = doc2_keys.difference(doc1_keys)
    change_list = Patch()
    for key in shared:
        if doc1[key] != doc2[key]:
            if type(doc1[key]) is not type(doc2[key]):
                change_list.extend(
                    [
                        Delete(f'{prefix + "/" if prefix else ""}{key}', "", doc1[key]),
                        Add(f'{prefix + "/" if prefix else ""}{key}', doc2[key]),
                    ]
                )
            elif type(doc1[key]) is list:
                method = overrides.get(key, default_list_handler)
                if method == "unordered":
                    change_list.extend(
                        diff_unordered_list(
                            doc1[key],
                            doc2[key],
                            path=f'{prefix + "/" if prefix else ""}',
                        )
                    )
                else:
                    change_list.extend(
                        diff_ordered_list(
                            doc1[key],
                            doc2[key],
                            path=f'{prefix + "/" if prefix else ""}',
                        )
                    )

            elif type(doc1[key]) is dict:
                change_list.extend(
                    diff_dicts(
                        doc1[key],
                        doc2[key],
                        prefix=f'{prefix + "/" if prefix else ""}{key}',
                        default_list_handler=default_list_handler,
                        overrides=overrides,
                    )
                )
            else:
                change_list.extend(
                    [
                        Delete(f'{prefix + "/" if prefix else ""}{key}', "", doc1[key]),
                        Add(f'{prefix + "/" if prefix else ""}{key}', doc2[key]),
                    ]
                )
    for key in deleted:
        change_list.append(Delete(f'{prefix + "/" if prefix else ""}{key}'))
    for key in added:
        change_list.append(Add(f'{prefix + "/" if prefix else ""}{key}', doc2[key]))
    return change_list


# [start here]
def test_diff_ordered_list():

    assert diff_ordered_list([1, 2, 3, 4], [1, 2, 4, 5]) == Patch(
        [Delete("2", "", "3"), Add("3", "5")]
    ), "testing diff with a replacement of a value"
    assert diff_ordered_list([], [1, 2, 3, 4]) == Patch(
        [Add("0", 1), Add("1", 2), Add("2", 3), Add("3", 4)]
    ), "testing diff adding to an empty dict"
    assert diff_ordered_list([1, 2, 3], []) == Patch(
        [Delete("0", "", "1"), Delete("0", "", "2"), Delete("0", "", "3")]
    ), "Testing deleting all elements from a list."
    assert diff_ordered_list([0, 1, 2], [2, 1, 0]) == Patch(
        [Delete("1", "", 1), Delete("1", "", "2"), Add("0", 2), Add("1", 1)]
    ), "testing rearrangement of elements"
    assert diff_ordered_list([{"1": "2"}], [{"2": "1"}]) == Patch(
        [Delete("0", "", {'1': '2'}), Add("0", {'2': '1'})]
    ), "testing replacement with dict elements"


def test_apply_add():

    assert Add("foo", "bar").apply({}) == {
        "foo": "bar"
    }, "testing simple application of Add on an empty dict"
    assert Add("foo/foo", "bar").apply({}) == {
        "foo": {"foo": "bar"}
    }, "testing simple adding of a dict-based value to an empty dict."
    assert Add("foo/3", 1).apply({"foo": [5, 6, 2, 3, 4]}) == {
        "foo": [5, 6, 2, 1, 3, 4]
    }, "Testing inserting a value into a list."
    assert Add("foo/*", 1).apply({"foo": [5, 6, 2, 3, 4]}) == {
        "foo": [5, 6, 2, 3, 4, 1]
    }, "Testing appending a value to a list."
    assert Add("foo", [1, 2, 3, 4]).apply({}) == {
        "foo": [1, 2, 3, 4]
    }, "testing adding a new key with a list value."
    assert Add("foo/6", 6).apply({"foo": [5, 6, 6, 1]}) == {
        "foo": [5, 6, 6, 1, 6]
    }, "Testing inserting past the list length."
    assert Add("foo", "bar").apply({"foo": "not bar"}) == {
        "foo": "not bar"
    }, "testing adding to a dict where the value already exists."


def test_apply_delete():

    assert Delete("foo").apply({"bar": "foo"}) == {
        "bar": "foo"
    }, "testing a failed attempt at removing a key"
    assert (
        Delete("foo").apply({"foo": "bar"}) == {}
    ), "testing removal of last entry in a dict."
    assert Delete("foo/3").apply({"foo": [1, 1, 2, 1, 4]}) == {
        "foo": [1, 1, 2, 4]
    }, "testing removal of  an specific index in a list."
    assert Delete("foo/*").apply({"foo": [1, 2, 3, 4, 5]}) == {
        "foo": [1, 2, 3, 4]
    }, "testing removal of the last element in a list."
    assert Delete("foo/6").apply({"foo": [1, 2, 3]}) == {
        "foo": [1, 2]
    }, "testing removal of an index out of scope in the list."
    assert Delete("foo/bar").apply({"foo": {"bar": "foo", "foo": "bar"}}) == {
        "foo": {"foo": "bar"}
    }, "testing removal of item in a nested dict."
    assert (
        Delete("foo").apply({"foo": [1, 2, 3, 4]}) == {}
    ), "Testing full removal of an array."
    assert Delete("foo/3").apply({"foo": [1, 2, 3, {"bar": "foo"}]}) == {
        "foo": [1, 2, 3]
    }, "testing removal of a dict in an array"


def test_diff_adds():
    assert diff_dicts({}, {"foo": "bar"}) == Patch(
        [Add("foo", "bar")]
    ), "Error in adding a single value to an empty dict."
    assert diff_dicts({"foo": {}}, {"foo": {"foo": "bar"}}) == Patch(
        [Add("foo/foo", "bar")]
    ), "Error in adding a key to a nested dict"
    assert diff_dicts({"foo": [1, 2, 3, 4]}, {"foo": [1, 2, 3, 4, 5, 6]}) == Patch(
        [Add("foo", [5, 6])]
    ), "Error in adding values to an array."
    assert diff_dicts({"foo": [1, 2, 3, 4]}, {"foo": [1, 1, 1, 1, 2, 3, 4]}) == Patch(
        [Add("foo", [1, 1, 1])]
    ), "Error in tracking the number of duplicate values added."


def test_diff_deletes():
    assert diff_dicts({"foo": "bar"}, {}) == Patch(
        [Delete("foo")]
    ), "Error in deleting a key from a dictionary."
    assert diff_dicts(
        {"foo": {"foo": "bar", "bar": "foo"}}, {"foo": {"foo": "bar"}}
    ) == Patch([Delete("foo/bar")]), "Error deleting a value in a nested dict"
    assert diff_dicts({"foo": [1, 2, 3, 4]}, {"foo": [1, 2, 3]}) == Patch(
        [Delete("foo", [4])]
    ), "error deleting a value in an array"
    assert diff_dicts({"foo": {"foo": "bar"}, "bar": "foo"}, {"bar": "foo"}) == Patch(
        [Delete("foo")]
    ), "Error in deleting a dict."
    assert diff_dicts({"foo": [1, 2, 3, 4]}, {"foo": [1, 3]}) == Patch(
        [Delete("foo", [2, 4])]
    ), "error in deleting a non-final element in a list."
