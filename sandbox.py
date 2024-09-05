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
#       Do I want a recursive definition? Quite possibly. After all, if it's recursive,
#          it will properly allow me to deal with all sorts of potential structures. Now, problem-- how do I handle this data?
# How do I have the paths properly?
# Thought -> Pass the appropriate prefix into the function. Then-- Okay, let's just Haskell it.
# On internal dict: [f'{prefix}/{newKey}' for newKey in diffDict()]


# Stages for recording changes: Simple keys/values, easyy.
# Let's see about lists now. We have two types, ordered and unordered.
# This will be tricky-ish. How will I accomplish this?  Let's assume that Patches aren't (usually) manually created,
# And usually only function from diff_dicts, and the like. This way, we have an easy pipeline to go to work with, and can potentially ignore some inconveniences.
# So let's see. Desired behavior when performing the Add operation:
#              - If adding a simple key value, check if the key already exists.  If it doesn't exist, add it.
#              - If adding a value to a list, check to see if there's an index argument. If not, append it to the end of the list.
#              - If navigating to a value that doesn't exist, create keys on the way to what doesn't exist.  This begs the question, should it be a different type
#                             to add to arrays? I think maybe, yes actually-- I like the idea of that.
# Yeah, the elegant way to do this is to remove Replace, and instead use a variety of insert keys, but is that invertible? Let's think about it this way.
#              - Is the insert method invertible? It certainly is, it is undone by pop.
# Alright, I think I need to bite the bullet, and use the 'path' method. Okay.  This way, each add is responsible for a single data point.
# This is a pitfall. Alright, I think I need to be careful, because the problem with this,
# is that 'adding to a dict is an intrinsically separate operation from adding to a list.
# But both use the same way of indexing in. How can I avoid ambiguity, here? Do I need to avoid it?
#    Let's say that I'm adding to it with a key.
# Alright, back to breaking down the types of adding.
#         - Adding a dict key and value.
#         - Adding an element to a list (orderless)
#         - Adding an element to a list (ordered)
from copy import deepcopy
from dataclasses import dataclass, field
from contextlib import suppress
from typing import Literal


# When should an Add be inverted?  And what does it mean, what's the desired behavior?
# The desired behavior is split into three sections.
#       -normal data type: if the value still matches the value from the add, then it should be deleted.  If it was a complex data type, then ...
#           all keys matching it should be changed? No, that doesn't sound right. Let's consider the scenario where I've added in an author name.
#           deleting this is relatively trivial. If the author name is still noted at that address, then, remove it.
# Alright, I think this might benefit from splitting it up into two
# different typese for adds/deletes respectively. Also, worth noting-- this is going to
# find the fastest solution regardless, so there will not be unnecessary in betweens-- and even if they are, they'll be governed by order
# Information needed to see if an Add should be undone (because it's a function on this add, all of this needs to be available to deletes. ):
#                   - The path of the value to check.
#                   - Is the value in a list?  (This is checkable in function.)
#                           - If so, if it's unordered, then remove the first
#                       instance of it in the list. Do nothing if the element is not in the list.
#                           - If the list is ordered, then ????? [[return later]] (This will
#               need to be aware of intermediary changes, so I think I'll have to actually
#                                generate and compare/add the diffs together of the next function.)
#                   - If the value's not in a list, then just check if it matches the old value. if it does, then delete it.
#


class HashableDict(dict):
    def __hash__(self):
        return hash(tuple(sorted(self.items())))


def convert_to_hashable(
    doc: dict[any, any] | list[any]
) -> HashableDict[any, any] | tuple[any]:
    if type(doc) is dict:
        hashable_dict = HashableDict()
        for key in doc.keys():
            hashable_dict[key] = convert_to_hashable(dict[key])
        return hashable_dict
    elif type(doc) is list:
        return tuple([convert_to_hashable(elem) for elem in doc])
    else:
        return doc


@dataclass
class Change:

    path: list[str | int]
    value: str | list | int = ""
    list_type: Literal["ol", "ul", None] = None
    index: None | int = None

    def apply(
        self,
        doc: dict,
        conflict_options: Literal["error", "keep-old", "overwrite"] = "keep-old",
    ):
        pass

    def invert(self) -> 'Change':
        pass


def traverse_nested_dicts_and_lists(
    path: list, document: dict, create_missing_path: bool
):

    for key in path[:-1]:
        if type(entry) is list:
            try:
                key = int(key)
                entry = entry[key]
            except:
                raise ValueError("List indices must be integers")
        elif type(entry) is dict:
            if create_missing_path:
                entry.setdefault(key, {})
            entry = entry[key]
        else:
            raise ValueError(
                "Error: Cannot index into a type that is not Dict or List."
            )
    return (entry, path[-1])


