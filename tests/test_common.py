# pylint: disable=missing-docstring

import enum
import unittest
from typing import Literal, get_args

from aas_smt_from_ifc.common import is_literal_in


class Kind(enum.Enum):
    Something = enum.auto()
    Another = enum.auto()
    YetAnother = enum.auto()


SomeLiteral = Literal[Kind.Something, Kind.Another]

SOME_LITERAL_SET = frozenset(get_args(SomeLiteral))


class TestIsLiteralIn(unittest.TestCase):
    @staticmethod
    def generate_some_kind_literal() -> Kind:
        return Kind.Something

    def test_basic(self) -> None:
        literal = TestIsLiteralIn.generate_some_kind_literal()

        assert is_literal_in(literal, SOME_LITERAL_SET)
