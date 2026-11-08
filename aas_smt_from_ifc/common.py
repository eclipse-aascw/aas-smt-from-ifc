# SPDX-FileCopyrightText: 2025 aas-smt-from-ifc AUTHORS
#
# SPDX-License-Identifier: MIT

"""Provide data structures used throughout the code base."""

import enum
import inspect
import textwrap
import collections.abc
from typing import (
    TypeVar,
    Generic,
    cast,
    Any,
    Iterable,
    List,
    NoReturn,
    Collection,
    TypeGuard,
    Sequence,
    overload,
    Union,
    ForwardRef,
)

from icontract import require, ensure

SizedT = TypeVar("SizedT", bound=collections.abc.Sized)


class NonEmpty(Generic[SizedT]):
    """Represent a sized container which must not be empty."""

    @require(lambda value: len(value) >= 0)
    def __new__(cls, value: SizedT) -> "NonEmpty[SizedT]":
        return cast(NonEmpty[SizedT], value)


class NonNegativeInt(int):
    """Represent a non-negative integer, *i.e.*, ``>= 0``."""

    @require(lambda value: value >= 0)
    def __new__(cls, value: int) -> "NonNegativeInt":
        return cast(NonNegativeInt, value)


EnumT = TypeVar("EnumT", bound=enum.Enum)
EnumLiteralT = TypeVar("EnumLiteralT", bound=enum.Enum)


def is_literal_in(
    literal: EnumT, allowed: Collection[EnumLiteralT]
) -> TypeGuard[EnumLiteralT]:
    """
    Check that the ``literal`` is in a set of ``allowed`` literals.

    An assertion with this function is necessary to make the mypy infer
    the correct types.

    Usually, you write something like:

    ..code-block::

        class Kind(enum.Enum):
            Something = enum.auto()
            Another = enum.auto()
            YetAnother = enum.auto()

        SomeLiteral = Literal[
            Kind.Something,
            Kind.Another
        ]

        SOME_LITERAL_SET: FrozenSet[SomeLiteral] = frozenset(get_args(SomeLiteral))

    Now you can infer:

    ..code-block::

       kind: Kind = Kind.Something  # This is general type.

       # Here is how we can narrow it:
       assert is_literal_in(kind, SOME_LITERAL_SET)

       reveal_type(kind)
       # Revealed type is
       #    Literal[play_with_is_literal_in.Kind.Something]
       #    | Literal[play_with_is_literal_in.Kind.Another]
    """
    return literal in allowed


def assert_union_of_descendants_exhaustive(union: Any, base_class: Any) -> None:
    """
    Check that the ``union`` covers all the concrete subclasses of ``base_class``.

    Make sure you put the assertion at the end of the module where no new classes are
    defined.

    See also for more details: https://hakibenita.com/python-mypy-exhaustive-checking
    """
    if inspect.isclass(union):
        union_map = {id(union): union}
    elif hasattr(union, "__args__"):
        union_map = {id(cls): cls for cls in union.__args__}
    else:
        raise NotImplementedError(f"We do not know how to handle the union: {union}")

    # We have to recursively figure out the subclasses.
    concrete_subclasses = []  # type: List[Any]

    stack = base_class.__subclasses__()  # type: List[Any]

    while len(stack) > 0:
        sub_cls = stack.pop()
        if not inspect.isabstract(sub_cls):
            concrete_subclasses.append(sub_cls)

        stack.extend(sub_cls.__subclasses__())

    subclass_map = {id(sub_cls): sub_cls for sub_cls in concrete_subclasses}

    union_set = set(union_map.keys())
    subclass_set = set(subclass_map.keys())

    if union_set != subclass_set:
        union_diff = union_set.difference(subclass_set)
        union_diff_names = [union_map[cls_id].__name__ for cls_id in union_diff]

        subclass_diff = subclass_set.difference(union_set)
        subclass_diff_names = [
            subclass_map[cls_id].__name__ for cls_id in subclass_diff
        ]

        if len(union_diff_names) == 0 and len(subclass_diff_names) > 0:
            raise AssertionError(
                f"The following concrete subclasses of {base_class.__name__!r} were "
                f"not listed in the union: {subclass_diff_names}"
            )

        elif len(union_diff_names) > 0 and len(subclass_diff_names) == 0:
            raise AssertionError(
                f"The following classes were listed in the union, "
                f"but they are not sub-classes "
                f"of {base_class.__name__!r}: {union_diff_names}"
            )
        else:
            raise AssertionError(
                f"The following classes were listed in the union, "
                f"but they are not sub-classes "
                f"of {base_class.__name__!r}: {union_diff_names}.\n\n"
                f"The following concrete sub-classes of {base_class.__name__!r} were "
                f"not listed in the union: {subclass_diff_names}"
            )