# Inverting an Add means that it deletes.
# Consider if In-Place/Out-Of-Place should be an input option.
class Add(Change):

    # TODO: Create a tripartite set of options to replace overwrite. Error with conflict, keep old, or overwrite.
    def apply(
        self,
        doc: dict,
        conflict_options: Literal["error", "keep-old", "overwrite"] = "keep-old",
    ) -> dict:
        entry = doc
        for key in self.path[:-1]:
            if type(entry) is list:
                try:
                    key = int(key)
                    entry = entry[key]
                except:
                    raise ValueError("List indices must be integers")
            elif type(entry) is dict:
                entry.setdefault(key, {})
                entry = entry[key]
            else:
                raise ValueError(
                    "Cannot index into a value other than a dictionary  or list."
                )
        # If the value is a list, and there exists a key:value pair at the full end of the path, we want to instead
        # add the elements of the value into the list.

        add_point = entry.get(self.path[-1], None)
        if isinstance(add_point, list):
            if self.list_type == "ul" or (
                self.list_type == "ol"
                and self.index is not None
                and self.index >= len(add_point)
            ):
                add_point.append(self.value)
            elif self.list_type == "ol" and self.index is not None:
                add_point.insert(self.index, self.value)
            else:
                if self.list_type is not None and self.index is None:
                    raise ValueError(
                        f'No index exists for list type: [{self.list_type}]'
                    )
                else:
                    raise ValueError(f'Invalid List Type')
        else:
            if conflict_options == "overwrite":
                entry[self.path[-1]] = self.value
            elif conflict_options == "error":
                raise ValueError(
                    f'Error in adding to key at path {self.path}, as a value already exists at that key.'
                )

            entry.setdefault(self.path[-1], self.value)

        return doc

    def invert(self) -> Change:
        return Delete(self.path, self.value, self.list_type, self.index)


# The Delete class does not need a value, normally. However, when deleting elements from a list, the value equals
# the value of the element to be deleted.
# So, Delete's path needs to record the index for re-adding. Does this mean a recursive function is best?????
# Add's information: key, value, and path. The path for a list includes the index after the /.
# Delete's old value is the value that was deleted. This is not necessary when it has a singular value, as in deleting an element from a list.
class Delete(Change):

    def apply(
        self,
        doc: dict,
        conflict_options: Literal["error", "keep-old", "overwrite"] = "keep-old",
    ):
        entry = doc
        for key in self.path[:-1]:
            if type(entry) is list:
                try:
                    key = int(key)
                    entry = entry[key]
                except:
                    return doc
            elif type(entry) is dict:
                entry = entry.get(key, None)
            if not entry:
                return doc

        # If the value is a list, then we want to delete based off of the index.
        if type(entry) is dict:
            add_point = entry.get(self.path[-1], None)
        elif type(entry) is list:
            try:
                key = int(self.path[-1])
                add_point = entry[key]
            except:
                raise ValueError("List indexes must be integer values.")
        if add_point is None:
            return doc
        if conflict_options == "overwrite" or add_point == self.value:
            entry.pop(self.path[-1])
        else:
            if isinstance(add_point, list):
                if (
                    self.index is not None
                    and self.list_type == "ol"
                    and (
                        conflict_options == "overwrite"
                        or add_point[self.index] == self.value
                    )
                ):
                    add_point.pop(self.index)
                elif self.list_type == "ul":
                    with suppress(ValueError):
                        add_point.remove(self.value)
        return doc

    def invert(self):
        return Add(self.path, self.value, self.list_type, self.index)


@dataclass
class Patch:

    change_list: list[Change] = field(default_factory=list)

    # DONE THIS: Consider implementing Dataclass properly; look into how their constructors are defined.
    def __post_init__(self):
        self.change_list = [] if type(self.change_list) is None else self.change_list

    def append(self, change: Change):
        self.change_list.append(change)

    def extend(self, changes: 'Patch| list[Change]') -> None:
        if type(changes) is list:
            self.change_list.extend(changes)
        else:
            self.change_list.extend(changes.change_list)

    # DONE THIS: Remove DeepCopy from Adds/Deletes, and only run via Patch.
    def apply(self, doc: dict, conflict_options="keep-old") -> dict:
        changed_doc = deepcopy(doc)
        for change in self.change_list:
            changed_doc = change.apply(changed_doc, conflict_options)
        return changed_doc

    # out of place operation, returns a new Patch object.
    def invert(self) -> 'Patch':
        return Patch([change.invert() for change in reversed(self.change_list)])

    def __repr__(self):
        return f'Patch({self.change_list!s})'


