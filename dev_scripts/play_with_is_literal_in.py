# SPDX-FileCopyrightText: 2025 aas-smt-from-ifc AUTHORS
#
# SPDX-License-Identifier: MIT

# NOTE (mristin):
# This program is meant to be checked with mypy, not run.

import enum
from typing import Collection, TypeGuard, FrozenSet, TypeVar, Union, overload, Literal, \
    get_args, Type, Hashable, Tuple, Set, cast, Any

from typing_extensions import reveal_type, assert_never

EnumT = TypeVar("EnumT", bound=enum.Enum)
EnumLiteralT = TypeVar("EnumLiteralT", bound=enum.Enum)


def is_literal_in(
        literal: EnumT,
        allowed: Collection[EnumLiteralT]
) -> TypeGuard[EnumLiteralT]:
    """Check that the literal is in a set of """
    return literal in allowed


class Kind(enum.Enum):
    Something = enum.auto()
    Another = enum.auto()
    YetAnother = enum.auto()
    YetYetAnother = enum.auto()

class X:
    SomeLiteral = Literal[
        Kind.Something,
        Kind.Another
    ]

    AnotherLiteral = Literal[
        Kind.Another,
        Kind.YetAnother
    ]

    UnionLiteral = Literal[SomeLiteral, AnotherLiteral]

    SOME_LITERAL_SET: FrozenSet[SomeLiteral] = frozenset(get_args(SomeLiteral))
    ANOTHER_LITERAL_SET: FrozenSet[AnotherLiteral] = frozenset(get_args(AnotherLiteral))
    UNION_LITERAL_SET: FrozenSet[UnionLiteral] = frozenset(get_args(UnionLiteral))

    reveal_type(SOME_LITERAL_SET)

    @staticmethod
    def generate_kind() -> Kind:
        return Kind.YetAnother

    a: Kind = generate_kind()
    reveal_type(a)

    assert is_literal_in(a, UNION_LITERAL_SET)
    reveal_type(a)

    if is_literal_in(a, SOME_LITERAL_SET):
        reveal_type(a)

    elif is_literal_in(a, ANOTHER_LITERAL_SET):
        reveal_type(a)
    else:
        # NOTE (mristin):
        # This unfortunately does not work with the latest mypy 1.18.2 since mypy
        # can not subtract literal types.
        assert_never(a)