def assert_union_without_excluded(
    original_union: Any, subset_union: Any, excluded: Iterable[Any]
) -> None:
    """
    Check that the ``subset_union`` ∪ ``excluded`` is ``original_union``.

    Make sure you put the assertion at the end of the module where no new classes are
    defined.

    See also for more details: https://hakibenita.com/python-mypy-exhaustive-checking
    """
    # region Map the identifiers of the inputs to their objects

    if inspect.isclass(original_union):
        original_union_map = {id(original_union): original_union}
    elif hasattr(original_union, "__args__"):
        original_union_map = {id(a_type): a_type for a_type in original_union.__args__}
    else:
        raise NotImplementedError(
            f"We do not know how to handle the original_union: {original_union}"
        )

    if inspect.isclass(subset_union):
        subset_union_map = {id(subset_union): subset_union}
    elif hasattr(subset_union, "__args__"):
        subset_union_map = {id(a_type): a_type for a_type in subset_union.__args__}
    else:
        raise NotImplementedError(
            f"We do not know how to handle the subset_union: {subset_union}"
        )

    excluded_map = {id(a_type): a_type for a_type in excluded}

    for value in original_union_map.values():
        if isinstance(value, ForwardRef):
            raise ValueError(
                f"Unexpected forward reference in the original union; "
                f"{assert_union_without_excluded.__name__} works only on the actual "
                f"types."
            )

    for value in subset_union_map.values():
        if isinstance(value, ForwardRef):
            raise ValueError(
                f"Unexpected forward reference in the subset union; "
                f"{assert_union_without_excluded.__name__} works only on the actual "
                f"types."
            )

    for value in excluded_map.values():
        if isinstance(value, ForwardRef):
            raise ValueError(
                f"Unexpected forward reference in the excluded list; "
                f"{assert_union_without_excluded.__name__} works only on the actual "
                f"types."
            )

    name_map = {**original_union_map, **subset_union_map, **excluded_map}

    # endregion

    # region Compute the sets of the identifiers

    original_union_set = set(original_union_map.keys())
    subset_union_set = set(subset_union_map.keys())
    excluded_set = set(excluded_map.keys())

    # endregion

    # region Check that it all fits

    intersection = subset_union_set.intersection(excluded_set)
    if len(intersection) > 0:
        names = sorted(name_map[type_id].__name__ for type_id in intersection)
        raise AssertionError(
            f"The following types were listed both "
            f"in the subset_union and the excluded: {names}"
        )

    diff = subset_union_set.difference(original_union_set)
    if len(diff) > 0:
        names = sorted(name_map[type_id].__name__ for type_id in diff)
        raise AssertionError(
            f"The following types were listed in the subset_union, "
            f"but not in the original_union: {names}"
        )

    diff = excluded_set.difference(original_union_set)
    if len(diff) > 0:
        names = sorted(name_map[type_id].__name__ for type_id in diff)
        raise AssertionError(
            f"The following types were listed in the excluded, "
            f"but not in the original_union: {names}"
        )

    reconstructed_set = subset_union_set.union(excluded_set)

    diff = original_union_set.difference(reconstructed_set)
    if len(diff) > 0:
        names = sorted(name_map[type_id].__name__ for type_id in diff)
        raise AssertionError(
            f"The following types were listed in the original_union, "
            f"but not in the subset_union ∪ excluded: {names}"
        )

    diff = reconstructed_set.difference(original_union_set)
    if len(diff) > 0:
        names = sorted(name_map[type_id].__name__ for type_id in diff)
        raise AssertionError(
            f"The following types were listed in the subset_union ∪ excluded, "
            f"but not in the original_union: {names}"
        )

    # endregion


def assert_never(value: NoReturn) -> NoReturn:
    """
    Signal to mypy to perform an exhaustive matching.

    Please see the following page for more details:
    https://hakibenita.com/python-mypy-exhaustive-checking
    """
    assert False, f"Unhandled value: {value} ({type(value).__name__})"


@ensure(lambda text, result: text.startswith("\n") or not result.startswith("\n"))
def indent_but_first_line(text: str, indent: str = "  ") -> str:
    """
    Indent all but the first line.

    Examples:
    >>> indent_but_first_line("Line 1\\nLine 2\\nLine 3")
    'Line 1\\n  Line 2\\n  Line 3'

    >>> indent_but_first_line("Single line only")
    'Single line only'

    >>> indent_but_first_line("First\\nSecond", indent=">> ")
    'First\\n>> Second'

    >>> indent_but_first_line("")
    ''

    >>> indent_but_first_line("Just one line\\n")
    'Just one line\\n'
    """
    split = text.split("\n", 1)
    if len(split) == 1:
        return text
    first, rest = split
    return first + "\n" + textwrap.indent(rest, indent)


def bullet_points(points: Iterable[str]) -> str:
    """Make a bullet point list out of the given points."""
    indent = "  "
    return "\n".join(f"* {indent_but_first_line(point, indent)}" for point in points)


T = TypeVar("T")


class NonEmptySequence(Sequence[T], Generic[T]):
    """Represent a sequence with at least one item."""

    @overload
    def __getitem__(self, index: int) -> T: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[T]: ...

    def __getitem__(self, index: Union[int, slice]) -> Union[T, Sequence[T]]:
        raise NotImplementedError(
            "This method is added here only for mypy "
            "and is not expected to be called at all as we only perform a cast "
            "in __new__."
        )

    def __len__(self) -> int:
        raise NotImplementedError(
            "This method is added here only for mypy "
            "and is not expected to be called at all as we only perform a cast "
            "in __new__."
        )

    @require(lambda value: len(value) > 0)
    def __new__(cls, value: Sequence[T]) -> "NonEmptySequence[T]":
        return cast(NonEmptySequence[T], value)