def diff_unordered_list(list1: list, list2: list, path: str = "") -> Patch:
    item_to_count: dict = {}
    hash_to_original: dict = {}
    change_list = Patch([])
    for elem in list2:
        elem_hash = convert_to_hashable(elem)
        hash_to_original.setdefault(elem_hash, elem)
        hash_to_original[elem]
        item_to_count.setdefault(elem_hash, 0)
        item_to_count[elem_hash] += 1
    for elem in list1:
        elem_hash = convert_to_hashable(elem)
        hash_to_original.setdefault(elem_hash, elem)
        item_to_count.setdefault(elem_hash, 0)
        item_to_count[elem_hash] -= 1

    for key, value in item_to_count.items():
        if value > 0:
            for i in range(value):
                change_list.append(Add(path, hash_to_original[key], list_type="ul"))
        elif value < 0:
            for i in range(abs(value)):
                change_list.append(Delete(path, hash_to_original[key], list_type="ul"))
    return change_list


# What do I prioritize, in
def diff_ordered_list(input1: list, input2: list, path: list[str | int] = []) -> Patch:
    changelist = Patch([])
    shared_values = find_shared_sequences(input1, input2)
    deleted_indices = [x for x in range(len(input1)) if x not in shared_values[0]]
    added_indices = [y for y in range(len(input2)) if y not in shared_values[1]]
    for i in range(len(deleted_indices)):
        changelist.append(
            Delete(
                path,
                value=input1[deleted_indices[i]],
                list_type="ol",
                index=deleted_indices[i] - i,
            )
        )
    for addition in added_indices:
        changelist.append(Add(path, input2[addition], list_type="ol", index=addition))
    return changelist


# Alright, this is a problem. From the microscopic view (only seeing if two indices of a list are different), there's
# no actual way to determine if the operation was
# An add or a delete.  This means that any solution I have will have to
# examine other pieces of the list, as well. This means a recursive method might not be ideal.
# Now, here's a thought. Okay. Let's actually define a 'Swap' change, maybe? No, alright, this is going to be a problem. Let's figure it out.
# So my current issue has to do with figuring out a way to efficiently diff sections of a list.
# step 1, match if the same, adding the index object to the shared_values array.
# step 2, if not the same, increment the right until they are the same, and continue. If right goes over the
# step 3: To handle duplicates;  do I need to run  this multiple times, for each possible configuration? That feels like
# the best way, but also like it could get expensive to manage.
# Alright, let's think of it this way.   There's a, per repetition of a^x b^y c^z, etc, it'll be a total of x*y*z combinations.  How often  will this occur?
# Probably not often. However, this will lead to issues in situations of......  Alright, let's consider the possibility of


# [TODO: Implement that idea of running this function once for each permutation of duplicates being what it skips to. Then, after doing this, take the shortest
# Patch path. Additional note: Consider improving performance of this by, rather than having to iterate through the list to find the next occcurence, save the
# ids of the values in a way thtat will let you automatically O(1) access the next one. ]
def find_shared_sequences(input1: list, input2: list):
    right_pointer = 0
    left_pointer = 0
    shared_doc1_indices: list[int] = []
    shared_doc2_indices: list[int] = []
    # Alright, I now have the ability to check indices for specific elements in O(1) time. That's helpful.
    # Now what I need is to generate different ways of pairing up the lists, so that's going to be...
    # Lists of lists? Yeah, because each time I do, I copy and extend with the new value?
    # And then I can quickly check each index to see if they're in order. If not, it can get removed.
    # How to calculate different pairs... It's easy if the element appears once in either list. [1], [1,2,3] becomes [(1,1), (1,2), (1,3)]
    # Now, it becomes slightly harder if both pairs have two or more occurrences. [1,2], [1,2,3] becomes [[(1,1), (2,2)],
    # [(1,1), (2,3)], [(1,2), (2,3)], [(2,1)], [(1,3)]]
    # Invalid are [(1,2), (2,1)]... No, I don't need full iteration, because I already know I want to match where possible. So, the 3 options become:
    # [(1,1),(2,2)], [(1,1), (2,3)], [(1,2), (2,3)], which is...choose 2 from 3, alright.  This makes sense, combinations don't care about order.
    # Now, how to generate this lists of tuples in terms of a function....
    # The problem is that I cannot do in blindly based on the matching indexes for a singular element. I will need partial matches, because the ways in which other sequences
    # work will be interfered with by this proccess.

    # Belay this: I don't yet know if it's necessary, let's wait on that.

    # Building this index takes care of counting duplicates, which is needed in order to properly get the most efficient version of differences.
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
    path: list[str | int] = [],
    default_list_handler: Literal["ordered", "unordered"] = "unordered",
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
                        Delete(path + [key], doc1[key]),
                        Add(path + [key], doc2[key]),
                    ]
                )
            elif type(doc1[key]) is list:
                method = overrides.get(key, default_list_handler)
                if method == "unordered":
                    change_list.extend(
                        diff_unordered_list(
                            doc1[key],
                            doc2[key],
                            path=path + [key],
                        )
                    )
                else:
                    change_list.extend(
                        diff_ordered_list(
                            doc1[key],
                            doc2[key],
                            path=path + [key],
                        )
                    )

            elif type(doc1[key]) is dict:
                change_list.extend(
                    diff_dicts(
                        doc1[key],
                        doc2[key],
                        path=path + [key],
                        default_list_handler=default_list_handler,
                        overrides=overrides,
                    )
                )
            else:
                change_list.extend(
                    [
                        Delete(path + [key], doc1[key]),
                        Add(path + [key], doc2[key]),
                    ]
                )
    for key in deleted:
        change_list.append(Delete(path + [key], doc1[key]))
    for key in added:
        change_list.append(Add(path + [key], doc2[key]))
    return change_list


def undo_arbitrary_version_changes():
    pass


# [start here]


# Permutations to test:
#    1: Insertion, Deletion
#    2: As normal, into an ordered list, unordered list.
#    3: Forced, Non-Forced
#    4: Successful, Failing
#    5: iinversion


# TODO: Look into Pytest shorthand for applying tests to different values in an array, rather than manually entering each one. ([inputs], failure message) for example, as each cell.
def test_diff_ordered_list():

    assert diff_ordered_list([1, 2, 3, 4], [1, 2, 4, 5]) == Patch(
        [Delete([], 3, "ol", 2), Add([], 5, "ol", 3)]
    ), "testing diff with a replacement of a value"
    assert diff_ordered_list([], [1, 2, 3, 4]) == Patch(
        [
            Add([], 1, "ol", 0),
            Add([], 2, "ol", 1),
            Add([], 3, "ol", 2),
            Add([], 4, "ol", 3),
        ]
    ), "testing diff adding to an empty dict"
    assert diff_ordered_list([1, 2, 3], []) == Patch(
        [Delete([], 1, "ol", 0), Delete([], 2, "ol", 0), Delete([], 3, "ol", 0)]
    ), "Testing deleting all elements from a list."
    assert diff_ordered_list([0, 1, 2], [2, 1, 0]) == Patch(
        [
            Delete([], 1, "ol", 1),
            Delete([], 2, "ol", 1),
            Add([], 2, "ol", 0),
            Add([], 1, "ol", 1),
        ]
    ), "testing rearrangement of elements"
    assert diff_ordered_list([{"1": "2"}], [{"2": "1"}]) == Patch(
        [Delete([], {"1": "2"}, "ol", 0), Add([], {"2": "1"}, "ol", 0)]
    ), "testing replacement with dict elements"


def test_apply_add():

    assert Add(["foo"], "bar").apply({}) == {
        "foo": "bar"
    }, "testing simple application of Add on an empty dict"
    assert Add(["foo", "foo"], "bar").apply({}) == {
        "foo": {"foo": "bar"}
    }, "testing simple adding of a dict-based value to an empty dict."
    assert Add(["foo"], 1, "ol", 3).apply({"foo": [5, 6, 2, 3, 4]}) == {
        "foo": [5, 6, 2, 1, 3, 4]
    }, "Testing inserting a value into a list."
    assert Add(["foo"], 1, "ul").apply({"foo": [5, 6, 2, 3, 4]}) == {
        "foo": [5, 6, 2, 3, 4, 1]
    }, "Testing appending a value to a list."
    assert Add(["foo"], [1, 2, 3, 4]).apply({}) == {
        "foo": [1, 2, 3, 4]
    }, "testing adding a new key with a list value."
    assert Add(["foo"], 6, "ol", 6).apply({"foo": [5, 6, 6, 1]}) == {
        "foo": [5, 6, 6, 1, 6]
    }, "Testing inserting past the list length."
    assert Add(["foo"], "bar").apply({"foo": "not bar"}) == {
        "foo": "not bar"
    }, "testing adding to a dict where the value already exists."
    assert Add(["foo"], "bar").apply(
        {"foo": "not bar"}, conflict_options="overwrite"
    ) == {
        "foo": "bar"
    }, "testing  an overwrite add to a dict where the value already exists."
    assert Add(["foo", 1, "foo"], "bar").apply({"foo": [0, {}]}) == {
        "foo": [0, {"foo": "bar"}]
    }


def test_apply_delete():

    assert Delete(["foo"], "foo").apply({"bar": "foo"}) == {
        "bar": "foo"
    }, "testing a failed attempt at removing a key"
    assert Delete(["foo"], "bar").apply({"foo": "foo"}) == {
        "foo": "foo"
    }, "testing a failed attempt at removing a key with the wrong value"
    assert (
        Delete(["foo"], "bar").apply({"foo": "bar"}) == {}
    ), "testing removal of last entry in a dict."
    assert Delete(["foo"], 1, "ol", 3).apply({"foo": [1, 1, 2, 1, 4]}) == {
        "foo": [1, 1, 2, 4]
    }, "testing removal of  an specific index in a list."
    assert Delete(["foo"], 5, "ul").apply({"foo": [1, 2, 3, 4, 5]}) == {
        "foo": [1, 2, 3, 4]
    }, "testing removal of an element by value in an unordered list"
    assert Delete(["foo"], "8", "ul").apply({"foo": [1, 2, 3]}) == {
        "foo": [1, 2, 3]
    }, "testing removal of an element not within an unordered list"
    assert Delete(["foo", "bar"], "foo").apply(
        {"foo": {"bar": "foo", "foo": "bar"}}
    ) == {"foo": {"foo": "bar"}}, "testing removal of item in a nested dict."
    assert (
        Delete(["foo"], [1, 2, 3, 4]).apply({"foo": [1, 2, 3, 4]}) == {}
    ), "Testing full removal of an array."
    assert Delete(["foo"], {"bar": "foo"}, "ul").apply(
        {"foo": [1, 2, 3, {"bar": "foo"}]}
    ) == {"foo": [1, 2, 3]}, "testing removal of a dict in an array"
    assert Delete(["foo", 1, "foo"], "bar").apply({"foo": [0, {"foo": "bar"}]}) == {
        "foo": [0, {}]
    }


def test_diff_adds():
    assert diff_dicts({}, {"foo": "bar"}) == Patch(
        [Add(["foo"], "bar")]
    ), "Error in adding a single value to an empty dict."
    assert diff_dicts({"foo": {}}, {"foo": {"foo": "bar"}}) == Patch(
        [Add(["foo", "foo"], "bar")]
    ), "Error in adding a key to a nested dict"
    assert diff_dicts({"foo": [1, 2, 3, 4]}, {"foo": [1, 2, 3, 4, 5, 6]}) == Patch(
        [Add(["foo"], 5, "ul"), Add(["foo"], 6, "ul")]
    ), "Error in adding values to an array."
    assert diff_dicts(
        {"foo": [1, 2, 3, 4]},
        {"foo": [1, 1, 1, 1, 2, 3, 4]},
        overrides={"foo": "ordered"},
    ) == Patch(
        [Add(["foo"], 1, "ol", 1), Add(["foo"], 1, "ol", 2), Add(["foo"], 1, "ol", 3)]
    ), "Error in tracking the number of duplicate values added."


def test_diff_deletes():
    assert diff_dicts({"foo": "bar"}, {}) == Patch(
        [Delete(["foo"], "bar")]
    ), "Error in deleting a key from a dictionary."
    assert diff_dicts(
        {"foo": {"foo": "bar", "bar": "foo"}}, {"foo": {"foo": "bar"}}
    ) == Patch(
        [Delete(["foo", "bar"], "foo")]
    ), "Error deleting a value in a nested dict"
    assert diff_dicts({"foo": [1, 2, 3, 4]}, {"foo": [1, 2, 3]}) == Patch(
        [Delete(["foo"], 4, "ul")]
    ), "error deleting a value in an array"
    assert diff_dicts({"foo": {"foo": "bar"}, "bar": "foo"}, {"bar": "foo"}) == Patch(
        [Delete(["foo"], {"foo": "bar"})]
    ), "Error in deleting a dict."
    assert diff_dicts({"foo": [1, 2, 3, 4]}, {"foo": [1, 3]}) == Patch(
        [Delete(["foo"], 2, "ul"), Delete(["foo"], 4, "ul")]
    ), "error in deleting a non-final element in a list."


def test_inverts():

    def invert_test(doc1: dict, doc2: dict):
        diff = diff_dicts(doc1, doc2)
        return diff.invert().apply(doc2) == doc1

    assert diff_dicts({"foo": "bar"}, {"foo": "foo"}).invert().apply(
        {"foo": "foo"}
    ) == {"foo": "bar"}, "Simple invert test."
