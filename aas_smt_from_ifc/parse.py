"""Tokenize and parse than Express schema."""

# pylint: disable=missing-docstring

import collections.abc
import copy
import decimal
import enum
import functools
import re
import typing
from typing import (
    List,
    Final,
    Sequence,
    Union,
    Optional,
    TypeVar,
    cast,
    Tuple,
    get_args,
    Callable,
    FrozenSet,
    ParamSpec,
    Concatenate,
    Dict,
    Any,
)

from icontract import DBC, require, ensure, snapshot

from aas_smt_from_ifc.common import (
    NonNegativeInt,
    assert_never,
    is_literal_in,
)


class _TokenKind(enum.Enum):
    # Comments
    COMMENT = "COMMENT"

    # Keywords (case-insensitive)
    SELF = "SELF"
    WHERE = "WHERE"
    ENTITY = "ENTITY"
    END_ENTITY = "END_ENTITY"
    TYPE = "TYPE"
    END_TYPE = "END_TYPE"
    FUNCTION = "FUNCTION"
    END_FUNCTION = "END_FUNCTION"
    PROCEDURE = "PROCEDURE"
    END_PROCEDURE = "END_PROCEDURE"
    RULE = "RULE"
    END_RULE = "END_RULE"
    SUBTYPE = "SUBTYPE"
    SUPERTYPE = "SUPERTYPE"
    OF = "OF"
    DERIVE = "DERIVE"
    INVERSE = "INVERSE"
    OPTIONAL = "OPTIONAL"
    UNIQUE = "UNIQUE"
    ABSTRACT = "ABSTRACT"
    SET = "SET"
    LIST = "LIST"
    ARRAY = "ARRAY"
    BAG = "BAG"
    BOOLEAN = "BOOLEAN"
    INTEGER = "INTEGER"
    REAL = "REAL"
    STRING = "STRING"
    NUMBER = "NUMBER"
    LOGICAL = "LOGICAL"
    BINARY = "BINARY"
    GENERIC = "GENERIC"
    FIXED = "FIXED"
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"
    ANDOR = "ANDOR"
    AND = "AND"
    OR = "OR"
    XOR = "XOR"
    NOT = "NOT"
    IF = "IF"
    THEN = "THEN"
    ELSE = "ELSE"
    END_IF = "END_IF"
    CASE = "CASE"
    END_CASE = "END_CASE"
    FORALL = "FORALL"
    RETURN = "RETURN"
    SCHEMA = "SCHEMA"
    END_SCHEMA = "END_SCHEMA"
    USE = "USE"
    REFERENCE = "REFERENCE"
    FROM = "FROM"
    ALIAS = "ALIAS"
    END_ALIAS = "END_ALIAS"
    AS = "AS"
    IN = "IN"
    LIKE = "LIKE"
    AGGREGATE = "AGGREGATE"
    BY = "BY"
    DIV = "DIV"
    MOD = "MOD"
    CONSTANT = "CONSTANT"
    END_CONSTANT = "END_CONSTANT"
    ENUMERATION = "ENUMERATION"
    FOR = "FOR"
    LOCAL = "LOCAL"
    END_LOCAL = "END_LOCAL"
    ONEOF = "ONEOF"
    OTHERWISE = "OTHERWISE"
    QUERY = "QUERY"
    SELECT = "SELECT"
    TO = "TO"
    REPEAT = "REPEAT"
    END_REPEAT = "END_REPEAT"
    WHILE = "WHILE"
    UNTIL = "UNTIL"
    BEGIN = "BEGIN"
    END = "END"
    ESCAPE = "ESCAPE"
    SKIP = "SKIP"
    VAR = "VAR"

    # Comparison
    NE = "NE"
    LE = "LE"
    GE = "GE"
    LT = "LT"
    GT = "GT"
    COLON_LT_GT_COLON = "COLON_LT_GT_COLON"
    COLON_EQ_COLON = "COLON_EQ_COLON"

    # Misc. operators
    LT_STAR = "LT_STAR"
    DOUBLE_PIPE = "DOUBLE_PIPE"
    COLON_EQ = "COLON_EQ"
    DOUBLE_HYPHEN = "DOUBLE_HYPHEN"

    # Arithmetic
    DOUBLE_STAR = "DOUBLE_STAR"
    PLUS = "PLUS"
    MINUS = "MINUS"
    STAR = "STAR"
    SLASH = "SLASH"

    # Punctuation (include backslash)
    BACKSLASH = "BACKSLASH"
    DOT = "DOT"
    LPAR = "LPAR"
    RPAR = "RPAR"
    LSQ = "LSQ"
    RSQ = "RSQ"
    LCRLY = "LCRLY"
    RCRLY = "RCRLY"
    PIPE = "PIPE"
    COMMA = "COMMA"
    SEMI = "SEMI"
    COLON = "COLON"
    EQ = "EQ"

    IDENTIFIER = "IDENTIFIER"

    BINARY_LITERAL = "BINARY_LITERAL"
    INTEGER_LITERAL = "INTEGER_LITERAL"
    REAL_LITERAL = "REAL_LITERAL"
    STRING_LITERAL = "STRING"

    QMARK = "QMARK"


class Position:
    """Represent a position in a source code."""

    lineno: Final[NonNegativeInt]
    column: Final[NonNegativeInt]

    def __init__(self, lineno: NonNegativeInt, column: NonNegativeInt) -> None:
        self.lineno = lineno
        self.column = column

    def __str__(self) -> str:
        return f"{int(self.lineno) + 1}:{int(self.column) + 1}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Position):
            return NotImplemented

        return self.lineno == other.lineno and self.column == other.column


class _Token:
    """Model a token in the tokenization stream."""

    kind: Final[_TokenKind]
    text: Final[str]
    start: Final[NonNegativeInt]
    position: Final[Position]

    def __init__(
        self,
        kind: _TokenKind,
        text: str,
        #: Index in the original text
        start: NonNegativeInt,
        #: Line number and column in the original text
        position: Position,
    ) -> None:
        self.kind = kind
        self.text = text
        self.start = start
        self.position = position

    def __str__(self) -> str:
        return f"<_Token {self.kind.name} at {self.position} {self.text!r}>"


class _TokenizationRule:
    pattern: Final[re.Pattern[str]]
    kind: Final[_TokenKind]

    def __init__(self, pattern: re.Pattern[str], kind: _TokenKind) -> None:
        self.pattern = pattern
        self.kind = kind


# noinspection RegExpSimplifiable
IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z_0-9]*$")


class Identifier(str):
    """Represent an identifier."""

    @require(lambda value: IDENTIFIER_RE.fullmatch(value))
    def __new__(cls, value: str) -> "Identifier":
        return cast(Identifier, value)


def _create_tokenization_rules() -> List[_TokenizationRule]:
    @require(lambda word: IDENTIFIER_RE.fullmatch(word))
    def kw(word: str, kind: _TokenKind) -> _TokenizationRule:
        # case-insensitive keyword bounded by word boundaries
        return _TokenizationRule(re.compile(rf"(?i)\b{word}\b"), kind)

    def rx(pat: str, kind: _TokenKind) -> _TokenizationRule:
        return _TokenizationRule(re.compile(pat), kind)

    # noinspection PyListCreation
    rules: List[_TokenizationRule] = []

    # --- Comment ---
    rules.append(
        _TokenizationRule(
            # NOTE (mristin):
            # We make the regular expression non-greedy with `?` after the `.*` so that
            # we do not consume the content between two content blocks.
            pattern=re.compile(r"\(\*.*?\*\)", re.DOTALL),
            kind=_TokenKind.COMMENT,
        )
    )

    # --- Literals ---
    rules.append(rx(r"[0-9]+\.[0-9]*([Ee][+-]?[0-9]+)?", _TokenKind.REAL_LITERAL))
    rules.append(rx(r"\.[0-9]+([Ee][+-]?[0-9]+)?", _TokenKind.REAL_LITERAL))
    rules.append(rx(r"[0-9]+\.", _TokenKind.REAL_LITERAL))
    rules.append(rx(r"[0-9]+", _TokenKind.INTEGER_LITERAL))

    rules.append(rx(r"'((''|\\.|[^'])*?)'", _TokenKind.STRING_LITERAL))

    rules.append(rx(r"%[01][01]*", _TokenKind.BINARY_LITERAL))

    # --- Keywords (case-insensitive) ---
    rules.extend(
        [
            kw("SELF", _TokenKind.SELF),
            kw("WHERE", _TokenKind.WHERE),
            kw("ENTITY", _TokenKind.ENTITY),
            kw("END_ENTITY", _TokenKind.END_ENTITY),
            kw("TYPE", _TokenKind.TYPE),
            kw("END_TYPE", _TokenKind.END_TYPE),
            kw("FUNCTION", _TokenKind.FUNCTION),
            kw("END_FUNCTION", _TokenKind.END_FUNCTION),
            kw("PROCEDURE", _TokenKind.PROCEDURE),
            kw("END_PROCEDURE", _TokenKind.END_PROCEDURE),
            kw("RULE", _TokenKind.RULE),
            kw("END_RULE", _TokenKind.END_RULE),
            kw("SUBTYPE", _TokenKind.SUBTYPE),
            kw("SUPERTYPE", _TokenKind.SUPERTYPE),
            kw("OF", _TokenKind.OF),
            kw("DERIVE", _TokenKind.DERIVE),
            kw("INVERSE", _TokenKind.INVERSE),
            kw("OPTIONAL", _TokenKind.OPTIONAL),
            kw("UNIQUE", _TokenKind.UNIQUE),
            kw("ABSTRACT", _TokenKind.ABSTRACT),
            kw("SET", _TokenKind.SET),
            kw("LIST", _TokenKind.LIST),
            kw("ARRAY", _TokenKind.ARRAY),
            kw("BAG", _TokenKind.BAG),
            kw("BOOLEAN", _TokenKind.BOOLEAN),
            kw("INTEGER", _TokenKind.INTEGER),
            kw("REAL", _TokenKind.REAL),
            kw("STRING", _TokenKind.STRING),
            kw("NUMBER", _TokenKind.NUMBER),
            kw("LOGICAL", _TokenKind.LOGICAL),
            kw("BINARY", _TokenKind.BINARY),
            kw("GENERIC", _TokenKind.GENERIC),
            kw("FIXED", _TokenKind.FIXED),
            kw("TRUE", _TokenKind.TRUE),
            kw("FALSE", _TokenKind.FALSE),
            kw("UNKNOWN", _TokenKind.UNKNOWN),
            kw("ANDOR", _TokenKind.ANDOR),
            kw("AND", _TokenKind.AND),
            kw("OR", _TokenKind.OR),
            kw("XOR", _TokenKind.XOR),
            kw("NOT", _TokenKind.NOT),
            kw("IF", _TokenKind.IF),
            kw("THEN", _TokenKind.THEN),
            kw("ELSE", _TokenKind.ELSE),
            kw("END_IF", _TokenKind.END_IF),
            kw("CASE", _TokenKind.CASE),
            kw("END_CASE", _TokenKind.END_CASE),
            kw("FORALL", _TokenKind.FORALL),
            kw("RETURN", _TokenKind.RETURN),
            kw("SCHEMA", _TokenKind.SCHEMA),
            kw("END_SCHEMA", _TokenKind.END_SCHEMA),
            kw("USE", _TokenKind.USE),
            kw("REFERENCE", _TokenKind.REFERENCE),
            kw("FROM", _TokenKind.FROM),
            kw("ALIAS", _TokenKind.ALIAS),
            kw("END_ALIAS", _TokenKind.END_ALIAS),
            kw("AS", _TokenKind.AS),
            kw("IN", _TokenKind.IN),
            kw("LIKE", _TokenKind.LIKE),
            kw("AGGREGATE", _TokenKind.AGGREGATE),
            kw("BY", _TokenKind.BY),
            kw("DIV", _TokenKind.DIV),
            kw("MOD", _TokenKind.MOD),
            kw("CONSTANT", _TokenKind.CONSTANT),
            kw("END_CONSTANT", _TokenKind.END_CONSTANT),
            kw("ENUMERATION", _TokenKind.ENUMERATION),
            kw("FOR", _TokenKind.FOR),
            kw("LOCAL", _TokenKind.LOCAL),
            kw("END_LOCAL", _TokenKind.END_LOCAL),
            kw("ONEOF", _TokenKind.ONEOF),
            kw("OTHERWISE", _TokenKind.OTHERWISE),
            kw("QUERY", _TokenKind.QUERY),
            kw("SELECT", _TokenKind.SELECT),
            kw("TO", _TokenKind.TO),
            kw("REPEAT", _TokenKind.REPEAT),
            kw("END_REPEAT", _TokenKind.END_REPEAT),
            kw("WHILE", _TokenKind.WHILE),
            kw("UNTIL", _TokenKind.UNTIL),
            kw("BEGIN", _TokenKind.BEGIN),
            kw("END", _TokenKind.END),
            kw("ESCAPE", _TokenKind.ESCAPE),
            kw("SKIP", _TokenKind.SKIP),
            kw("VAR", _TokenKind.VAR),
        ]
    )

    # --- Misc. operators ---
    # NOTE (mristin):
    # This must come before LT token!
    rules.append(rx(r"<\*", _TokenKind.LT_STAR))
    rules.append(rx(r"\|\|", _TokenKind.DOUBLE_PIPE))
    rules.append(rx(r"--", _TokenKind.DOUBLE_HYPHEN))

    # --- Comparison (order matters: two-character before one-character) ---
    rules.extend(
        [
            rx(r":<>:", _TokenKind.COLON_LT_GT_COLON),
            rx(r":=:", _TokenKind.COLON_EQ_COLON),
            rx(r"<>", _TokenKind.NE),
            rx(r"<=", _TokenKind.LE),
            rx(r">=", _TokenKind.GE),
            rx(r"<", _TokenKind.LT),
            rx(r">", _TokenKind.GT),
        ]
    )

    # --- Misc. operators ---
    rules.append(rx(r":=", _TokenKind.COLON_EQ))

    # --- Arithmetic ---
    rules.extend(
        [
            rx(r"\*\*", _TokenKind.DOUBLE_STAR),
            rx(r"\+", _TokenKind.PLUS),
            rx(r"-", _TokenKind.MINUS),
            rx(r"\*", _TokenKind.STAR),
            rx(r"/", _TokenKind.SLASH),
        ]
    )

    # --- Punctuation (include backslash) ---
    rules.extend(
        [
            rx(r"\\", _TokenKind.BACKSLASH),
            rx(r"\.", _TokenKind.DOT),
            rx(r"\(", _TokenKind.LPAR),
            rx(r"\)", _TokenKind.RPAR),
            rx(r"\[", _TokenKind.LSQ),
            rx(r"\]", _TokenKind.RSQ),
            rx(r"{", _TokenKind.LCRLY),
            rx(r"}", _TokenKind.RCRLY),
            rx(r"\|", _TokenKind.PIPE),
            rx(r",", _TokenKind.COMMA),
            rx(r";", _TokenKind.SEMI),
            rx(r":", _TokenKind.COLON),
            rx(r"=", _TokenKind.EQ),
        ]
    )

    rules.append(rx(r"[A-Za-z_][A-Za-z0-9_]*", _TokenKind.IDENTIFIER))

    rules.append(rx(r"\?", _TokenKind.QMARK))

    return rules


_TOKENIZATION_RULES = _create_tokenization_rules()

_WHITESPACE_RE = re.compile(r"\s+")


def _lex(text: str) -> Tuple[List[_Token], bool]:
    """
    Lex the given text.

    Return the successfully lexed tokens and success/fail.
    """
    tokens = []  # type: List[_Token]

    # NOTE (mristin):
    # Theoretically, we could use range trees, but since we are not going to parse
    # huge texts, this is a quick work-around.
    linenos = []
    columns = []
    current_lineno = 0
    current_column = 0
    for character in text:
        linenos.append(current_lineno)
        columns.append(current_column)

        if character == "\n":
            current_lineno += 1
            current_column = 0
        else:
            current_column += 1

    start = 0
    while start < len(text):
        old_start = start

        match: Optional[re.Match[str]] = None
        for rule in _TOKENIZATION_RULES:
            match = rule.pattern.match(text, pos=start)

            if match is not None:
                assert len(match.group(0)) > 0, (
                    f"Empty strings should never be matched against tokenization rule, "
                    f"but rule pattern matched: {rule.pattern}"
                )

                token = _Token(
                    kind=rule.kind,
                    text=match.group(0),
                    start=NonNegativeInt(start),
                    position=Position(
                        lineno=NonNegativeInt(linenos[start]),
                        column=NonNegativeInt(columns[start]),
                    ),
                )

                tokens.append(token)
                start = match.end()
                break

        if match is None:
            # NOTE (mristin):
            # We ignore the whitespace as it is irrelevant for us.
            match = _WHITESPACE_RE.match(text, pos=start)
            if match is not None:
                start = match.end()

        if match is None:
            return tokens, False

        assert start > old_start, (
            f"Loop invariant: {start=}, {old_start=}, "
            f"{len(text)=}, {text[start:start+10]=}, "
            f"{match=}"
        )

    return tokens, True


class Error:
    """Define a parsing error with precise 0-based source location."""

    message: Final[str]
    line: Final[int]
    column: Final[int]

    def __init__(
        self,
        message: str,
        line: int,
        column: int,
    ) -> None:
        self.message = message
        self.line = line
        self.column = column

    def __str__(self) -> str:
        return f"{self.line + 1}:{self.column + 1}: {self.message}"


# region AST

T_co = TypeVar("T_co", covariant=True)


class Node(DBC):
    """Provide a base class for all AST nodes."""

    position: Final[Position]

    def __init__(self, position: Position) -> None:
        self.position = position


# NOTE (mristin):
# The AST types are heavily influenced by:
# https://github.com/hypar-io/IFC-gen/blob/IFC4/grammar/Express.g4
# https://github.com/dustintownsend/EXPRESS-Modeling-Language-References/blob/master/iso-10303-11.bnf


class LogicalValue(enum.Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


class BinaryLiteral(Node):
    value: Final[bytes]

    def __init__(self, position: Position, value: bytes) -> None:
        super().__init__(position)
        self.value = value


class IntegerLiteral(Node):
    value: Final[int]

    def __init__(self, position: Position, value: int) -> None:
        super().__init__(position)
        self.value = value


class LogicalLiteral(Node):
    value: Final[LogicalValue]

    def __init__(self, position: Position, value: LogicalValue) -> None:
        super().__init__(position)
        self.value = value


class RealLiteral(Node):
    value: Final[decimal.Decimal]

    def __init__(self, position: Position, value: decimal.Decimal) -> None:
        super().__init__(position)
        self.value = value


class StringLiteral(Node):
    value: Final[str]

    def __init__(self, position: Position, value: str) -> None:
        super().__init__(position)
        self.value = value


class Element(Node):
    expr: Final["Expr"]
    repetition: Final[Optional["Expr"]]

    def __init__(
        self, position: Position, expr: "Expr", repetition: Optional["Expr"]
    ) -> None:
        super().__init__(position)
        self.expr = expr
        self.repetition = repetition


class AggregateLiteral(Node):
    elements: Final[Sequence[Element]]

    def __init__(self, position: Position, elements: Sequence[Element]) -> None:
        super().__init__(position)
        self.elements = elements


class IndeterminateLiteral(Node):
    """Represent a ``?`` literal."""


class UnaryOp(enum.Enum):
    PLUS = "PLUS"
    NEG = "NEG"
    NOT = "NOT"


class UnaryExpr(Node):
    op: UnaryOp
    operand: Final["Expr"]

    def __init__(self, position: Position, op: UnaryOp, operand: "Expr") -> None:
        super().__init__(position)
        self.op = op
        self.operand = operand


class BinaryOp(enum.Enum):
    # Arithmetic
    ADD = "ADD"
    SUBTRACT = "SUBTRACT"
    MULTIPLY = "MULTIPLY"
    REAL_DIVIDE = "REAL_DIVIDE"
    INTEGER_DIVIDE = "INTEGER_DIVIDE"
    MODULO = "MODULO"
    POWER = "POWER"

    # Logical
    OR = "OR"
    XOR = "XOR"
    AND = "AND"

    # Collections
    CONCAT = "CONCAT"

    # Relational (value comparison)
    LESS_THAN = "LESS_THAN"  # <
    GREATER_THAN = "GREATER_THAN"  # >
    LESS_EQUAL = "LESS_EQUAL"  # <=
    GREATER_EQUAL = "GREATER_EQUAL"  # >=
    EQUAL = "EQUAL"  # =
    NOT_EQUAL = "NOT_EQUAL"  # <>

    # Instance comparison (entity identity)
    INSTANCE_EQUAL = "INSTANCE_EQUAL"  # :=:
    INSTANCE_NOT_EQUAL = "INSTANCE_NOT_EQUAL"  # :<>:

    # Membership / pattern match
    IN = "IN"  # IN
    LIKE = "LIKE"  # LIKE


class BinaryExpr(Node):
    left: Final["Expr"]
    op: BinaryOp
    right: Final["Expr"]

    def __init__(
        self, position: Position, left: "Expr", op: BinaryOp, right: "Expr"
    ) -> None:
        super().__init__(position)
        self.left = left
        self.op = op
        self.right = right


# NOTE (mristin):
# We diverge our terms here from the grammar as we want to make the AST easier to use
# for the downstream users.


class Self(Node):
    """Represent the reference to ``SELF``."""


class NameRef(Node):
    identifier: Final[Identifier]

    def __init__(self, position: Position, identifier: Identifier) -> None:
        super().__init__(position)
        self.identifier = identifier


class AttributeRef(Node):
    source: Final["Expr"]
    identifier: Final[Identifier]

    def __init__(
        self, position: Position, source: "Expr", identifier: Identifier
    ) -> None:
        super().__init__(position)
        self.source = source
        self.identifier = identifier


class QualifiedAttributeRef(Node):
    source: Final["Expr"]
    group_qualifier: Final[Identifier]
    attribute: Final[Identifier]

    def __init__(
        self,
        position: Position,
        source: "Expr",
        group_qualifier: Identifier,
        attribute: Identifier,
    ) -> None:
        super().__init__(position)
        self.source = source
        self.group_qualifier = group_qualifier
        self.attribute = attribute


class IndexExpr(Node):
    source: Final["Expr"]
    index: Final["Expr"]

    def __init__(self, position: Position, source: "Expr", index: "Expr") -> None:
        super().__init__(position)
        self.source = source
        self.index = index


class Arg(Node):
    name: Final[Optional[Identifier]]
    value: Final["Expr"]

    def __init__(
        self, position: Position, name: Optional[Identifier], value: "Expr"
    ) -> None:
        super().__init__(position)
        self.name = name
        self.value = value


class Call(Node):
    callee: Final["Expr"]
    args: Final[Sequence[Arg]]

    def __init__(self, position: Position, callee: "Expr", args: Sequence[Arg]) -> None:
        super().__init__(position)
        self.callee = callee
        self.args = args


IntervalOp = typing.Literal[BinaryOp.LESS_THAN, BinaryOp.LESS_EQUAL]


class Interval(Node):
    left: Final["Expr"]
    left_to_center: Final[IntervalOp]
    center: Final["Expr"]
    center_to_right: Final[IntervalOp]
    right: Final["Expr"]

    def __init__(
        self,
        position: Position,
        left: "Expr",
        left_to_center: IntervalOp,
        center: "Expr",
        center_to_right: IntervalOp,
        right: "Expr",
    ) -> None:
        super().__init__(position)
        self.left = left
        self.left_to_center = left_to_center
        self.center = center
        self.center_to_right = center_to_right
        self.right = right


class QueryExpr(Node):
    variable: Final[Identifier]
    aggregate: Final["Expr"]
    predicate: Final["Expr"]

    def __init__(
        self,
        position: Position,
        variable: Identifier,
        aggregate: "Expr",
        predicate: "Expr",
    ) -> None:
        super().__init__(position)
        self.variable = variable
        self.aggregate = aggregate
        self.predicate = predicate


Literal = Union[
    "BinaryLiteral",
    "IntegerLiteral",
    "LogicalLiteral",
    "RealLiteral",
    "StringLiteral",
    "AggregateLiteral",
    "IndeterminateLiteral",
]

Expr = Union[
    "Literal",
    "UnaryExpr",
    "BinaryExpr",
    "Self",
    "NameRef",
    "AttributeRef",
    "QualifiedAttributeRef",
    "IndexExpr",
    "Call",
    "Interval",
    "QueryExpr",
]


class BoundSpec(Node):
    lower: Final[Expr]
    upper: Final[Expr]

    def __init__(self, position: Position, lower: Expr, upper: Expr) -> None:
        super().__init__(position)
        self.lower = lower
        self.upper = upper


class NamedType(Node):
    reference: Final[Identifier]

    def __init__(self, position: Position, reference: Identifier) -> None:
        super().__init__(position)
        self.reference = reference


class BinaryType(Node):
    width: Final[Optional["Expr"]]
    fixed: Final[bool]

    @require(lambda width, fixed: not (width is None) or (not fixed))
    def __init__(
        self, position: Position, width: Optional["Expr"], fixed: bool
    ) -> None:
        super().__init__(position)
        self.width = width
        self.fixed = fixed


class BooleanType(Node):
    pass


class IntegerType(Node):
    pass


class LogicalType(Node):
    pass


class NumberType(Node):
    pass


class RealType(Node):
    precision_spec: Final[Optional[Expr]]

    def __init__(self, position: Position, precision_spec: Optional[Expr]) -> None:
        super().__init__(position)
        self.precision_spec = precision_spec


class StringType(Node):
    width: Final[Optional["Expr"]]
    fixed: Final[bool]

    @require(lambda width, fixed: not (width is None) or (not fixed))
    def __init__(
        self, position: Position, width: Optional["Expr"], fixed: bool
    ) -> None:
        super().__init__(position)
        self.width = width
        self.fixed = fixed


SimpleType = Union[
    BinaryType, BooleanType, IntegerType, LogicalType, NumberType, RealType, StringType
]


class GenericType(Node):
    type_label: Final[Optional[Identifier]]

    def __init__(self, position: Position, type_label: Optional[Identifier]) -> None:
        super().__init__(position)
        self.type_label = type_label


CollectionTypeSelection = Union[
    "CollectionType", "NamedType", "SimpleType", "GenericType"
]


class ArrayType(Node):
    bound_spec: Final[BoundSpec]
    optional: Final[bool]
    unique: Final[bool]
    of: Final["CollectionTypeSelection"]

    def __init__(
        self,
        position: Position,
        bound_spec: BoundSpec,
        optional: bool,
        unique: bool,
        of: "CollectionTypeSelection",
    ) -> None:
        super().__init__(position)
        self.bound_spec = bound_spec
        self.optional = optional
        self.unique = unique
        self.of = of


class BagType(Node):
    bound_spec: Final[Optional[BoundSpec]]
    of: Final["CollectionTypeSelection"]

    def __init__(
        self,
        position: Position,
        bound_spec: Optional[BoundSpec],
        of: "CollectionTypeSelection",
    ) -> None:
        super().__init__(position)
        self.bound_spec = bound_spec
        self.of = of


class ListType(Node):
    bound_spec: Final[Optional[BoundSpec]]
    unique: bool
    of: Final["CollectionTypeSelection"]

    def __init__(
        self,
        position: Position,
        bound_spec: Optional[BoundSpec],
        unique: bool,
        of: "CollectionTypeSelection",
    ) -> None:
        super().__init__(position)
        self.bound_spec = bound_spec
        self.unique = unique
        self.of = of


class SetType(Node):
    bound_spec: Final[Optional[BoundSpec]]
    of: Final["CollectionTypeSelection"]

    def __init__(
        self,
        position: Position,
        bound_spec: Optional[BoundSpec],
        of: "CollectionTypeSelection",
    ) -> None:
        super().__init__(position)
        self.bound_spec = bound_spec
        self.of = of


CollectionType = Union["ArrayType", "BagType", "ListType", "SetType"]


class EnumType(Node):
    values: Final[Sequence[Identifier]]

    def __init__(self, position: Position, values: Sequence[Identifier]) -> None:
        super().__init__(position)
        self.values = values


class SelectType(Node):
    values: Final[Sequence[NamedType]]

    def __init__(self, position: Position, values: Sequence[NamedType]) -> None:
        super().__init__(position)
        self.values = values


TypeSelection = Union[
    "CollectionType", "NamedType", "SimpleType", "EnumType", "SelectType"
]


class SupertypeBinaryOp(enum.Enum):
    AND = "AND"
    ANDOR = "ANDOR"


class SupertypeBinaryExpr(Node):
    left: Final["SupertypeExpr"]
    op: Final[SupertypeBinaryOp]
    right: Final["SupertypeExpr"]

    def __init__(
        self,
        position: Position,
        left: "SupertypeExpr",
        op: SupertypeBinaryOp,
        right: "SupertypeExpr",
    ) -> None:
        super().__init__(position)
        self.left = left
        self.op = op
        self.right = right


class Choice(Node):
    supertype_exprs: Final[Sequence["SupertypeExpr"]]

    def __init__(
        self, position: Position, supertype_exprs: Sequence["SupertypeExpr"]
    ) -> None:
        super().__init__(position)
        self.supertype_exprs = supertype_exprs


SupertypeExpr = Union[NameRef, Choice, SupertypeBinaryExpr]


class AbstractSupertype(Node):
    pass


class SupertypeOf(Node):
    abstract: Final[bool]
    of: Final[SupertypeExpr]

    def __init__(self, position: Position, abstract: bool, of: SupertypeExpr) -> None:
        super().__init__(position)
        self.abstract = abstract
        self.of = of


SupertypeDeclaration = Union[AbstractSupertype, SupertypeOf]


class SubtypeDeclaration(Node):
    of: Final[Sequence[NameRef]]

    def __init__(self, position: Position, of: Sequence[NameRef]) -> None:
        super().__init__(position)
        self.of = of


class ExplicitAttributeDefinition(Node):
    attributes: Final[Sequence[Expr]]
    optional: Final[bool]
    type_selection: Final[CollectionTypeSelection]

    def __init__(
        self,
        position: Position,
        attributes: Sequence[Expr],
        optional: bool,
        type_selection: CollectionTypeSelection,
    ) -> None:
        super().__init__(position)
        self.attributes = attributes
        self.optional = optional
        self.type_selection = type_selection


class DerivedAttribute(Node):
    attribute: Final[Expr]
    type_selection: Final[CollectionTypeSelection]
    init: Final[Expr]

    def __init__(
        self,
        position: Position,
        attribute: Expr,
        type_selection: CollectionTypeSelection,
        init: Expr,
    ) -> None:
        super().__init__(position)
        self.attribute = attribute
        self.type_selection = type_selection
        self.init = init


class DeriveClause(Node):
    derived_attributes: Final[Sequence[DerivedAttribute]]

    def __init__(
        self, position: Position, derived_attributes: Sequence[DerivedAttribute]
    ) -> None:
        super().__init__(position)
        self.derived_attributes = derived_attributes


class InverseBag(Node):
    bound_spec: Final[Optional[BoundSpec]]
    entity: Final[Identifier]

    def __init__(
        self, position: Position, bound_spec: Optional[BoundSpec], entity: Identifier
    ) -> None:
        super().__init__(position)
        self.bound_spec = bound_spec
        self.entity = entity


class InverseSet(Node):
    bound_spec: Final[Optional[BoundSpec]]
    entity: Final[Identifier]

    def __init__(
        self, position: Position, bound_spec: Optional[BoundSpec], entity: Identifier
    ) -> None:
        super().__init__(position)
        self.bound_spec = bound_spec
        self.entity = entity


InverseType = Union[NameRef, InverseBag, InverseSet]


class InverseDefinition(Node):
    attribute: Final[Expr]
    inverse_type: Final[InverseType]
    attribute_ref: Final[Expr]

    def __init__(
        self,
        position: Position,
        attribute: Expr,
        inverse_type: InverseType,
        attribute_ref: Expr,
    ) -> None:
        super().__init__(position)
        self.attribute = attribute
        self.inverse_type = inverse_type
        self.attribute_ref = attribute_ref


class InverseClause(Node):
    inverses: Final[Sequence[InverseDefinition]]

    def __init__(
        self, position: Position, inverses: Sequence[InverseDefinition]
    ) -> None:
        super().__init__(position)
        self.inverses = inverses


class UniqueRule(Node):
    label: Final[Identifier]
    attributes: Final[Sequence[Expr]]

    def __init__(
        self, position: Position, label: Identifier, attributes: Sequence[Expr]
    ) -> None:
        super().__init__(position)
        self.label = label
        self.attributes = attributes


class DomainRule(Node):
    label: Final[Identifier]
    expr: Final[Expr]

    def __init__(self, position: Position, label: Identifier, expr: Expr) -> None:
        super().__init__(position)
        self.label = label
        self.expr = expr


class EntityDeclaration(Node):
    identifier: Final[Identifier]

    supertype_declaration: Final[Optional[SupertypeDeclaration]]
    subtype_declaration: Final[Optional[SubtypeDeclaration]]

    explicit_clauses: Final[Sequence[ExplicitAttributeDefinition]]
    derive_clauses: Final[Sequence[DeriveClause]]
    inverse_clauses: Final[Sequence[InverseClause]]

    unique_rules: Final[Sequence[UniqueRule]]
    domain_rules: Final[Sequence[DomainRule]]

    def __init__(
        self,
        position: Position,
        identifier: Identifier,
        supertype_declaration: Optional[SupertypeDeclaration],
        subtype_declaration: Optional[SubtypeDeclaration],
        explicit_clauses: Sequence[ExplicitAttributeDefinition],
        derive_clauses: Sequence[DeriveClause],
        inverse_clauses: Sequence[InverseClause],
        unique_rules: Sequence[UniqueRule],
        domain_rules: Sequence[DomainRule],
    ) -> None:
        super().__init__(position)
        self.identifier = identifier
        self.supertype_declaration = supertype_declaration
        self.subtype_declaration = subtype_declaration
        self.explicit_clauses = explicit_clauses
        self.derive_clauses = derive_clauses
        self.inverse_clauses = inverse_clauses
        self.unique_rules = unique_rules
        self.domain_rules = domain_rules


class TypeDeclaration(Node):
    identifier: Final[Identifier]
    type_selection: Final[TypeSelection]
    domain_rules: Final[Sequence[DomainRule]]

    def __init__(
        self,
        position: Position,
        identifier: Identifier,
        type_selection: TypeSelection,
        domain_rules: Sequence[DomainRule],
    ) -> None:
        super().__init__(position)
        self.identifier = identifier
        self.type_selection = type_selection
        self.domain_rules = domain_rules


class AggregateType(Node):
    label: Final[Optional[Identifier]]
    of: Final["ParameterType"]

    def __init__(
        self, position: Position, label: Optional[Identifier], of: "ParameterType"
    ) -> None:
        super().__init__(position)
        self.label = label
        self.of = of


class ConformantArrayType(Node):
    bound_spec: Final[Optional[BoundSpec]]
    optional: Final[bool]
    unique: Final[bool]
    of: Final["ParameterType"]

    def __init__(
        self,
        position: Position,
        bound_spec: Optional[BoundSpec],
        optional: bool,
        unique: bool,
        of: "ParameterType",
    ) -> None:
        super().__init__(position)
        self.bound_spec = bound_spec
        self.optional = optional
        self.unique = unique
        self.of = of


class ConformantBagType(Node):
    bound_spec: Final[Optional[BoundSpec]]
    of: Final["ParameterType"]

    def __init__(
        self, position: Position, bound_spec: Optional[BoundSpec], of: "ParameterType"
    ) -> None:
        super().__init__(position)
        self.bound_spec = bound_spec
        self.of = of


class ConformantListType(Node):
    bound_spec: Final[Optional[BoundSpec]]
    unique: Final[bool]
    of: Final["ParameterType"]

    def __init__(
        self,
        position: Position,
        bound_spec: Optional[BoundSpec],
        unique: bool,
        of: "ParameterType",
    ) -> None:
        super().__init__(position)
        self.bound_spec = bound_spec
        self.unique = unique
        self.of = of


class ConformantSetType(Node):
    bound_spec: Final[Optional[BoundSpec]]
    of: Final["ParameterType"]

    def __init__(
        self, position: Position, bound_spec: Optional[BoundSpec], of: "ParameterType"
    ) -> None:
        super().__init__(position)
        self.bound_spec = bound_spec
        self.of = of


ConformantType = Union[
    ConformantArrayType, ConformantBagType, ConformantListType, ConformantSetType
]

# NOTE (mristin):
# We take the naming here from iso-10303-11.bnf instead of Express.g4 since
# ``parameter_type`` makes more sense than ``allTypeSel``.
ParameterType = Union[AggregateType, ConformantType, SimpleType, NamedType, GenericType]


class FormalParameter(Node):
    identifiers: Final[Sequence[Identifier]]
    of_type: Final[ParameterType]

    def __init__(
        self,
        position: Position,
        identifiers: Sequence[Identifier],
        of_type: ParameterType,
    ) -> None:
        super().__init__(position)
        self.identifiers = identifiers
        self.of_type = of_type


Declaration = Union[
    EntityDeclaration, TypeDeclaration, "FunctionDeclaration", "ProcedureDeclaration"
]


class ConstantDefinition(Node):
    identifier: Final[Identifier]

    # NOTE (mristin):
    # We re-use the collection type selection here although constant is not strictly
    # a collection. However, we already defined a more general type selection which
    # does not apply to constants.
    type_selection: Final[CollectionTypeSelection]

    init: Final[Expr]

    def __init__(
        self,
        position: Position,
        identifier: Identifier,
        type_selection: CollectionTypeSelection,
        init: Expr,
    ) -> None:
        super().__init__(position)
        self.identifier = identifier
        self.type_selection = type_selection
        self.init = init


class LocalVariableDefinition(Node):
    identifiers: Final[Sequence[Identifier]]
    of_type: Final[ParameterType]
    init: Final[Optional[Expr]]

    def __init__(
        self,
        position: Position,
        identifiers: Sequence[Identifier],
        of_type: ParameterType,
        init: Optional[Expr] = None,
    ) -> None:
        super().__init__(position)
        self.identifiers = identifiers
        self.of_type = of_type
        self.init = init


class AliasStmt(Node):
    variable: Final[Identifier]
    target: Final[Expr]
    body: Final[Sequence["Stmt"]]

    def __init__(
        self,
        position: Position,
        variable: Identifier,
        target: Expr,
        body: Sequence["Stmt"],
    ) -> None:
        super().__init__(position)
        self.variable = variable
        self.target = target
        self.body = body


class AssignmentStmt(Node):
    # NOTE (mristin):
    # We adopt the structure from Python's AST where target is very liberal. While
    # Express schema is much stricter when it comes to target, we allow arbitrary
    # expressions to lower the complexity of the interface.
    #
    # For example, from ``Express.g4``:
    # assignmentStmt
    # 	: varRef ':=' (expression|derivedPath|'[]') ';'
    # 	;
    #
    # varRef
    # 	: varDef qualifier
    # 	| aliasRef qualifier
    # 	| attrRef qualifier
    # 	| constRef qualifier
    # 	| entityRef
    # 	| enumRef
    # 	| funcRef qualifier
    # 	| paramRef qualifier
    # 	| procRef
    # 	;
    #
    # Instead of modelling ``varRef``, we simply take ``Expr`` and allow the client to
    # restrict the output after parsing.

    target: Final[Expr]
    value: Final[Expr]

    def __init__(
        self,
        position: Position,
        target: Expr,
        value: Expr,
    ) -> None:
        super().__init__(position)
        self.target = target
        self.value = value


class CaseAction(Node):
    labels: Final[Sequence[Expr]]
    stmt: Final["Stmt"]

    def __init__(
        self, position: Position, labels: Sequence[Expr], stmt: "Stmt"
    ) -> None:
        super().__init__(position)
        self.labels = labels
        self.stmt = stmt


class CaseStmt(Node):
    selector: Final[Expr]
    actions: Final[Sequence[CaseAction]]
    otherwise: Final[Optional["Stmt"]]

    def __init__(
        self,
        position: Position,
        selector: Expr,
        actions: Sequence[CaseAction],
        otherwise: Optional["Stmt"] = None,
    ) -> None:
        super().__init__(position)
        self.selector = selector
        self.actions = actions
        self.otherwise = otherwise


class CompoundStmt(Node):
    stmts: Final[Sequence["Stmt"]]

    def __init__(self, position: Position, stmts: Sequence["Stmt"]) -> None:
        super().__init__(position)
        self.stmts = stmts


class EscapeStmt(Node):
    pass


class IfStmt(Node):
    condition: Final[Expr]
    then: Final[Sequence["Stmt"]]
    or_else: Final[Sequence["Stmt"]]

    def __init__(
        self,
        position: Position,
        condition: Expr,
        then: Sequence["Stmt"],
        or_else: Sequence["Stmt"],
    ) -> None:
        super().__init__(position)
        self.condition = condition
        self.then = then
        self.or_else = or_else


class NullStmt(Node):
    pass


class CallStmt(Node):
    call: Final[Call]

    def __init__(self, position: Position, call: Call) -> None:
        super().__init__(position)
        self.call = call


class IncrementControl(Node):
    variable: Final[Identifier]
    bound_1: Final[Expr]
    bound_2: Final[Expr]
    increment: Final[Optional[Expr]]

    def __init__(
        self,
        position: Position,
        variable: Identifier,
        bound_1: Expr,
        bound_2: Expr,
        increment: Optional[Expr],
    ) -> None:
        super().__init__(position)
        self.variable = variable
        self.bound_1 = bound_1
        self.bound_2 = bound_2
        self.increment = increment


class RepeatControl(Node):
    increment_control: Final[Optional[IncrementControl]]
    while_control: Final[Optional[Expr]]
    until_control: Final[Optional[Expr]]

    def __init__(
        self,
        position: Position,
        increment_control: Optional[IncrementControl],
        while_control: Optional[Expr],
        until_control: Optional[Expr],
    ) -> None:
        super().__init__(position)
        self.increment_control = increment_control
        self.while_control = while_control
        self.until_control = until_control


class RepeatStmt(Node):
    control: Final[RepeatControl]
    body: Final[Sequence["Stmt"]]

    def __init__(
        self, position: Position, control: RepeatControl, body: Sequence["Stmt"]
    ) -> None:
        super().__init__(position)
        self.control = control
        self.body = body


class ReturnStmt(Node):
    value: Final[Optional[Expr]]

    def __init__(self, position: Position, value: Optional[Expr]) -> None:
        super().__init__(position)
        self.value = value


class SkipStmt(Node):
    pass


Stmt = Union[
    AliasStmt,
    AssignmentStmt,
    CaseStmt,
    CompoundStmt,
    EscapeStmt,
    IfStmt,
    NullStmt,
    CallStmt,
    RepeatStmt,
    ReturnStmt,
    SkipStmt,
]


class AlgorithmHead:
    declarations: Final[Sequence[Declaration]]
    constant_definitions: Final[Sequence[ConstantDefinition]]
    local_variable_definitions: Final[Sequence[LocalVariableDefinition]]

    def __init__(
        self,
        declarations: Sequence[Declaration],
        constant_definitions: Sequence[ConstantDefinition],
        local_variable_definitions: Sequence[LocalVariableDefinition],
    ) -> None:
        self.declarations = declarations
        self.constant_definitions = constant_definitions
        self.local_variable_definitions = local_variable_definitions


class FunctionDeclaration(Node):
    identifier: Final[Identifier]
    formal_parameters: Final[Sequence[FormalParameter]]
    return_type: Final[ParameterType]
    head: Final[AlgorithmHead]
    body: Final[Sequence[Stmt]]

    def __init__(
        self,
        position: Position,
        identifier: Identifier,
        formal_parameters: Sequence[FormalParameter],
        return_type: ParameterType,
        head: AlgorithmHead,
        body: Sequence[Stmt],
    ) -> None:
        super().__init__(position)
        self.identifier = identifier
        self.formal_parameters = formal_parameters
        self.return_type = return_type
        self.head = head
        self.body = body


class ProcedureDeclaration(Node):
    identifier: Final[Identifier]
    formal_parameters: Final[Sequence[FormalParameter]]
    head: Final[AlgorithmHead]
    body: Final[Sequence[Stmt]]

    def __init__(
        self,
        position: Position,
        identifier: Identifier,
        formal_parameters: Sequence[FormalParameter],
        head: AlgorithmHead,
        body: Sequence[Stmt],
    ) -> None:
        super().__init__(position)
        self.identifier = identifier
        self.formal_parameters = formal_parameters
        self.head = head
        self.body = body


class RuleDeclaration(Node):
    identifier: Final[Identifier]
    for_entities: Final[Sequence[Identifier]]
    head: Final[AlgorithmHead]
    body: Final[Sequence[Stmt]]
    where: Final[Sequence[DomainRule]]

    def __init__(
        self,
        position: Position,
        identifier: Identifier,
        for_entities: Sequence[Identifier],
        head: AlgorithmHead,
        body: Sequence[Stmt],
        where: Sequence[DomainRule],
    ) -> None:
        super().__init__(position)
        self.identifier = identifier
        self.for_entities = for_entities
        self.head = head
        self.body = body
        self.where = where


class ImportItem(Node):
    reference: Final[Identifier]
    alias: Final[Optional[Identifier]]

    def __init__(
        self,
        position: Position,
        reference: Identifier,
        alias: Optional[Identifier],
    ) -> None:
        super().__init__(position)
        self.reference = reference
        self.alias = alias


class ReferenceClause(Node):
    schema_ref: Final[Identifier]
    import_list: Final[Sequence[ImportItem]]

    def __init__(
        self,
        position: Position,
        schema_ref: Identifier,
        import_list: Sequence[ImportItem],
    ) -> None:
        super().__init__(position)
        self.schema_ref = schema_ref
        self.import_list = import_list


class UseItem(Node):
    reference: Final[Identifier]
    alias: Final[Optional[Identifier]]

    def __init__(
        self,
        position: Position,
        reference: Identifier,
        alias: Optional[Identifier],
    ) -> None:
        super().__init__(position)
        self.reference = reference
        self.alias = alias


class UseClause(Node):
    schema_ref: Final[Identifier]
    use_list: Final[Sequence[UseItem]]

    def __init__(
        self,
        position: Position,
        schema_ref: Identifier,
        use_list: Sequence[UseItem],
    ) -> None:
        super().__init__(position)
        self.schema_ref = schema_ref
        self.use_list = use_list


class Schema(Node):
    identifier: Final[Identifier]
    reference_clauses: Final[Sequence["ReferenceClause"]]
    use_clauses: Final[Sequence["UseClause"]]
    constant_definitions: Final[Sequence["ConstantDefinition"]]
    entity_declarations: Final[Sequence["EntityDeclaration"]]
    function_declarations: Final[Sequence["FunctionDeclaration"]]
    procedure_declarations: Final[Sequence["ProcedureDeclaration"]]
    type_declarations: Final[Sequence["TypeDeclaration"]]
    rule_declarations: Final[Sequence["RuleDeclaration"]]

    def __init__(
        self,
        position: Position,
        identifier: Identifier,
        reference_clauses: Sequence["ReferenceClause"],
        use_clauses: Sequence["UseClause"],
        constant_definitions: Sequence["ConstantDefinition"],
        entity_declarations: Sequence["EntityDeclaration"],
        function_declarations: Sequence["FunctionDeclaration"],
        procedure_declarations: Sequence["ProcedureDeclaration"],
        type_declarations: Sequence["TypeDeclaration"],
        rule_declarations: Sequence["RuleDeclaration"],
    ) -> None:
        super().__init__(position)
        self.identifier = identifier
        self.reference_clauses = reference_clauses
        self.use_clauses = use_clauses
        self.constant_definitions = constant_definitions
        self.entity_declarations = entity_declarations
        self.function_declarations = function_declarations
        self.procedure_declarations = procedure_declarations
        self.type_declarations = type_declarations
        self.rule_declarations = rule_declarations


# endregion AST

# region Parse


class _TokenTape:
    """
    Iterate and jump through the sequence of tokens.

    The comments are expected to be removed from the tape as noise.
    """

    # fmt: off
    @require(
        lambda tokens:
        all(
            token.kind is not _TokenKind.COMMENT
            for token in tokens
        )
    )
    @require(
        lambda tokens:
        len(set(id(token) for token in tokens)) == len(tokens),
        "Tokens must not contain any duplicate token objects."
    )
    # fmt: on
    def __init__(self, tokens: Sequence[_Token]) -> None:
        self._tokens = tokens
        self._cursor = 0

    def token(self) -> Optional[_Token]:
        """Retrieve the token pointed to by the cursor."""
        if self._cursor >= len(self._tokens):
            return None

        return self._tokens[self._cursor]

    @snapshot(lambda self: self.token(), "token")
    @ensure(lambda self, OLD: self.token() is OLD.token, "The cursor did not move.")
    def tokens(self, count: NonNegativeInt) -> Optional[Sequence[_Token]]:
        """
        Retrieve that many tokens pointed by the cursor without moving the cursor.

        Return None if there are not enough tokens on the tape left.
        """
        if self._cursor + count > len(self._tokens):
            return None

        return self._tokens[self._cursor : self._cursor + count]

    def move_by(self, offset: int) -> None:
        """Move the cursor by the given offset."""
        self._cursor += offset


class _Associativity(enum.Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    NONASSOCIATIVE = "NONASSOCIATIVE"


# region Decorators for _Parser

# NOTE (mristin):
# We put the decorators outside ``_Parser`` since mypy got confused with
# static methods.


T = TypeVar("T")

P = ParamSpec("P")


def _affect_parsing_stack(
    func: Callable[Concatenate["_Parser", P], T],
) -> Callable[Concatenate["_Parser", P], T]:
    @functools.wraps(func)
    def wrapped(that: "_Parser", /, *args: P.args, **kwargs: P.kwargs) -> T:
        name = func.__name__
        if name.startswith("_parse_"):
            name = name[len("_parse_") :]
        elif name.startswith("parse_"):
            name = name[len("parse_") :]
        else:
            pass

        name = name.replace("_", " ")

        # pylint: disable=protected-access
        that._stack.append(name)

        try:
            result = func(that, *args, **kwargs)
            return result
        finally:
            that._stack.pop()

    return wrapped


def _ensure_nibble_result_coincides_with_errors(
    func: Callable[Concatenate["_Parser", P], Optional[_Token]],
) -> Callable[Concatenate["_Parser", P], Optional[_Token]]:
    # NOTE (mristin):
    # Icontract does not support pre-definition and re-use of contracts, so we
    # define our own post-condition checker.

    @functools.wraps(func)
    def wrapped(
        that: "_Parser", /, *args: P.args, **kwargs: P.kwargs
    ) -> Optional[_Token]:
        old_error_count = len(that.errors)

        result = func(that, *args, **kwargs)

        assert (
            not (result is not None) or len(that.errors) == old_error_count
        ), "No errors must be emitted if nibble successful."

        assert (
            not (result is None) or len(that.errors) == old_error_count + 1
        ), "Exactly one error must be emitted if nibble failed."

        return result

    return wrapped


# NOTE (mristin):
# Mypy can not do arugment matching, so we can not write ``Optional[T]`` within
# the ``Callable`` -- mypy will not match the union passed as T, but the most basic
# supertype. That is why we have to introduce this clumsy ``OptionalT``.
OptionalT = TypeVar("OptionalT", bound=Optional[Any])


def _ensure_parse_result_coincides_with_last_parsed_token_and_errors(
    func: Callable[Concatenate["_Parser", P], OptionalT],
) -> Callable[Concatenate["_Parser", P], OptionalT]:
    # NOTE (mristin):
    # Icontract does not support pre-definition and re-use of contracts, so we
    # define our own post-condition checker.

    # pylint: disable=protected-access

    @functools.wraps(func)
    def wrapped(that: "_Parser", /, *args: P.args, **kwargs: P.kwargs) -> OptionalT:
        old_last_parsed_token = that._last_parsed_token

        result = func(that, *args, **kwargs)

        assert (
            not (result is not None)
            or that._last_parsed_token is not old_last_parsed_token
        ), "Last parsed token must move on success."

        assert (
            not (result is None) or len(that.errors) > 0
        ), "There must be errors on failure."

        assert (
            not (result is not None) or len(that.errors) == 0
        ), "There must be no errors on success."

        return result

    return wrapped


def _ensure_last_parsed_token_is_semi_on_success(
    func: Callable[Concatenate["_Parser", P], OptionalT],
) -> Callable[Concatenate["_Parser", P], OptionalT]:
    # NOTE (mristin):
    # Icontract does not support pre-definition and re-use of contracts, so we
    # define our own post-condition checker.

    # pylint: disable=protected-access

    @functools.wraps(func)
    def wrapped(that: "_Parser", /, *args: P.args, **kwargs: P.kwargs) -> OptionalT:
        result = func(that, *args, **kwargs)

        if result is not None:
            assert that._last_parsed_token is not None, (
                "We expected the last parsed token on success to be "
                "a semi-colon (`;`), "
                "but the last parsed token is set to None"
            )

            assert that._last_parsed_token.kind is _TokenKind.SEMI, (
                f"We expected the last parsed token on success to be "
                f"a semi-colon (`;`), "
                f"but we parsed {that._last_parsed_token.kind}: "
                f"{that._last_parsed_token.text!r}"
            )

        return result

    return wrapped


# endregion Decorators for _Parser


class _Parser:
    """Parse recursively the tokens into an Express schema."""

    #: List one or more parsing errors. The errors should be checked after each parsing.
    errors: Final[List[Error]]

    def __init__(self, tape: _TokenTape) -> None:
        self.errors = []

        #: List the current parsing stack
        self._stack = []  # type: List[str]

        self._tape = tape
        self._last_parsed_token = None  # type: Optional[_Token]

    def _emit_error(self, message: str) -> None:
        token = self._tape.token()
        if token is None:
            if self._last_parsed_token is not None:
                line = self._last_parsed_token.position.lineno
                column = (
                    self._last_parsed_token.position.column
                    + len(self._last_parsed_token.text)
                    - 1
                )
            else:
                line = NonNegativeInt(0)
                column = NonNegativeInt(0)
        else:
            line = token.position.lineno
            column = token.position.column

        if len(self._stack) > 0:
            stack_joined = ", ".join(self._stack)
            message = f"{message}\nParsing chain: {stack_joined}"

        error = Error(message=message, line=line, column=column)
        self.errors.append(error)

    def _emit_error_at(self, message: str, token: _Token) -> None:
        self.errors.append(
            Error(
                message=message,
                line=token.position.lineno,
                column=token.position.column,
            )
        )

    # fmt: off
    @ensure(
        lambda kinds, result:
        not (result is not None)
        or (
            len(kinds) == len(result)
            and all(
                kind == token.kind
                for kind, token in zip(kinds, result)
            )
        )
    )
    # fmt: on
    def _peek_kinds(self, kinds: Sequence[_TokenKind]) -> Optional[Sequence[_Token]]:
        """
        Peek on the tape if the next tokens are of the given kinds.

        Return the tokens if they do, or None otherwise.
        """
        tokens = self._tape.tokens(NonNegativeInt(len(kinds)))
        if tokens is None:
            return None

        if all(
            token.kind is expected_kind for token, expected_kind in zip(tokens, kinds)
        ):
            return tokens
        else:
            return None

    def _peek_kind(self, kind: _TokenKind) -> Optional[_Token]:
        """
        Peek on the tape if the current token is of the given kind.

        Return the token if it does, or None otherwise.
        """
        token = self._tape.token()
        if token is None:
            return None

        if token.kind is kind:
            return token
        else:
            return None

    def _peek_in_kind_set(self, kind_set: FrozenSet[_TokenKind]) -> Optional[_Token]:
        """
        Peek on the tape if the current token is of one kind in the given set.

        Return the token if it does, or None otherwise.
        """
        token = self._tape.token()
        if token is None:
            return None

        if token.kind in kind_set:
            return token
        else:
            return None

    @_ensure_nibble_result_coincides_with_errors
    def _nibble(self) -> Optional[_Token]:
        """
        Consume the current token.

        Return the nibbled token, or None if failed.
        """
        token = self._tape.token()
        if token is None:
            self._emit_error("Expected a token, but got an end-of-input")
            return None

        self._tape.move_by(1)
        return token

    @_ensure_nibble_result_coincides_with_errors
    def _nibble_kind(self, expected_kind: _TokenKind) -> Optional[_Token]:
        """
        Consume the current token assuming it matches the expected kind.

        Return the nibbled token, or None if failed.
        """
        token = self._tape.token()
        if token is None:
            self._emit_error(
                f"Expected a token {expected_kind.name!r}, but got an end-of-input"
            )
            return None

        if token.kind is not expected_kind:
            self._emit_error(
                f"Expected a token {expected_kind.name!r}, "
                f"but got a token {token.kind.name!r}: {token.text!r}"
            )
            return None

        self._tape.move_by(1)
        return token

    @_ensure_nibble_result_coincides_with_errors
    def _nibble_in_kind_set(
        self, expected_kind_set: FrozenSet[_TokenKind]
    ) -> Optional[_Token]:
        """
        Consume the current token assuming it is in the set of the expected kinds.

        Return the nibbled token, or None if failed.
        """
        token = self._tape.token()
        if token is None:
            expected_set_joined = ", ".join(
                sorted([kind.name for kind in expected_kind_set])
            )
            self._emit_error(
                f"Expected a token in {expected_set_joined}, but got an end-of-input"
            )
            return None

        if token.kind not in expected_kind_set:
            expected_set_joined = ", ".join(
                sorted([kind.name for kind in expected_kind_set])
            )
            self._emit_error(
                f"Expected a token in {expected_set_joined}, "
                f"but got a token {token.kind.name!r}"
            )
            return None

        self._tape.move_by(1)
        return token

    @staticmethod
    def _position_from_token(token: _Token) -> Position:
        return Position(lineno=token.position.lineno, column=token.position.column)

    # NOTE (mristin):
    # We implement here precedence-climbing expression parser, see:
    # https://en.wikipedia.org/wiki/Operator-precedence_parser
    #
    # The postfix operators like index expression, attribute or qualified attribute
    # reference are dealt separately.

    _LiteralKind = typing.Literal[
        _TokenKind.BINARY_LITERAL,
        _TokenKind.INTEGER_LITERAL,
        _TokenKind.REAL_LITERAL,
        _TokenKind.STRING_LITERAL,
        _TokenKind.TRUE,
        _TokenKind.FALSE,
        _TokenKind.UNKNOWN,
        _TokenKind.QMARK,
    ]

    _LITERAL_KIND_SET: FrozenSet[_LiteralKind] = frozenset(get_args(_LiteralKind))

    @staticmethod
    def _is_hex_text(text: str) -> bool:
        """
        Check whether the text is a valid Hex representation.

        >>> _Parser._is_hex_text("this is not hex text")
        False

        >>> _Parser._is_hex_text("deadbeef")
        True

        >>> _Parser._is_hex_text("c01dc0ffe")
        True
        """
        try:
            int(text, 16)
            return True
        except ValueError:
            return False

    @staticmethod
    @ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
    def _unescape_string_token(content: str) -> Tuple[Optional[str], Optional[str]]:
        r"""
        Unescape a quoted EXPRESS string literal.

        Handle:
        - Simple escapes: \\ \' \" \n \r \t \f \b \0
        - STEP extended escapes:
                \X\<hex>\X\          (UCS-2, 4 hex digits per code unit)
                \X2\<hex>\X0\        (UCS-4, 8 hex digits per code point)
                \S\hh                  (Latin-1 byte; two hex digits)

        Return the unescaped string, or an error.
        """
        if len(content) < 2:
            return None, (
                f"Expected single quotes around the string literal, "
                f"but got an input of only {len(content)} character(s)"
            )

        if content[0] != "'" or content[-1] != "'":
            return None, (
                f"Expected single quotes around the string literal, "
                f"but got prefix {content[0]!r} and suffix {content[-1]!r}"
            )

        wo_quotes = content[1:-1]

        map_of_simple_escapes: Dict[str, str] = {
            "n": "\n",
            "r": "\r",
            "t": "\t",
            "f": "\f",
            "b": "\b",
            "0": "\0",
            "\\": "\\",
            "'": "'",
            '"': '"',
        }

        result: List[str] = []
        cursor = 0
        len_wo_quotes = len(wo_quotes)

        def consume_until(marker: str, start: int) -> Optional[int]:
            """
            Find next occurrence of marker starting at ``start``.

            Return the index of the occurrence, or None if not found.
            """
            j = wo_quotes.find(marker, start)
            return j if j != -1 else None

        while cursor < len_wo_quotes:
            character = wo_quotes[cursor]
            if character != "\\":
                result.append(character)
                cursor += 1
                continue

            # We have a backslash.

            cursor += 1
            if cursor >= len_wo_quotes:
                return None, "Dangling backslash at the end of the string literal"

            # Extended escapes first (multi-char lookahead)
            # \X2\...\X0\
            if wo_quotes.startswith("X2\\", cursor):
                # The content of the extended escape starts after '\X2\'.
                content_start = cursor + 3
                end = consume_until("\\X0\\", content_start)

                if end is None:
                    return None, "Unterminated \\X2\\...\\X0\\ escape"

                hex_sequence = wo_quotes[content_start:end]

                if len(hex_sequence) % 8 != 0 or not _Parser._is_hex_text(hex_sequence):
                    return None, "\\X2\\ block must be groups of 8 hex digits"

                for k in range(0, len(hex_sequence), 8):
                    codepoint = int(hex_sequence[k : k + 8], 16)
                    result.append(chr(codepoint))

                cursor = end + 4  # skip past '\X0\'
                continue

            # \X\...\X\
            if wo_quotes.startswith("X\\", cursor):
                content_start = cursor + 2
                end = consume_until("\\X\\", content_start)
                if end is None:
                    return None, "Unterminated \\X\\...\\X\\ escape"

                hex_sequence = wo_quotes[content_start:end]
                if len(hex_sequence) % 4 != 0 or not _Parser._is_hex_text(hex_sequence):
                    return None, "\\X\\ block must be groups of 4 hex digits"

                for k in range(0, len(hex_sequence), 4):
                    codeunit = int(hex_sequence[k : k + 4], 16)  # UCS-2 unit

                    # NOTE (mristin):
                    # UCS-2 does not support surrogate pairs to represent characters
                    # above Basic Multilinguagal Plane (BMP).
                    if 0xD800 <= codeunit <= 0xDFFF:
                        return None, "Lone surrogate in \\X\\ block"

                    result.append(chr(codeunit))

                cursor = end + 3  # skip past '\X\'
                continue

            # \S\hh  (exactly two hex digits)
            if wo_quotes.startswith("S\\", cursor):
                j = cursor + 2
                if j + 2 > len_wo_quotes:
                    return None, "Incomplete \\S\\hh escape"

                hh = wo_quotes[j : j + 2]
                if not _Parser._is_hex_text(hh):
                    return None, "Invalid hex in \\S\\hh escape"

                result.append(chr(int(hh, 16)))  # Latin-1 byte → same codepoint
                cursor = j + 2
                continue

            # Simple one-letter escapes (e.g., \n, \r, \t, \\, \', \")
            next_character = wo_quotes[cursor]
            mapped = map_of_simple_escapes.get(next_character)
            if mapped is not None:
                result.append(mapped)
                cursor += 1
                continue

            # Unknown escape: keep the backslash + next char literally according to
            # the specification
            result.append("\\")
            result.append(next_character)
            cursor += 1

        return "".join(result), None

    _LOGICAL_FROM_KIND = {
        _TokenKind.TRUE: LogicalValue.TRUE,
        _TokenKind.FALSE: LogicalValue.FALSE,
        _TokenKind.UNKNOWN: LogicalValue.UNKNOWN,
    }

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_literal(self) -> Optional[Literal]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_in_kind_set(_Parser._LITERAL_KIND_SET)
        if token is None:
            return None

        assert is_literal_in(token.kind, _Parser._LITERAL_KIND_SET)

        position = _Parser._position_from_token(token)

        # NOTE (mristin):
        # We have to update the last parsed token in each branch separately as string
        # literals are exceptions -- they might not be parsed correctly even though
        # we lexed them correctly.

        if token.kind is _TokenKind.BINARY_LITERAL:
            self._last_parsed_token = token

            assert token.text.startswith("%"), (
                f"Expected a binary literal token to start with '%', "
                f"but got: {token.text}"
            )
            binary_text = token.text[1:]

            byte_parts = []  # type: List[bytes]

            for i in range(0, len(binary_text), 8):
                byte_part = int(binary_text[i : i + 8], 2).to_bytes(1, byteorder="big")
                byte_parts.append(byte_part)

            return BinaryLiteral(position=position, value=b"".join(byte_parts))

        elif token.kind is _TokenKind.REAL_LITERAL:
            self._last_parsed_token = token

            return RealLiteral(position=position, value=decimal.Decimal(token.text))

        elif token.kind is _TokenKind.INTEGER_LITERAL:
            self._last_parsed_token = token

            return IntegerLiteral(position=position, value=int(token.text))

        elif token.kind is _TokenKind.STRING_LITERAL:
            value, error = _Parser._unescape_string_token(token.text)

            if error is not None:
                self._emit_error(f"Failed to parse the string literal: {error}")
                return None

            assert value is not None

            self._last_parsed_token = token

            return StringLiteral(position=position, value=value)

        elif token.kind in _Parser._LOGICAL_FROM_KIND:
            self._last_parsed_token = token

            return LogicalLiteral(
                position=position, value=_Parser._LOGICAL_FROM_KIND[token.kind]
            )

        elif token.kind is _TokenKind.QMARK:
            self._last_parsed_token = token

            return IndeterminateLiteral(position=position)

        else:
            raise NotImplementedError(
                f"Unexpected unhandled literal token kind: {token.kind}"
            )

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_aggregate_literal(self) -> Optional[AggregateLiteral]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.LSQ)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        elements = []  # type: List[Element]

        while True:
            if (token := self._peek_kind(_TokenKind.RSQ)) is not None:
                self._last_parsed_token = token
                self._tape.move_by(1)

                return AggregateLiteral(position=position, elements=elements)
            else:
                if len(elements) > 0:
                    if self._nibble_kind(_TokenKind.COMMA) is None:
                        return None

                expr = self._parse_expr()
                if expr is None:
                    return None

                repetition = None  # type: Optional[Expr]
                if self._peek_kind(_TokenKind.COLON):
                    self._tape.move_by(1)

                    repetition = self._parse_expr()
                    if repetition is None:
                        return None

                elements.append(
                    Element(
                        position=copy.copy(expr.position),
                        expr=expr,
                        repetition=repetition,
                    )
                )

    _UNARY_OP_KIND_SET = frozenset([_TokenKind.NOT, _TokenKind.PLUS, _TokenKind.MINUS])

    _UNARY_OP_FROM_KIND = {
        _TokenKind.PLUS: UnaryOp.PLUS,
        _TokenKind.MINUS: UnaryOp.NEG,
        _TokenKind.NOT: UnaryOp.NOT,
    }

    _INTERVAL_OP_KIND_SET = frozenset([_TokenKind.LT, _TokenKind.LE])

    _INTERVAL_OP_FROM_KIND: Dict[_TokenKind, IntervalOp] = {
        _TokenKind.LT: BinaryOp.LESS_THAN,
        _TokenKind.LE: BinaryOp.LESS_EQUAL,
    }

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_primary_or_unary(self) -> Optional[Expr]:
        if len(self.errors) > 0:
            return None

        result: Expr

        if (token := self._peek_in_kind_set(_Parser._UNARY_OP_KIND_SET)) is not None:
            position = _Parser._position_from_token(token)
            self._tape.move_by(1)

            operand = self._parse_primary_or_unary()
            if operand is None:
                return None

            result = UnaryExpr(
                position=position,
                op=_Parser._UNARY_OP_FROM_KIND[token.kind],
                operand=operand,
            )

        elif self._peek_kind(_TokenKind.LPAR) is not None:
            self._tape.move_by(1)

            expr = self._parse_expr()
            if expr is None:
                return None

            result = expr

            token = self._nibble_kind(_TokenKind.RPAR)
            if token is None:
                return None

            self._last_parsed_token = token

        elif self._peek_kind(_TokenKind.LSQ) is not None:
            aggregate_literal = self._parse_aggregate_literal()
            if aggregate_literal is None:
                return None

            result = aggregate_literal

        elif (token := self._peek_kind(_TokenKind.LCRLY)) is not None:
            position = _Parser._position_from_token(token)

            self._tape.move_by(1)

            # NOTE (mristin):
            # We explicitly disallow binding of relational operators.
            relational_precedence, relational_associativity = (
                _Parser._BINARY_PRECEDENCE_MAP[_TokenKind.LT]
            )
            assert relational_associativity is _Associativity.NONASSOCIATIVE

            above_relational_precedence = relational_precedence + 1

            left = self._parse_expr(min_precedence=above_relational_precedence)

            if left is None:
                return None

            token = self._nibble_in_kind_set(_Parser._INTERVAL_OP_KIND_SET)
            if token is None:
                return None

            left_to_center = _Parser._INTERVAL_OP_FROM_KIND[token.kind]

            center = self._parse_expr(min_precedence=above_relational_precedence)
            if center is None:
                return None

            token = self._nibble_in_kind_set(_Parser._INTERVAL_OP_KIND_SET)
            if token is None:
                return None

            center_to_right = _Parser._INTERVAL_OP_FROM_KIND[token.kind]

            right = self._parse_expr(min_precedence=above_relational_precedence)
            if right is None:
                return None

            token = self._nibble_kind(_TokenKind.RCRLY)
            if token is None:
                return None

            self._last_parsed_token = token

            result = Interval(
                position=position,
                left=left,
                left_to_center=left_to_center,
                center=center,
                center_to_right=center_to_right,
                right=right,
            )

        elif (token := self._peek_kind(_TokenKind.QUERY)) is not None:
            position = _Parser._position_from_token(token)

            self._tape.move_by(1)

            if self._nibble_kind(_TokenKind.LPAR) is None:
                return None

            token = self._nibble_kind(_TokenKind.IDENTIFIER)
            if token is None:
                return None

            variable = Identifier(token.text)

            if self._nibble_kind(_TokenKind.LT_STAR) is None:
                return None

            aggregate = self._parse_expr()
            if aggregate is None:
                return None

            if self._nibble_kind(_TokenKind.PIPE) is None:
                return None

            predicate = self._parse_expr()
            if predicate is None:
                return None

            token = self._nibble_kind(_TokenKind.RPAR)
            if token is None:
                return None

            self._last_parsed_token = token

            result = QueryExpr(
                position=position,
                variable=variable,
                aggregate=aggregate,
                predicate=predicate,
            )

        elif self._peek_in_kind_set(_Parser._LITERAL_KIND_SET) is not None:
            literal = self._parse_literal()
            if literal is None:
                return None

            result = literal

        elif (token := self._peek_kind(_TokenKind.SELF)) is not None:
            self._tape.move_by(1)
            self._last_parsed_token = token

            result = Self(position=_Parser._position_from_token(token))

        elif (token := self._peek_kind(_TokenKind.IDENTIFIER)) is not None:
            self._tape.move_by(1)
            self._last_parsed_token = token

            result = NameRef(
                position=_Parser._position_from_token(token),
                identifier=Identifier(token.text),
            )

        else:
            token = self._tape.token()
            if token is None:
                self._emit_error(
                    "Unexpected end of input when parsing a primary "
                    "or unary expression"
                )
            else:
                self._emit_error(
                    f"Unexpected token {token.kind.name!r} "
                    f"when parsing a primary or unary expression: {token.text!r}"
                )

            return None

        # NOTE (mristin):
        # We handle the postfix operators first since they have precedence over
        # any other binary operator.
        while True:
            if self._peek_kind(_TokenKind.LPAR) is not None:
                # This is a call as the postfix starts with a "(".

                args = self._parse_argument_list()
                if args is None:
                    return None

                assert (
                    self._last_parsed_token is not None
                    and self._last_parsed_token.kind is _TokenKind.RPAR
                )
                result = Call(position=result.position, callee=result, args=args)
            elif self._peek_kind(_TokenKind.LSQ) is not None:
                self._tape.move_by(1)

                # This is an index access as the postfix starts with a "[".
                index_expr = self._parse_expr()
                if index_expr is None:
                    return None

                token = self._nibble_kind(_TokenKind.RSQ)
                if token is None:
                    return None

                self._last_parsed_token = token
                result = IndexExpr(
                    position=result.position, source=result, index=index_expr
                )

            elif self._peek_kind(_TokenKind.DOT) is not None:
                # This is an attribute reference.
                self._tape.move_by(1)

                attribute_token = self._nibble_kind(_TokenKind.IDENTIFIER)
                if attribute_token is None:
                    return None

                self._last_parsed_token = attribute_token
                result = AttributeRef(
                    position=copy.copy(result.position),
                    source=result,
                    identifier=Identifier(attribute_token.text),
                )

            elif self._peek_kind(_TokenKind.BACKSLASH) is not None:
                # This is a cast as the postfix starts with a "\".
                self._tape.move_by(1)

                group_qualifier = self._nibble_kind(_TokenKind.IDENTIFIER)
                if group_qualifier is None:
                    return None

                if self._nibble_kind(_TokenKind.DOT) is None:
                    return None

                attribute_token = self._nibble_kind(_TokenKind.IDENTIFIER)
                if attribute_token is None:
                    return None

                self._last_parsed_token = attribute_token
                result = QualifiedAttributeRef(
                    position=result.position,
                    source=result,
                    group_qualifier=Identifier(group_qualifier.text),
                    attribute=Identifier(attribute_token.text),
                )

            else:
                break

        return result

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_argument(self) -> Optional[Arg]:
        if len(self.errors) > 0:
            return None

        token = self._tape.token()
        if token is None:
            self._emit_error("Unexpected end of input while parsing an argument")
            return None

        position = _Parser._position_from_token(token)

        name = None  # type: Optional[Identifier]
        if self._peek_kind(_TokenKind.DOUBLE_HYPHEN) is not None:
            first_token = self._tape.token()
            assert first_token is not None

            self._tape.move_by(1)

            token = self._nibble_kind(_TokenKind.IDENTIFIER)
            if token is None:
                return None

            name = Identifier(token.text)

        value = self._parse_expr()
        if value is None:
            return None

        return Arg(position=position, name=name, value=value)

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_argument_list(self) -> Optional[List[Arg]]:
        if len(self.errors) > 0:
            return None

        if self._nibble_kind(_TokenKind.LPAR) is None:
            return None

        args = []  # type: List[Arg]

        while True:
            old_last_parsed_token = self._last_parsed_token

            if (token := self._peek_kind(_TokenKind.RPAR)) is not None:
                self._last_parsed_token = token
                self._tape.move_by(1)

                return args

            if len(args) > 0:
                if self._nibble_kind(_TokenKind.COMMA) is None:
                    return None

            arg = self._parse_argument()
            if arg is None:
                return None

            args.append(arg)

            assert (
                old_last_parsed_token is not self._last_parsed_token
            ), "Loop invariant -- the last parsed token must constantly move"

    @staticmethod
    def _generate_precedence_map() -> Dict[_TokenKind, Tuple[int, _Associativity]]:
        """Define precedence -- larger number binds tighter."""

        result = dict()  # type: Dict[_TokenKind, Tuple[int, _Associativity]]

        # Logical OR and XOR
        score = 0
        for token_kind in [
            _TokenKind.OR,
            _TokenKind.XOR,
        ]:
            result[token_kind] = (score, _Associativity.LEFT)

        # Logical AND binds tighter than OR and XOR
        score += 10
        for token_kind in [
            _TokenKind.AND,
        ]:
            result[token_kind] = (score, _Associativity.LEFT)

        # Relational
        score += 10
        for token_kind in [
            _TokenKind.GT,
            _TokenKind.LT,
            _TokenKind.GE,
            _TokenKind.LE,
            _TokenKind.NE,
            _TokenKind.EQ,
            _TokenKind.COLON_EQ_COLON,
            _TokenKind.COLON_LT_GT_COLON,
            _TokenKind.LIKE,
            _TokenKind.IN,
        ]:
            result[token_kind] = (score, _Associativity.NONASSOCIATIVE)

        # Addition-like
        score += 10
        for token_kind in [
            _TokenKind.PLUS,
            _TokenKind.MINUS,
            _TokenKind.DOUBLE_PIPE,
        ]:
            result[token_kind] = (score, _Associativity.LEFT)

        # Multiplication-like
        score += 10
        for token_kind in [
            _TokenKind.STAR,
            _TokenKind.SLASH,
            _TokenKind.MOD,
            _TokenKind.DIV,
        ]:
            result[token_kind] = (score, _Associativity.LEFT)

        # Exponentiation
        score += 10
        for token_kind in [
            _TokenKind.DOUBLE_STAR,
        ]:
            result[token_kind] = (score, _Associativity.RIGHT)

        return result

    _BINARY_PRECEDENCE_MAP = _generate_precedence_map()

    _BINARY_OP_FROM_KIND: Dict[_TokenKind, BinaryOp] = {
        # Arithmetic
        _TokenKind.PLUS: BinaryOp.ADD,
        _TokenKind.MINUS: BinaryOp.SUBTRACT,
        _TokenKind.STAR: BinaryOp.MULTIPLY,
        _TokenKind.SLASH: BinaryOp.REAL_DIVIDE,
        _TokenKind.DIV: BinaryOp.INTEGER_DIVIDE,
        _TokenKind.MOD: BinaryOp.MODULO,
        _TokenKind.DOUBLE_STAR: BinaryOp.POWER,
        # Logical
        _TokenKind.OR: BinaryOp.OR,
        _TokenKind.XOR: BinaryOp.XOR,
        _TokenKind.AND: BinaryOp.AND,
        # Collections
        _TokenKind.DOUBLE_PIPE: BinaryOp.CONCAT,
        # Relational (value comparison)
        _TokenKind.LT: BinaryOp.LESS_THAN,
        _TokenKind.GT: BinaryOp.GREATER_THAN,
        _TokenKind.LE: BinaryOp.LESS_EQUAL,
        _TokenKind.GE: BinaryOp.GREATER_EQUAL,
        _TokenKind.EQ: BinaryOp.EQUAL,
        _TokenKind.NE: BinaryOp.NOT_EQUAL,
        # Instance comparison (entity identity)
        _TokenKind.COLON_EQ_COLON: BinaryOp.INSTANCE_EQUAL,
        _TokenKind.COLON_LT_GT_COLON: BinaryOp.INSTANCE_NOT_EQUAL,
        # Membership / pattern match
        _TokenKind.IN: BinaryOp.IN,
        _TokenKind.LIKE: BinaryOp.LIKE,
    }

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_expr(self, min_precedence: int = 0) -> Optional[Expr]:
        if len(self.errors) > 0:
            return None

        result = self._parse_primary_or_unary()
        if result is None:
            return None

        while True:
            token = self._tape.token()
            if token is None:
                break

            precedence_associativity = _Parser._BINARY_PRECEDENCE_MAP.get(
                token.kind, None
            )

            if precedence_associativity is None:
                break

            precedence, associativity = precedence_associativity

            # NOTE (mristin):
            # Why this works:
            # * Left-assoc (+ - * / DIV MOD ||): the RHS can’t grab another operator of
            #   the same precedence, so we use prec + 1.
            #
            # * Right-assoc (^): the RHS can grab another ^ (same precedence), so we use
            #   prec.

            if precedence < min_precedence:
                break

            self._tape.move_by(1)

            if associativity is _Associativity.LEFT:
                next_min_precedence = precedence + 1

            elif associativity is _Associativity.RIGHT:
                next_min_precedence = precedence

            elif associativity is _Associativity.NONASSOCIATIVE:
                # We have to prevent chaining here. When you recurse with prec + 1,
                # it ensures that the RHS of the operator cannot "eat" another operator
                # of the same precedence.
                next_min_precedence = precedence + 1

            else:
                # noinspection PyUnreachableCode
                assert_never(associativity)

            right = self._parse_expr(min_precedence=next_min_precedence)
            if right is None:
                return None

            result = BinaryExpr(
                position=copy.copy(result.position),
                left=result,
                op=_Parser._BINARY_OP_FROM_KIND[token.kind],
                right=right,
            )

        return result

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_bound_spec(self) -> Optional[BoundSpec]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.LSQ)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        lower = self._parse_expr()
        if lower is None:
            return None

        if self._nibble_kind(_TokenKind.COLON) is None:
            return None

        upper = self._parse_expr()
        if upper is None:
            return None

        token = self._nibble_kind(_TokenKind.RSQ)
        if token is None:
            return None

        self._last_parsed_token = token
        return BoundSpec(position=position, lower=lower, upper=upper)

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_named_type(self) -> Optional[NamedType]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.IDENTIFIER)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        self._last_parsed_token = token
        return NamedType(position=position, reference=Identifier(token.text))

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_binary_type(self) -> Optional[BinaryType]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.BINARY)
        if token is None:
            return None

        last_parsed_token = token  # type: Optional[_Token]

        position = _Parser._position_from_token(token)

        width = None  # type: Optional[Expr]
        fixed = False

        if self._peek_kind(_TokenKind.LPAR) is not None:
            self._tape.move_by(1)

            width = self._parse_expr()
            if width is None:
                return None

            token = self._nibble_kind(_TokenKind.RPAR)
            if token is None:
                return None
            last_parsed_token = token

            if self._peek_kind(_TokenKind.FIXED) is not None:
                fixed = True
                assert self._tape.token() is not None
                last_parsed_token = self._tape.token()
                self._tape.move_by(1)
        else:
            if self._peek_kind(_TokenKind.FIXED) is not None:
                self._emit_error("FIXED may only be specified if a width is given")
                return None

        self._last_parsed_token = last_parsed_token
        return BinaryType(position=position, width=width, fixed=fixed)

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_boolean_type(self) -> Optional[BooleanType]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.BOOLEAN)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        self._last_parsed_token = token
        return BooleanType(position=position)

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_integer_type(self) -> Optional[IntegerType]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.INTEGER)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        self._last_parsed_token = token
        return IntegerType(position=position)

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_logical_type(self) -> Optional[LogicalType]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.LOGICAL)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        self._last_parsed_token = token
        return LogicalType(position=position)

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_number_type(self) -> Optional[NumberType]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.NUMBER)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        self._last_parsed_token = token
        return NumberType(position=position)

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_real_type(self) -> Optional[RealType]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.REAL)
        if token is None:
            return None

        last_parsed_token = token

        position = _Parser._position_from_token(token)

        precision_spec = None  # type: Optional[Expr]
        if self._peek_kind(_TokenKind.LPAR) is not None:
            self._tape.move_by(1)

            precision_spec = self._parse_expr()
            if precision_spec is None:
                return None

            token = self._nibble_kind(_TokenKind.RPAR)
            if token is None:
                return None

            last_parsed_token = token

        self._last_parsed_token = last_parsed_token
        return RealType(position=position, precision_spec=precision_spec)

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_string_type(self) -> Optional[StringType]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.STRING)
        if token is None:
            return None

        position = _Parser._position_from_token(token)
        last_parsed_token = token

        width: Optional[Expr] = None
        fixed = False
        if self._peek_kind(_TokenKind.LPAR) is not None:
            self._tape.move_by(1)

            width = self._parse_expr()
            if width is None:
                return None

            token = self._nibble_kind(_TokenKind.RPAR)
            if token is None:
                return None
            last_parsed_token = token

            if self._peek_kind(_TokenKind.FIXED) is not None:
                fixed = True
                token = self._tape.token()
                assert token is not None
                last_parsed_token = token
                self._tape.move_by(1)

        else:
            if self._peek_kind(_TokenKind.FIXED) is not None:
                self._emit_error("FIXED may only be specified if a width is given")
                return None

        self._last_parsed_token = last_parsed_token
        return StringType(position=position, width=width, fixed=fixed)

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_generic_type(self) -> Optional[GenericType]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.GENERIC)
        if token is None:
            return None

        position = _Parser._position_from_token(token)
        last_parsed_token = token

        type_label = None  # type: Optional[Identifier]
        if self._peek_kind(_TokenKind.COLON) is not None:
            self._tape.move_by(1)

            token = self._nibble_kind(_TokenKind.IDENTIFIER)
            if token is None:
                return None

            last_parsed_token = token

        self._last_parsed_token = last_parsed_token
        return GenericType(position=position, type_label=type_label)

    _CollectionTypeKind = typing.Literal[
        _TokenKind.ARRAY,
        _TokenKind.BAG,
        _TokenKind.LIST,
        _TokenKind.SET,
    ]
    _COLLECTION_TYPE_KIND_SET: FrozenSet[_CollectionTypeKind] = frozenset(
        get_args(_CollectionTypeKind)
    )

    _SimpleTypeKind = typing.Literal[
        _TokenKind.BINARY,
        _TokenKind.BOOLEAN,
        _TokenKind.INTEGER,
        _TokenKind.LOGICAL,
        _TokenKind.NUMBER,
        _TokenKind.REAL,
        _TokenKind.STRING,
    ]
    _SIMPLE_TYPE_KIND_SET: FrozenSet[_SimpleTypeKind] = frozenset(
        get_args(_SimpleTypeKind)
    )

    _CollectionTypeSelectionKind = typing.Literal[
        _CollectionTypeKind, _TokenKind.IDENTIFIER, _SimpleTypeKind, _TokenKind.GENERIC
    ]
    _COLLECTION_TYPE_SELECTION_KIND_SET: FrozenSet[_CollectionTypeSelectionKind] = (
        frozenset(get_args(_CollectionTypeSelectionKind))
    )

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_collection_type_selection(self) -> Optional[CollectionTypeSelection]:
        if len(self.errors) > 0:
            return None

        token = self._tape.token()
        if token is None:
            self._emit_error(
                "Expected a collection type selection, but got the end of input"
            )
            return None

        if not is_literal_in(token.kind, _Parser._COLLECTION_TYPE_SELECTION_KIND_SET):
            self._emit_error(
                f"Expected a collection type selection, "
                f"but got a token {token.kind.name}: {token.text!r}"
            )
            return None

        if is_literal_in(token.kind, _Parser._COLLECTION_TYPE_KIND_SET):
            return self._parse_collection_type()

        elif token.kind is _TokenKind.IDENTIFIER:
            return self._parse_named_type()

        elif is_literal_in(token.kind, _Parser._SIMPLE_TYPE_KIND_SET):
            return self._parse_simple_type()

        elif token.kind is _TokenKind.GENERIC:
            return self._parse_generic_type()

        else:
            # NOTE (mristin):
            # As of 2025-09-24, mypy does not support type substraction, so we have to
            # rise an assertion error ourselves. In the future, we can simply state
            # ``assert_never(token.kind)`` here for exhaustive matching.
            raise AssertionError(f"Unhandled {token.kind=}")

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_collection_type(self) -> Optional[CollectionType]:
        if len(self.errors) > 0:
            return None

        token = self._tape.token()
        if token is None:
            self._emit_error("Expected a collection type, but got the end of input")
            return None

        if not is_literal_in(token.kind, _Parser._COLLECTION_TYPE_KIND_SET):
            self._emit_error(
                f"Expected a collection type, "
                f"but got a token {token.kind.name}: {token.text!r}"
            )
            return None

        # noinspection PyUnreachableCode
        if token.kind is _TokenKind.ARRAY:
            return self._parse_array_type()

        elif token.kind is _TokenKind.BAG:
            return self._parse_bag_type()

        elif token.kind is _TokenKind.LIST:
            return self._parse_list_type()

        elif token.kind is _TokenKind.SET:
            return self._parse_set_type()
        else:
            # noinspection PyUnreachableCode
            assert_never(token.kind)

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_simple_type(self) -> Optional[SimpleType]:
        if len(self.errors) > 0:
            return None

        token = self._peek_in_kind_set(_Parser._SIMPLE_TYPE_KIND_SET)
        if token is None:
            return None

        assert is_literal_in(token.kind, _Parser._SIMPLE_TYPE_KIND_SET)

        # noinspection PyUnreachableCode
        if token.kind is _TokenKind.BINARY:
            return self._parse_binary_type()

        elif token.kind is _TokenKind.BOOLEAN:
            return self._parse_boolean_type()

        elif token.kind is _TokenKind.INTEGER:
            return self._parse_integer_type()

        elif token.kind is _TokenKind.LOGICAL:
            return self._parse_logical_type()

        elif token.kind is _TokenKind.NUMBER:
            return self._parse_number_type()

        elif token.kind is _TokenKind.REAL:
            return self._parse_real_type()

        elif token.kind is _TokenKind.STRING:
            return self._parse_string_type()

        else:
            # noinspection PyUnreachableCode
            assert_never(token.kind)

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_array_type(self) -> Optional[ArrayType]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.ARRAY)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        bound_spec = self._parse_bound_spec()
        if bound_spec is None:
            return None

        if self._nibble_kind(_TokenKind.OF) is None:
            return None

        optional = False
        if self._peek_kind(_TokenKind.OPTIONAL) is not None:
            self._tape.move_by(1)
            optional = True

        unique = False
        if self._peek_kind(_TokenKind.UNIQUE) is not None:
            self._tape.move_by(1)
            unique = True

        collection_type_selection = self._parse_collection_type_selection()
        if collection_type_selection is None:
            return None

        return ArrayType(
            position=position,
            bound_spec=bound_spec,
            optional=optional,
            unique=unique,
            of=collection_type_selection,
        )

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_bag_type(self) -> Optional[BagType]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.BAG)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        bound_spec = None  # type: Optional[BoundSpec]
        if self._peek_kind(_TokenKind.LSQ):
            bound_spec = self._parse_bound_spec()
            if bound_spec is None:
                return None

        if self._nibble_kind(_TokenKind.OF) is None:
            return None

        collection_type_selection = self._parse_collection_type_selection()
        if collection_type_selection is None:
            return None

        return BagType(
            position=position, bound_spec=bound_spec, of=collection_type_selection
        )

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_list_type(self) -> Optional[ListType]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.LIST)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        bound_spec = None  # type: Optional[BoundSpec]
        if self._peek_kind(_TokenKind.LSQ):
            bound_spec = self._parse_bound_spec()
            if bound_spec is None:
                return None

        if self._nibble_kind(_TokenKind.OF) is None:
            return None

        unique = False
        if self._peek_kind(_TokenKind.UNIQUE) is not None:
            self._tape.move_by(1)
            unique = True

        collection_type_selection = self._parse_collection_type_selection()
        if collection_type_selection is None:
            return None

        return ListType(
            position=position,
            bound_spec=bound_spec,
            unique=unique,
            of=collection_type_selection,
        )

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_set_type(self) -> Optional[SetType]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.SET)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        bound_spec = None  # type: Optional[BoundSpec]
        if self._peek_kind(_TokenKind.LSQ):
            bound_spec = self._parse_bound_spec()
            if bound_spec is None:
                return None

        if self._nibble_kind(_TokenKind.OF) is None:
            return None

        collection_type_selection = self._parse_collection_type_selection()
        if collection_type_selection is None:
            return None

        return SetType(
            position=position, bound_spec=bound_spec, of=collection_type_selection
        )

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_enum_type(self) -> Optional[EnumType]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.ENUMERATION)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        if self._nibble_kind(_TokenKind.OF) is None:
            return None

        if self._nibble_kind(_TokenKind.LPAR) is None:
            return None

        token = self._nibble_kind(_TokenKind.IDENTIFIER)
        if token is None:
            return None

        values = [Identifier(token.text)]  # type: List[Identifier]

        while True:
            token = self._tape.token()

            if token is None:
                self._emit_error(
                    "Unexpected end of input while parsing enumeration type"
                )
                return None

            elif token.kind is _TokenKind.RPAR:
                self._tape.move_by(1)
                self._last_parsed_token = token
                break

            elif token.kind is _TokenKind.COMMA:
                self._tape.move_by(1)

                token = self._nibble_kind(_TokenKind.IDENTIFIER)
                if token is None:
                    return None

                values.append(Identifier(token.text))

            else:
                self._emit_error(
                    f"Unexpected token {token.kind} while parsing "
                    f"enumeration type: {token.text}"
                )
                return None

        return EnumType(position=position, values=values)

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_select_type(self) -> Optional[SelectType]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.SELECT)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        if self._nibble_kind(_TokenKind.LPAR) is None:
            return None

        first_value = self._parse_named_type()
        if first_value is None:
            return None

        values = [first_value]  # type: List[NamedType]

        while True:
            token = self._tape.token()

            if token is None:
                self._emit_error("Unexpected end of input while parsing select type")

            elif token.kind is _TokenKind.RPAR:
                self._tape.move_by(1)
                self._last_parsed_token = token
                break

            elif token.kind is _TokenKind.COMMA:
                self._tape.move_by(1)

                value = self._parse_named_type()
                if value is None:
                    return None

                values.append(value)

            else:
                self._emit_error(
                    f"Unexpected token {token.kind} while parsing "
                    f"select type: {token.text}"
                )
                return None

        return SelectType(position=position, values=values)

    _TypeSelectionKind = typing.Literal[
        _CollectionTypeKind,
        # For named type
        _TokenKind.IDENTIFIER,
        _SimpleTypeKind,
        # For enum type
        _TokenKind.ENUMERATION,
        # For select type
        _TokenKind.SELECT,
    ]
    _TYPE_SELECTION_KIND_SET: FrozenSet[_TypeSelectionKind] = frozenset(
        get_args(_TypeSelectionKind)
    )

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_type_selection(self) -> Optional[TypeSelection]:
        if len(self.errors) > 0:
            return None

        token = self._tape.token()
        if token is None:
            self._emit_error("Unexpected end of input while parsing type selection")
            return None

        if not is_literal_in(token.kind, _Parser._TYPE_SELECTION_KIND_SET):
            self._emit_error(
                f"Unexpected token {token.kind.name} "
                f"while parsing type selection: {token.text}"
            )
            return None

        if is_literal_in(token.kind, _Parser._COLLECTION_TYPE_KIND_SET):
            return self._parse_collection_type()

        elif token.kind is _TokenKind.IDENTIFIER:
            return self._parse_named_type()

        elif is_literal_in(token.kind, _Parser._SIMPLE_TYPE_KIND_SET):
            return self._parse_simple_type()

        elif token.kind is _TokenKind.ENUMERATION:
            return self._parse_enum_type()

        elif token.kind is _TokenKind.SELECT:
            return self._parse_select_type()

        else:
            # NOTE (mristin):
            # As of 2025-09-24, mypy does not support type substraction, so we have to
            # rise an assertion error ourselves. In the future, we can simply state
            # ``assert_never(token.kind)`` here for exhaustive matching.
            raise AssertionError(f"Unhandled {token.kind=}")

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_import_item(self) -> Optional[ImportItem]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.IDENTIFIER)
        if token is None:
            return None

        position = _Parser._position_from_token(token)
        reference = Identifier(token.text)

        last_parsed_token = token

        alias: Optional[Identifier] = None
        if self._peek_kind(_TokenKind.AS) is not None:
            self._tape.move_by(1)

            token = self._nibble_kind(_TokenKind.IDENTIFIER)
            if token is None:
                return None

            alias = Identifier(token.text)
            last_parsed_token = token

        self._last_parsed_token = last_parsed_token
        return ImportItem(position=position, reference=reference, alias=alias)

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_reference_clause(self) -> Optional[ReferenceClause]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.REFERENCE)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        if self._nibble_kind(_TokenKind.FROM) is None:
            return None

        token = self._nibble_kind(_TokenKind.IDENTIFIER)
        if token is None:
            return None

        schema_ref = Identifier(token.text)

        import_list: List[ImportItem] = []

        if self._peek_kind(_TokenKind.LPAR) is not None:
            self._tape.move_by(1)

            first_item = self._parse_import_item()
            if first_item is None:
                return None

            import_list.append(first_item)

            while True:
                if self._peek_kind(_TokenKind.RPAR) is not None:
                    self._tape.move_by(1)
                    break

                if self._nibble_kind(_TokenKind.COMMA) is None:
                    return None

                import_item = self._parse_import_item()
                if import_item is None:
                    return None

                import_list.append(import_item)

        token = self._nibble_kind(_TokenKind.SEMI)
        if token is None:
            return None

        self._last_parsed_token = token
        return ReferenceClause(
            position=position, schema_ref=schema_ref, import_list=import_list
        )

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_use_item(self) -> Optional[UseItem]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.IDENTIFIER)
        if token is None:
            return None

        position = _Parser._position_from_token(token)
        reference = Identifier(token.text)

        last_parsed_token = token

        alias: Optional[Identifier] = None
        if self._peek_kind(_TokenKind.AS) is not None:
            self._tape.move_by(1)

            token = self._nibble_kind(_TokenKind.IDENTIFIER)
            if token is None:
                return None

            alias = Identifier(token.text)
            last_parsed_token = token

        self._last_parsed_token = last_parsed_token
        return UseItem(position=position, reference=reference, alias=alias)

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_use_clause(self) -> Optional[UseClause]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.USE)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        if self._nibble_kind(_TokenKind.FROM) is None:
            return None

        token = self._nibble_kind(_TokenKind.IDENTIFIER)
        if token is None:
            return None

        schema_ref = Identifier(token.text)

        use_list: List[UseItem] = []

        if self._peek_kind(_TokenKind.LPAR) is not None:
            self._tape.move_by(1)

            first_item = self._parse_use_item()
            if first_item is None:
                return None

            use_list.append(first_item)

            while True:
                if self._peek_kind(_TokenKind.RPAR) is not None:
                    self._tape.move_by(1)
                    break

                if self._nibble_kind(_TokenKind.COMMA) is None:
                    return None

                use_item = self._parse_use_item()
                if use_item is None:
                    return None

                use_list.append(use_item)

        token = self._nibble_kind(_TokenKind.SEMI)
        if token is None:
            return None

        self._last_parsed_token = token
        return UseClause(position=position, schema_ref=schema_ref, use_list=use_list)

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_constant_definition(self) -> Optional[ConstantDefinition]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.IDENTIFIER)
        if token is None:
            return None

        position = _Parser._position_from_token(token)
        identifier = Identifier(token.text)

        if self._nibble_kind(_TokenKind.COLON) is None:
            return None

        type_selection = self._parse_collection_type_selection()
        if type_selection is None:
            return None

        if self._nibble_kind(_TokenKind.COLON_EQ) is None:
            return None

        init = self._parse_expr()
        if init is None:
            return None

        token = self._nibble_kind(_TokenKind.SEMI)
        if token is None:
            return None

        self._last_parsed_token = token
        return ConstantDefinition(
            position=position,
            identifier=identifier,
            type_selection=type_selection,
            init=init,
        )

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_constant_declaration(self) -> Optional[List[ConstantDefinition]]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.CONSTANT)
        if token is None:
            return None

        const_defs = []  # type: List[ConstantDefinition]

        while True:
            if self._peek_kind(_TokenKind.END_CONSTANT) is not None:
                break

            const_def = self._parse_constant_definition()
            if const_def is None:
                return None

            const_defs.append(const_def)

        token = self._nibble_kind(_TokenKind.END_CONSTANT)
        if token is None:
            return None

        token = self._nibble_kind(_TokenKind.SEMI)
        if token is None:
            return None

        self._last_parsed_token = token
        return const_defs

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_supertype_primary_expr(self) -> Optional[SupertypeExpr]:
        if len(self.errors) > 0:
            return None

        if (token := self._peek_kind(_TokenKind.IDENTIFIER)) is not None:
            self._tape.move_by(1)
            self._last_parsed_token = token

            return NameRef(
                position=_Parser._position_from_token(token),
                identifier=Identifier(token.text),
            )

        elif (token := self._peek_kind(_TokenKind.ONEOF)) is not None:
            position = _Parser._position_from_token(token)
            self._tape.move_by(1)

            if self._nibble_kind(_TokenKind.LPAR) is None:
                return None

            first_expr = self._parse_supertype_expr()
            if first_expr is None:
                return None

            supertype_exprs = [first_expr]  # type: List[SupertypeExpr]

            while True:
                if (token := self._peek_kind(_TokenKind.RPAR)) is not None:
                    self._tape.move_by(1)
                    self._last_parsed_token = token
                    break

                if self._nibble_kind(_TokenKind.COMMA) is None:
                    return None

                expr = self._parse_supertype_expr()
                if expr is None:
                    return None

                supertype_exprs.append(expr)

            return Choice(position=position, supertype_exprs=supertype_exprs)

        elif self._peek_kind(_TokenKind.LPAR) is not None:
            self._tape.move_by(1)

            expr = self._parse_supertype_expr()
            if expr is None:
                return None

            token = self._nibble_kind(_TokenKind.RPAR)
            if token is None:
                return None

            self._last_parsed_token = token
            return expr

        else:
            token = self._tape.token()
            if token is None:
                self._emit_error(
                    "Unexpected end of input when parsing "
                    "a supertype primary expression"
                )
            else:
                self._emit_error(
                    f"Unexpected token {token.kind.name!r} "
                    f"when parsing a supertype primary expression: {token.text!r}"
                )
            return None

    _SUPERTYPE_BINARY_OP_KIND_SET = frozenset([_TokenKind.AND, _TokenKind.ANDOR])

    _SUPERTYPE_BINARY_OP_FROM_KIND = {
        _TokenKind.AND: SupertypeBinaryOp.AND,
        _TokenKind.ANDOR: SupertypeBinaryOp.ANDOR,
    }

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_supertype_expr(self) -> Optional[SupertypeExpr]:
        if len(self.errors) > 0:
            return None

        result = self._parse_supertype_primary_expr()
        if result is None:
            return None

        while True:
            token = self._peek_in_kind_set(_Parser._SUPERTYPE_BINARY_OP_KIND_SET)
            if token is None:
                break

            op = _Parser._SUPERTYPE_BINARY_OP_FROM_KIND[token.kind]
            self._tape.move_by(1)

            right = self._parse_supertype_primary_expr()
            if right is None:
                return None

            result = SupertypeBinaryExpr(
                position=copy.copy(result.position), left=result, op=op, right=right
            )

        return result

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_supertype_declaration(self) -> Optional[SupertypeDeclaration]:
        """Parse a supertype declaration."""
        if len(self.errors) > 0:
            return None

        # fmt: off
        is_supertype_of = (
            (
                tokens := self._peek_kinds(
                    (_TokenKind.ABSTRACT, _TokenKind.SUPERTYPE, _TokenKind.OF)
                )
            ) is not None
            or (
                tokens := self._peek_kinds((_TokenKind.SUPERTYPE, _TokenKind.OF))
            ) is not None
        )
        # fmt: on

        if is_supertype_of:
            assert tokens is not None and len(tokens) > 0
            position = _Parser._position_from_token(tokens[0])

            abstract = False
            if self._peek_kind(_TokenKind.ABSTRACT) is not None:
                self._tape.move_by(1)
                abstract = True

            # NOTE (mristin):
            # We checked for this above in the condition of the if-statement,
            # so we assert the nibbles here.
            assert self._nibble_kind(_TokenKind.SUPERTYPE) is not None
            assert self._nibble_kind(_TokenKind.OF) is not None

            of = self._parse_supertype_expr()
            if of is None:
                return None

            return SupertypeOf(position=position, abstract=abstract, of=of)
        elif (
            tokens := self._peek_kinds((_TokenKind.ABSTRACT, _TokenKind.SUPERTYPE))
        ) is not None:
            assert len(tokens) == 2

            position = _Parser._position_from_token(tokens[0])
            self._tape.move_by(2)

            self._last_parsed_token = tokens[1]
            return AbstractSupertype(position=position)
        else:
            token = self._tape.token()
            if token is None:
                self._emit_error(
                    "Unexpected end of input while parsing supertype declaration"
                )
            else:
                self._emit_error(
                    f"Unexpected token {token.kind.name!r} while parsing "
                    f"supertype declaration: {token.text!r}"
                )
            return None

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_subtype_declaration(self) -> Optional[SubtypeDeclaration]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.SUBTYPE)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        if self._nibble_kind(_TokenKind.OF) is None:
            return None

        if self._nibble_kind(_TokenKind.LPAR) is None:
            return None

        token = self._nibble_kind(_TokenKind.IDENTIFIER)
        if token is None:
            return None

        of = [
            NameRef(
                position=_Parser._position_from_token(token),
                identifier=Identifier(token.text),
            )
        ]  # type: List[NameRef]

        while True:
            if (token := self._peek_kind(_TokenKind.RPAR)) is not None:
                self._tape.move_by(1)
                self._last_parsed_token = token
                break

            if self._nibble_kind(_TokenKind.COMMA) is None:
                return None

            token = self._nibble_kind(_TokenKind.IDENTIFIER)
            if token is None:
                return None

            of.append(
                NameRef(
                    position=_Parser._position_from_token(token),
                    identifier=Identifier(token.text),
                )
            )

        return SubtypeDeclaration(position=position, of=of)

    _ATTRIBUTE_REFERENCE_KIND_SET = frozenset([_TokenKind.IDENTIFIER, _TokenKind.SELF])

    @_affect_parsing_stack
    def _parse_attribute_reference(self) -> Optional[Expr]:
        if len(self.errors) > 0:
            return None

        token = self._tape.token()
        if token is None:
            self._emit_error(
                "Unexpected end of input while parsing an attribute reference"
            )
            return None

        if token.kind not in _Parser._ATTRIBUTE_REFERENCE_KIND_SET:
            self._emit_error(
                f"Unexpected token {token.kind.name!r} "
                f"while parsing an attribute reference: {token.text!r}"
            )
            return None

        return self._parse_expr()

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_explicit_definition(self) -> Optional[ExplicitAttributeDefinition]:
        if len(self.errors) > 0:
            return None

        first_attribute = self._parse_attribute_reference()
        if first_attribute is None:
            return None

        position = copy.copy(first_attribute.position)

        attributes = [first_attribute]  # type: List[Expr]

        while True:
            if self._peek_kind(_TokenKind.COLON) is not None:
                break

            if self._nibble_kind(_TokenKind.COMMA) is None:
                return None

            attribute = self._parse_attribute_reference()
            if attribute is None:
                return None

            attributes.append(attribute)

        if self._nibble_kind(_TokenKind.COLON) is None:
            return None

        optional = False
        if self._peek_kind(_TokenKind.OPTIONAL) is not None:
            self._tape.move_by(1)
            optional = True

        type_selection = self._parse_collection_type_selection()
        if type_selection is None:
            return None

        token = self._nibble_kind(_TokenKind.SEMI)
        if token is None:
            return None

        self._last_parsed_token = token
        return ExplicitAttributeDefinition(
            position=position,
            attributes=attributes,
            optional=optional,
            type_selection=type_selection,
        )

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_derived_attribute(self) -> Optional[DerivedAttribute]:
        if len(self.errors) > 0:
            return None

        attribute = self._parse_attribute_reference()
        if attribute is None:
            return None

        position = copy.copy(attribute.position)

        if self._nibble_kind(_TokenKind.COLON) is None:
            return None

        type_selection = self._parse_collection_type_selection()
        if type_selection is None:
            return None

        if self._nibble_kind(_TokenKind.COLON_EQ) is None:
            return None

        init = self._parse_expr()
        if init is None:
            return None

        token = self._nibble_kind(_TokenKind.SEMI)
        if token is None:
            return None

        self._last_parsed_token = token
        return DerivedAttribute(
            position=position,
            attribute=attribute,
            type_selection=type_selection,
            init=init,
        )

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_derive_clause(self) -> Optional[DeriveClause]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.DERIVE)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        derived_attributes = []  # type: List[DerivedAttribute]

        # Parse the first derived attribute (required)
        first_derived_attr = self._parse_derived_attribute()
        if first_derived_attr is None:
            return None

        derived_attributes.append(first_derived_attr)

        while True:
            # NOTE (mristin):
            # We check if we're at the end of the derive clause -- look ahead to see if
            # next token starts a new clause or ends the entity.
            if (
                self._peek_kind(_TokenKind.INVERSE) is not None
                or self._peek_kind(_TokenKind.UNIQUE) is not None
                or self._peek_kind(_TokenKind.WHERE) is not None
                or self._peek_kind(_TokenKind.END_ENTITY) is not None
                # NOTE (mristin):
                # We add this case to make this method testable so that you can
                # provide a snippet and have it parsed.
                or self._tape.token() is None
            ):
                break

            derived_attr = self._parse_derived_attribute()
            if derived_attr is None:
                return None

            derived_attributes.append(derived_attr)

        return DeriveClause(position=position, derived_attributes=derived_attributes)

    _InverseTypeKind = typing.Literal[_TokenKind.SET, _TokenKind.BAG]

    _INVERSE_TYPE_KIND_SET: FrozenSet[_InverseTypeKind] = frozenset(
        get_args(_InverseTypeKind)
    )

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_inverse_type(self) -> Optional[InverseType]:
        if len(self.errors) > 0:
            return None

        position: Optional[Position] = None
        kind: Optional[_Parser._InverseTypeKind] = None
        bound_spec: Optional[BoundSpec] = None

        if self._peek_in_kind_set(_Parser._INVERSE_TYPE_KIND_SET) is not None:
            token = self._nibble_in_kind_set(_Parser._INVERSE_TYPE_KIND_SET)
            if token is None:
                return None

            assert is_literal_in(token.kind, _Parser._INVERSE_TYPE_KIND_SET)

            kind = token.kind

            position = _Parser._position_from_token(token)

            bound_spec = None
            if self._peek_kind(_TokenKind.LSQ) is not None:
                bound_spec = self._parse_bound_spec()
                if bound_spec is None:
                    return None

            if self._nibble_kind(_TokenKind.OF) is None:
                return None

        token = self._nibble_kind(_TokenKind.IDENTIFIER)
        if token is None:
            return None

        entity_ref = Identifier(token.text)

        if position is None:
            position = _Parser._position_from_token(token)

        self._last_parsed_token = token

        # noinspection PyUnreachableCode
        if kind is None:
            return NameRef(position=position, identifier=entity_ref)
        elif kind is _TokenKind.SET:
            return InverseSet(
                position=position, bound_spec=bound_spec, entity=entity_ref
            )
        elif kind is _TokenKind.BAG:
            return InverseBag(
                position=position, bound_spec=bound_spec, entity=entity_ref
            )
        else:
            # noinspection PyUnreachableCode
            assert_never(kind)

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_inverse_definition(self) -> Optional[InverseDefinition]:
        if len(self.errors) > 0:
            return None

        attribute = self._parse_attribute_reference()
        if attribute is None:
            return None

        position = copy.copy(attribute.position)

        if self._nibble_kind(_TokenKind.COLON) is None:
            return None

        inverse_type = self._parse_inverse_type()
        if inverse_type is None:
            return None

        if self._nibble_kind(_TokenKind.FOR) is None:
            return None

        attribute_ref = self._parse_attribute_reference()
        if attribute_ref is None:
            return None

        token = self._nibble_kind(_TokenKind.SEMI)
        if token is None:
            return None

        self._last_parsed_token = token
        return InverseDefinition(
            position=position,
            attribute=attribute,
            inverse_type=inverse_type,
            attribute_ref=attribute_ref,
        )

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_inverse_clause(self) -> Optional[InverseClause]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.INVERSE)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        first_inverse_def = self._parse_inverse_definition()
        if first_inverse_def is None:
            return None

        inverses = [first_inverse_def]  # type: List[InverseDefinition]

        while True:
            if (
                self._peek_kind(_TokenKind.UNIQUE) is not None
                or self._peek_kind(_TokenKind.WHERE) is not None
                or self._peek_kind(_TokenKind.END_ENTITY) is not None
                # NOTE (mristin):
                # We add this condition to make this function testable even though
                # the end of input is unexpected in real schemas.
                or self._tape.token() is None
            ):
                break

            inverse_def = self._parse_inverse_definition()
            if inverse_def is None:
                return None

            inverses.append(inverse_def)

        return InverseClause(position=position, inverses=inverses)

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_unique_rule(self) -> Optional[UniqueRule]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.IDENTIFIER)
        if token is None:
            return None

        position = _Parser._position_from_token(token)
        label = Identifier(token.text)

        if self._nibble_kind(_TokenKind.COLON) is None:
            return None

        first_attribute = self._parse_attribute_reference()
        if first_attribute is None:
            return None

        attributes = [first_attribute]  # type: List[Expr]

        while True:
            if self._peek_kind(_TokenKind.SEMI):
                break

            if self._nibble_kind(_TokenKind.COMMA) is None:
                return None

            attribute = self._parse_attribute_reference()
            if attribute is None:
                return None

            attributes.append(attribute)

        token = self._nibble_kind(_TokenKind.SEMI)
        self._last_parsed_token = token

        return UniqueRule(position=position, label=label, attributes=attributes)

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_unique_rules(self) -> Optional[List[UniqueRule]]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.UNIQUE)
        if token is None:
            return None

        first_unique_rule = self._parse_unique_rule()
        if first_unique_rule is None:
            return None

        unique_rules = [first_unique_rule]  # type: List[UniqueRule]

        while True:
            # NOTE (mristin):
            # We check if we're at the end of the unique clause -- look ahead to see if
            # next token starts a new clause or ends the entity.
            if (
                self._peek_kind(_TokenKind.WHERE) is not None
                or self._peek_kind(_TokenKind.END_ENTITY) is not None
                # NOTE (mristin):
                # This allows us to test the function even though end of input is
                # unexpected in real schemas.
                or self._tape.token() is None
            ):
                break

            unique_rule = self._parse_unique_rule()
            if unique_rule is None:
                return None

            unique_rules.append(unique_rule)

        return unique_rules

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_domain_rule(self) -> Optional[DomainRule]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.IDENTIFIER)
        if token is None:
            return None

        position = _Parser._position_from_token(token)
        label = Identifier(token.text)

        if self._nibble_kind(_TokenKind.COLON) is None:
            return None

        expr = self._parse_expr()
        if expr is None:
            return None

        token = self._nibble_kind(_TokenKind.SEMI)
        if token is None:
            return None

        self._last_parsed_token = token

        return DomainRule(position=position, label=label, expr=expr)

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_entity_declaration(self) -> Optional[EntityDeclaration]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.ENTITY)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        token = self._nibble_kind(_TokenKind.IDENTIFIER)
        if token is None:
            return None

        identifier = Identifier(token.text)

        supertype_declaration = None  # type: Optional[SupertypeDeclaration]
        if (
            self._peek_kinds((_TokenKind.ABSTRACT, _TokenKind.SUPERTYPE)) is not None
            or self._peek_kind(_TokenKind.SUPERTYPE) is not None
        ):
            supertype_declaration = self._parse_supertype_declaration()
            if supertype_declaration is None:
                return None

        subtype_declaration = None  # type: Optional[SubtypeDeclaration]
        if self._peek_kind(_TokenKind.SUBTYPE) is not None:
            subtype_declaration = self._parse_subtype_declaration()
            if subtype_declaration is None:
                return None

        if self._nibble_kind(_TokenKind.SEMI) is None:
            return None

        explicit_clauses = []  # type: List[ExplicitAttributeDefinition]
        derive_clauses = []  # type: List[DeriveClause]
        inverse_clauses = []  # type: List[InverseClause]
        unique_rules = []  # type: List[UniqueRule]
        domain_rules = []  # type: List[DomainRule]

        while True:
            if self._peek_kind(_TokenKind.END_ENTITY) is not None:
                break

            elif (
                self._peek_kind(_TokenKind.IDENTIFIER) is not None
                or self._peek_kind(_TokenKind.SELF) is not None
            ):
                explicit_definition = self._parse_explicit_definition()
                if explicit_definition is None:
                    return None

                explicit_clauses.append(explicit_definition)

            elif self._peek_kind(_TokenKind.DERIVE) is not None:
                derive_clause = self._parse_derive_clause()
                if derive_clause is None:
                    return None

                derive_clauses.append(derive_clause)

            elif self._peek_kind(_TokenKind.INVERSE) is not None:
                inverse_clause = self._parse_inverse_clause()
                if inverse_clause is None:
                    return None

                inverse_clauses.append(inverse_clause)

            elif self._peek_kind(_TokenKind.UNIQUE) is not None:
                parsed_unique_rules = self._parse_unique_rules()
                if parsed_unique_rules is None:
                    return None

                unique_rules.extend(parsed_unique_rules)

            elif self._peek_kind(_TokenKind.WHERE) is not None:
                token = self._nibble_kind(_TokenKind.WHERE)
                if token is None:
                    return None

                while True:
                    # NOTE (mristin):
                    # We check if we're at the end of the where clause -- look ahead to
                    # see if next token ends the entity.
                    if self._peek_kind(_TokenKind.END_ENTITY) is not None:
                        break

                    domain_rule = self._parse_domain_rule()
                    if domain_rule is None:
                        return None

                    domain_rules.append(domain_rule)

            else:
                token = self._tape.token()
                if token is None:
                    self._emit_error(
                        "Unexpected end of input while parsing entity declaration"
                    )
                else:
                    self._emit_error(
                        f"Unexpected token {token.kind.name!r} "
                        f"while parsing entity declaration: {token.text!r}"
                    )
                return None

        token = self._nibble_kind(_TokenKind.END_ENTITY)
        if token is None:
            return None

        token = self._nibble_kind(_TokenKind.SEMI)
        if token is None:
            return None

        self._last_parsed_token = token
        return EntityDeclaration(
            position=position,
            identifier=identifier,
            supertype_declaration=supertype_declaration,
            subtype_declaration=subtype_declaration,
            explicit_clauses=explicit_clauses,
            derive_clauses=derive_clauses,
            inverse_clauses=inverse_clauses,
            unique_rules=unique_rules,
            domain_rules=domain_rules,
        )

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_type_declaration(self) -> Optional[TypeDeclaration]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.TYPE)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        token = self._nibble_kind(_TokenKind.IDENTIFIER)
        if token is None:
            return None

        identifier = Identifier(token.text)

        if self._nibble_kind(_TokenKind.EQ) is None:
            return None

        type_selection = self._parse_type_selection()
        if type_selection is None:
            return None

        if self._nibble_kind(_TokenKind.SEMI) is None:
            return None

        domain_rules = []  # type: List[DomainRule]

        if self._peek_kind(_TokenKind.WHERE):
            self._tape.move_by(1)

            first_domain_rule = self._parse_domain_rule()
            if first_domain_rule is None:
                return None

            domain_rules.append(first_domain_rule)

            while True:
                if self._peek_kind(_TokenKind.END_TYPE) is not None:
                    break

                domain_rule = self._parse_domain_rule()
                if domain_rule is None:
                    return None

                domain_rules.append(domain_rule)

        if self._nibble_kind(_TokenKind.END_TYPE) is None:
            return None

        token = self._nibble_kind(_TokenKind.SEMI)
        if token is None:
            return None

        self._last_parsed_token = token
        return TypeDeclaration(
            position=position,
            identifier=identifier,
            type_selection=type_selection,
            domain_rules=domain_rules,
        )

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_aggregate_type(self) -> Optional[AggregateType]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.AGGREGATE)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        label = None  # type: Optional[Identifier]
        if self._peek_kind(_TokenKind.COLON) is not None:
            self._tape.move_by(1)

            token = self._nibble_kind(_TokenKind.IDENTIFIER)
            if token is None:
                return None

            label = Identifier(token.text)

        if self._nibble_kind(_TokenKind.OF) is None:
            return None

        of_type = self._parse_parameter_type()
        if of_type is None:
            return None

        return AggregateType(position=position, label=label, of=of_type)

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_conformant_array_type(self) -> Optional[ConformantArrayType]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.ARRAY)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        bound_spec = None  # type: Optional[BoundSpec]
        if self._peek_kind(_TokenKind.LSQ):
            bound_spec = self._parse_bound_spec()
            if bound_spec is None:
                return None

        if self._nibble_kind(_TokenKind.OF) is None:
            return None

        optional = False
        if self._peek_kind(_TokenKind.OPTIONAL) is not None:
            self._tape.move_by(1)
            optional = True

        unique = False
        if self._peek_kind(_TokenKind.UNIQUE) is not None:
            self._tape.move_by(1)
            unique = True

        of_type = self._parse_parameter_type()
        if of_type is None:
            return None

        return ConformantArrayType(
            position=position,
            bound_spec=bound_spec,
            optional=optional,
            unique=unique,
            of=of_type,
        )

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_conformant_bag_type(self) -> Optional[ConformantBagType]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.BAG)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        bound_spec = None  # type: Optional[BoundSpec]
        if self._peek_kind(_TokenKind.LSQ):
            bound_spec = self._parse_bound_spec()
            if bound_spec is None:
                return None

        if self._nibble_kind(_TokenKind.OF) is None:
            return None

        of_type = self._parse_parameter_type()
        if of_type is None:
            return None

        return ConformantBagType(position=position, bound_spec=bound_spec, of=of_type)

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_conformant_list_type(self) -> Optional[ConformantListType]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.LIST)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        bound_spec = None  # type: Optional[BoundSpec]
        if self._peek_kind(_TokenKind.LSQ):
            bound_spec = self._parse_bound_spec()
            if bound_spec is None:
                return None

        if self._nibble_kind(_TokenKind.OF) is None:
            return None

        unique = False
        if self._peek_kind(_TokenKind.UNIQUE) is not None:
            self._tape.move_by(1)
            unique = True

        of_type = self._parse_parameter_type()
        if of_type is None:
            return None

        return ConformantListType(
            position=position, bound_spec=bound_spec, unique=unique, of=of_type
        )

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_conformant_set_type(self) -> Optional[ConformantSetType]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.SET)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        bound_spec = None  # type: Optional[BoundSpec]
        if self._peek_kind(_TokenKind.LSQ):
            bound_spec = self._parse_bound_spec()
            if bound_spec is None:
                return None

        if self._nibble_kind(_TokenKind.OF) is None:
            return None

        of_type = self._parse_parameter_type()
        if of_type is None:
            return None

        return ConformantSetType(position=position, bound_spec=bound_spec, of=of_type)

    _ParameterTypeKind = typing.Literal[
        # For AggregateType
        _TokenKind.AGGREGATE,
        # For ConformantType (ConformantArray, ConformantBag, ConformantList, ConformantSet)
        _TokenKind.ARRAY,
        _TokenKind.BAG,
        _TokenKind.LIST,
        _TokenKind.SET,
        # For SimpleType
        _TokenKind.BINARY,
        _TokenKind.BOOLEAN,
        _TokenKind.INTEGER,
        _TokenKind.LOGICAL,
        _TokenKind.NUMBER,
        _TokenKind.REAL,
        _TokenKind.STRING,
        # For NamedType
        _TokenKind.IDENTIFIER,
        # For GenericType
        _TokenKind.GENERIC,
    ]

    _PARAMETER_TYPE_KIND_SET: FrozenSet[_ParameterTypeKind] = frozenset(
        get_args(_ParameterTypeKind)
    )

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_parameter_type(self) -> Optional[ParameterType]:
        if len(self.errors) > 0:
            return None

        token = self._tape.token()
        if token is None:
            self._emit_error("Expected a parameter type, but got the end of input")
            return None

        if not is_literal_in(token.kind, _Parser._PARAMETER_TYPE_KIND_SET):
            self._emit_error(
                f"Expected a parameter type, "
                f"but got a token {token.kind.name}: {token.text!r}"
            )
            return None

        # AggregateType
        if token.kind is _TokenKind.AGGREGATE:
            return self._parse_aggregate_type()

        # ConformantType variants
        elif token.kind is _TokenKind.ARRAY:
            return self._parse_conformant_array_type()
        elif token.kind is _TokenKind.BAG:
            return self._parse_conformant_bag_type()
        elif token.kind is _TokenKind.LIST:
            return self._parse_conformant_list_type()
        elif token.kind is _TokenKind.SET:
            return self._parse_conformant_set_type()

        # SimpleType
        elif is_literal_in(token.kind, _Parser._SIMPLE_TYPE_KIND_SET):
            return self._parse_simple_type()

        # NamedType
        elif token.kind is _TokenKind.IDENTIFIER:
            return self._parse_named_type()

        # GenericType
        elif token.kind is _TokenKind.GENERIC:
            return self._parse_generic_type()

        else:
            # NOTE (mristin):
            # As of 2025-09-24, mypy does not support type substraction, so we have to
            # rise an assertion error ourselves. In the future, we can simply state
            # ``assert_never(token.kind)`` here for exhaustive matching.
            raise AssertionError(f"Unhandled {token.kind=}")

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_formal_parameter(self) -> Optional[FormalParameter]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.IDENTIFIER)
        if token is None:
            return None

        position = _Parser._position_from_token(token)
        identifiers = [Identifier(token.text)]  # type: List[Identifier]

        # Parse additional parameter identifiers separated by commas
        while True:
            if self._peek_kind(_TokenKind.COLON) is not None:
                break

            if self._nibble_kind(_TokenKind.COMMA) is None:
                return None

            token = self._nibble_kind(_TokenKind.IDENTIFIER)
            if token is None:
                return None

            identifiers.append(Identifier(token.text))

        if self._nibble_kind(_TokenKind.COLON) is None:
            return None

        of_type = self._parse_parameter_type()
        if of_type is None:
            return None

        return FormalParameter(
            position=position, identifiers=identifiers, of_type=of_type
        )

    _DeclarationKind = typing.Literal[
        _TokenKind.ENTITY,
        _TokenKind.TYPE,
        _TokenKind.FUNCTION,
        _TokenKind.PROCEDURE,
    ]

    _DECLARATION_KIND_SET: FrozenSet[_DeclarationKind] = frozenset(
        get_args(_DeclarationKind)
    )

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_declaration(self) -> Optional[Declaration]:
        if len(self.errors) > 0:
            return None

        token = self._tape.token()
        if token is None:
            self._emit_error("Expected a declaration, but got end of input")
            return None

        if not is_literal_in(token.kind, _Parser._DECLARATION_KIND_SET):
            expected_kinds = ", ".join(
                sorted(kind.name for kind in _Parser._DECLARATION_KIND_SET)
            )
            self._emit_error(
                f"Expected a declaration ({expected_kinds}), "
                f"but got token {token.kind.name!r}: {token.text!r}"
            )
            return None

        assert is_literal_in(token.kind, _Parser._DECLARATION_KIND_SET)

        if token.kind is _TokenKind.ENTITY:
            return self._parse_entity_declaration()

        elif token.kind is _TokenKind.TYPE:
            return self._parse_type_declaration()

        elif token.kind is _TokenKind.FUNCTION:
            return self._parse_function_declaration()

        elif token.kind is _TokenKind.PROCEDURE:
            return self._parse_procedure_declaration()

        else:
            # noinspection PyUnreachableCode
            assert_never(token.kind)

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_local_variable_definition(self) -> Optional[LocalVariableDefinition]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.IDENTIFIER)
        if token is None:
            return None

        position = _Parser._position_from_token(token)
        identifiers = [Identifier(token.text)]  # type: List[Identifier]

        while True:
            if self._peek_kind(_TokenKind.COLON) is not None:
                break

            if self._nibble_kind(_TokenKind.COMMA) is None:
                return None

            token = self._nibble_kind(_TokenKind.IDENTIFIER)
            if token is None:
                return None

            identifiers.append(Identifier(token.text))

        if self._nibble_kind(_TokenKind.COLON) is None:
            return None

        of_type = self._parse_parameter_type()
        if of_type is None:
            return None

        init = None  # type: Optional[Expr]
        if self._peek_kind(_TokenKind.COLON_EQ) is not None:
            self._tape.move_by(1)

            init = self._parse_expr()
            if init is None:
                return None

        token = self._nibble_kind(_TokenKind.SEMI)
        if token is None:
            return None

        self._last_parsed_token = token
        return LocalVariableDefinition(
            position=position, identifiers=identifiers, of_type=of_type, init=init
        )

    @_affect_parsing_stack
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_local_declaration(self) -> Optional[List[LocalVariableDefinition]]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.LOCAL)
        if token is None:
            return None

        local_variable_definitions = []  # type: List[LocalVariableDefinition]

        while True:
            if self._peek_kind(_TokenKind.END_LOCAL) is not None:
                break

            local_var_def = self._parse_local_variable_definition()
            if local_var_def is None:
                return None

            local_variable_definitions.append(local_var_def)

        token = self._nibble_kind(_TokenKind.END_LOCAL)
        if token is None:
            return None

        token = self._nibble_kind(_TokenKind.SEMI)
        if token is None:
            return None

        self._last_parsed_token = token
        return local_variable_definitions

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_alias_stmt(self) -> Optional[AliasStmt]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.ALIAS)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        token = self._nibble_kind(_TokenKind.IDENTIFIER)
        if token is None:
            return None

        variable = Identifier(token.text)

        if self._nibble_kind(_TokenKind.FOR) is None:
            return None

        target = self._parse_expr()
        if target is None:
            return None

        if self._nibble_kind(_TokenKind.SEMI) is None:
            return None

        body = []  # type: List["Stmt"]

        while True:
            if self._peek_kind(_TokenKind.END_ALIAS) is not None:
                break

            stmt = self._parse_stmt()
            if stmt is None:
                return None

            body.append(stmt)

        if self._nibble_kind(_TokenKind.END_ALIAS) is None:
            return None

        token = self._nibble_kind(_TokenKind.SEMI)
        if token is None:
            return None

        self._last_parsed_token = token
        return AliasStmt(position=position, variable=variable, target=target, body=body)

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_case_stmt(self) -> Optional["CaseStmt"]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.CASE)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        selector = self._parse_expr()
        if selector is None:
            return None

        if self._nibble_kind(_TokenKind.OF) is None:
            return None

        case_actions = []  # type: List[CaseAction]

        while True:
            # NOTE (mristin):
            # We check if we're at the end of case actions.
            if (
                self._peek_kind(_TokenKind.OTHERWISE) is not None
                or self._peek_kind(_TokenKind.END_CASE) is not None
            ):
                break

            first_label = self._parse_expr()
            if first_label is None:
                return None

            labels = [first_label]  # type: List[Expr]

            while True:
                if self._peek_kind(_TokenKind.COLON) is not None:
                    break

                if self._nibble_kind(_TokenKind.COMMA) is None:
                    return None

                label = self._parse_expr()
                if label is None:
                    return None

                labels.append(label)

            if self._nibble_kind(_TokenKind.COLON) is None:
                return None

            stmt = self._parse_stmt()
            if stmt is None:
                return None

            case_actions.append(
                CaseAction(
                    position=copy.copy(first_label.position), labels=labels, stmt=stmt
                )
            )

        # Parse optional OTHERWISE clause
        otherwise = None  # type: Optional["Stmt"]
        if self._peek_kind(_TokenKind.OTHERWISE) is not None:
            self._tape.move_by(1)

            if self._nibble_kind(_TokenKind.COLON) is None:
                return None

            otherwise = self._parse_stmt()
            if otherwise is None:
                return None

            # Consume optional semicolon after otherwise action
            if self._peek_kind(_TokenKind.SEMI) is not None:
                self._tape.move_by(1)

        token = self._nibble_kind(_TokenKind.END_CASE)
        if token is None:
            return None

        token = self._nibble_kind(_TokenKind.SEMI)
        if token is None:
            return None

        self._last_parsed_token = token
        return CaseStmt(
            position=position,
            selector=selector,
            actions=case_actions,
            otherwise=otherwise,
        )

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_compound_stmt(self) -> Optional[CompoundStmt]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.BEGIN)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        stmts = []  # type: List["Stmt"]

        while True:
            if self._peek_kind(_TokenKind.END) is not None:
                break

            stmt = self._parse_stmt()
            if stmt is None:
                return None

            stmts.append(stmt)

        token = self._nibble_kind(_TokenKind.END)
        if token is None:
            return None

        token = self._nibble_kind(_TokenKind.SEMI)
        if token is None:
            return None

        self._last_parsed_token = token
        return CompoundStmt(position=position, stmts=stmts)

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_escape_stmt(self) -> Optional[EscapeStmt]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.ESCAPE)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        token = self._nibble_kind(_TokenKind.SEMI)
        if token is None:
            return None

        self._last_parsed_token = token
        return EscapeStmt(position=position)

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_if_stmt(self) -> Optional[IfStmt]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.IF)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        condition = self._parse_expr()
        if condition is None:
            return None

        if self._nibble_kind(_TokenKind.THEN) is None:
            return None

        then_stmts = []  # type: List["Stmt"]

        # NOTE (mristin):
        # We parse then-statements until ELSE or END_IF
        while True:
            if (
                self._peek_kind(_TokenKind.ELSE) is not None
                or self._peek_kind(_TokenKind.END_IF) is not None
            ):
                break

            stmt = self._parse_stmt()
            if stmt is None:
                return None

            then_stmts.append(stmt)

        or_else_stmts = []  # type: List["Stmt"]
        if self._peek_kind(_TokenKind.ELSE) is not None:
            self._tape.move_by(1)

            # NOTE (mristin):
            # We parse else-statements until END_IF.
            while True:
                if self._peek_kind(_TokenKind.END_IF) is not None:
                    break

                stmt = self._parse_stmt()
                if stmt is None:
                    return None

                or_else_stmts.append(stmt)

        token = self._nibble_kind(_TokenKind.END_IF)
        if token is None:
            return None

        token = self._nibble_kind(_TokenKind.SEMI)
        if token is None:
            return None

        self._last_parsed_token = token
        return IfStmt(
            position=position,
            condition=condition,
            then=then_stmts,
            or_else=or_else_stmts,
        )

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_null_stmt(self) -> Optional[NullStmt]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.SEMI)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        self._last_parsed_token = token
        return NullStmt(position=position)

    @_affect_parsing_stack
    def _parse_repeat_control(self) -> Optional[RepeatControl]:
        if len(self.errors) > 0:
            return None

        old_last_parsed_token = self._last_parsed_token

        first_token = self._tape.token()
        if first_token is None:
            self._emit_error("Expected repeat control structure, but got end of input")
            return None

        position = _Parser._position_from_token(first_token)

        increment_control = None  # type: Optional[IncrementControl]

        # NOTE (mristin):
        # We check for increment control: ``identifier := expr TO expr [BY expr]``
        if self._peek_kinds((_TokenKind.IDENTIFIER, _TokenKind.COLON_EQ)) is not None:
            var_token = self._nibble_kind(_TokenKind.IDENTIFIER)
            if var_token is None:
                return None

            variable = Identifier(var_token.text)
            increment_position = _Parser._position_from_token(var_token)

            if self._nibble_kind(_TokenKind.COLON_EQ) is None:
                return None

            bound_1 = self._parse_expr()
            if bound_1 is None:
                return None

            if self._nibble_kind(_TokenKind.TO) is None:
                return None

            bound_2 = self._parse_expr()
            if bound_2 is None:
                return None

            increment = None  # type: Optional[Expr]
            if self._peek_kind(_TokenKind.BY) is not None:
                self._tape.move_by(1)
                increment = self._parse_expr()
                if increment is None:
                    return None

            increment_control = IncrementControl(
                position=increment_position,
                variable=variable,
                bound_1=bound_1,
                bound_2=bound_2,
                increment=increment,
            )

        while_control = None  # type: Optional[Expr]
        if self._peek_kind(_TokenKind.WHILE) is not None:
            self._tape.move_by(1)
            while_control = self._parse_expr()
            if while_control is None:
                return None

        until_control = None  # type: Optional[Expr]
        if self._peek_kind(_TokenKind.UNTIL) is not None:
            self._tape.move_by(1)
            until_control = self._parse_expr()
            if until_control is None:
                return None

        assert not (
            increment_control is not None
            or while_control is not None
            or until_control is not None
        ) or (
            self._last_parsed_token != old_last_parsed_token
        ), "Last parsed token must move if anything parsed."

        return RepeatControl(
            position=position,
            increment_control=increment_control,
            while_control=while_control,
            until_control=until_control,
        )

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_repeat_stmt(self) -> Optional[RepeatStmt]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.REPEAT)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        control = self._parse_repeat_control()
        if control is None:
            return None

        if self._nibble_kind(_TokenKind.SEMI) is None:
            return None

        body = []  # type: List["Stmt"]

        while True:
            if self._peek_kind(_TokenKind.END_REPEAT) is not None:
                break

            stmt = self._parse_stmt()
            if stmt is None:
                return None

            body.append(stmt)

        if self._nibble_kind(_TokenKind.END_REPEAT) is None:
            return None

        token = self._nibble_kind(_TokenKind.SEMI)
        if token is None:
            return None

        self._last_parsed_token = token
        return RepeatStmt(position=position, control=control, body=body)

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_return_stmt(self) -> Optional[ReturnStmt]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.RETURN)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        value = None  # type: Optional[Expr]
        if self._peek_kind(_TokenKind.SEMI) is None:
            value = self._parse_expr()
            if value is None:
                return None

        token = self._nibble_kind(_TokenKind.SEMI)
        if token is None:
            return None

        self._last_parsed_token = token
        return ReturnStmt(position=position, value=value)

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_skip_stmt(self) -> Optional[SkipStmt]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.SKIP)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        token = self._nibble_kind(_TokenKind.SEMI)
        if token is None:
            return None

        self._last_parsed_token = token
        return SkipStmt(position=position)

    _StmtKind = typing.Literal[
        _TokenKind.ALIAS,
        _TokenKind.CASE,
        _TokenKind.BEGIN,
        _TokenKind.ESCAPE,
        _TokenKind.IF,
        _TokenKind.REPEAT,
        _TokenKind.RETURN,
        _TokenKind.SKIP,
        _TokenKind.SEMI,
        _TokenKind.IDENTIFIER,
    ]

    _STMT_KIND_SET: FrozenSet[_StmtKind] = frozenset(get_args(_StmtKind))

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_stmt(self) -> Optional[Stmt]:
        if len(self.errors) > 0:
            return None

        token = self._tape.token()
        if token is None:
            self._emit_error("Expected a statement, but got end of input")
            return None

        if not is_literal_in(token.kind, _Parser._STMT_KIND_SET):
            self._emit_error(
                f"Unexpected token {token.kind.name!r} "
                f"while parsing statement: {token.text!r}"
            )
            return None

        if token.kind is _TokenKind.ALIAS:
            return self._parse_alias_stmt()

        elif token.kind is _TokenKind.CASE:
            return self._parse_case_stmt()

        elif token.kind is _TokenKind.BEGIN:
            return self._parse_compound_stmt()

        elif token.kind is _TokenKind.ESCAPE:
            return self._parse_escape_stmt()

        elif token.kind is _TokenKind.IF:
            return self._parse_if_stmt()

        elif token.kind is _TokenKind.REPEAT:
            return self._parse_repeat_stmt()

        elif token.kind is _TokenKind.RETURN:
            return self._parse_return_stmt()

        elif token.kind is _TokenKind.SKIP:
            return self._parse_skip_stmt()

        elif token.kind is _TokenKind.SEMI:
            return self._parse_null_stmt()

        elif token.kind is _TokenKind.IDENTIFIER:
            # NOTE (mristin):
            # This can be a procedure call or an assignment depending on what follows
            # the initial expression.

            position = _Parser._position_from_token(token)

            expr_token = token

            expr = self._parse_expr()
            if expr is None:
                return None

            if self._peek_kind(_TokenKind.COLON_EQ) is not None:
                # NOTE (mristin):
                # We have an assignment.
                self._tape.move_by(1)

                value = self._parse_expr()
                if value is None:
                    return None

                token = self._nibble_kind(_TokenKind.SEMI)
                if token is None:
                    return None

                self._last_parsed_token = token
                return AssignmentStmt(position=position, target=expr, value=value)
            else:
                token = self._nibble_kind(_TokenKind.SEMI)
                if token is None:
                    return None

                if isinstance(expr, Call):
                    self._last_parsed_token = token
                    return CallStmt(position=position, call=expr)
                else:
                    self._emit_error_at(
                        f"Unexpected expression; only call and assignment statements "
                        f"were expected in this context, "
                        f"but got {expr_token.kind.name!r}: {expr_token.text!r}",
                        expr_token,
                    )
                    return None
        else:
            # noinspection PyUnreachableCode
            assert_never(token.kind)

    @_affect_parsing_stack
    def _parse_algorithm_head(self) -> Optional[AlgorithmHead]:
        if len(self.errors) > 0:
            return None

        old_last_parsed_token = self._last_parsed_token

        # region Nested declarations
        declarations = []  # type: List[Declaration]

        while True:
            if self._peek_in_kind_set(_Parser._DECLARATION_KIND_SET) is not None:
                declaration = self._parse_declaration()
                if declaration is None:
                    return None

                declarations.append(declaration)
            else:
                break

        # endregion Nested declarations

        # region Constant declaration
        constant_definitions = []  # type: List[ConstantDefinition]
        if self._peek_kind(_TokenKind.CONSTANT) is not None:
            maybe_constant_definitions = self._parse_constant_declaration()
            if maybe_constant_definitions is None:
                return None

            constant_definitions = maybe_constant_definitions

        # endregion Constant declaration

        # region Local declaration
        local_variable_definitions = []  # type: List[LocalVariableDefinition]
        if self._peek_kind(_TokenKind.LOCAL) is not None:
            maybe_local_variable_definitions = self._parse_local_declaration()
            if maybe_local_variable_definitions is None:
                return None

            local_variable_definitions = maybe_local_variable_definitions

        # endregion Local declaration

        assert (
            not (
                len(declarations) > 0
                or len(constant_definitions) > 0
                or len(local_variable_definitions) > 0
            )
            or self._last_parsed_token is not old_last_parsed_token
        ), "Last parsed token moved if anything parsed."

        return AlgorithmHead(
            declarations=declarations,
            constant_definitions=constant_definitions,
            local_variable_definitions=local_variable_definitions,
        )

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_function_declaration(self) -> Optional[FunctionDeclaration]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.FUNCTION)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        token = self._nibble_kind(_TokenKind.IDENTIFIER)
        if token is None:
            return None

        # region Function head

        identifier = Identifier(token.text)

        if self._nibble_kind(_TokenKind.LPAR) is None:
            return None

        formal_parameters = []  # type: List[FormalParameter]

        # NOTE (mristin):
        # We check first if we have any parameters at all to simplify the code below.
        if self._peek_kind(_TokenKind.RPAR) is None:
            first_param = self._parse_formal_parameter()
            if first_param is None:
                return None

            formal_parameters.append(first_param)

            while True:
                if self._peek_kind(_TokenKind.RPAR) is not None:
                    break

                if self._nibble_kind(_TokenKind.SEMI) is None:
                    return None

                param = self._parse_formal_parameter()
                if param is None:
                    return None

                formal_parameters.append(param)

        if self._nibble_kind(_TokenKind.RPAR) is None:
            return None

        if self._nibble_kind(_TokenKind.COLON) is None:
            return None

        return_type = self._parse_parameter_type()
        if return_type is None:
            return None

        if self._nibble_kind(_TokenKind.SEMI) is None:
            return None

        # endregion Function head

        algorithm_head = self._parse_algorithm_head()
        if algorithm_head is None:
            return None

        # region Body statements
        body = []  # type: List[Stmt]

        while True:
            if self._peek_kind(_TokenKind.END_FUNCTION) is not None:
                break

            stmt = self._parse_stmt()
            if stmt is None:
                return None

            body.append(stmt)

        # endregion Body statements

        if self._nibble_kind(_TokenKind.END_FUNCTION) is None:
            return None

        token = self._nibble_kind(_TokenKind.SEMI)
        if token is None:
            return None

        self._last_parsed_token = token
        return FunctionDeclaration(
            position=position,
            identifier=identifier,
            formal_parameters=formal_parameters,
            return_type=return_type,
            head=algorithm_head,
            body=body,
        )

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_procedure_declaration(self) -> Optional[ProcedureDeclaration]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.PROCEDURE)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        token = self._nibble_kind(_TokenKind.IDENTIFIER)
        if token is None:
            return None

        # region Procedure head

        identifier = Identifier(token.text)

        if self._nibble_kind(_TokenKind.LPAR) is None:
            return None

        formal_parameters = []  # type: List[FormalParameter]

        # NOTE (mristin):
        # We check first if we have any parameters at all to simplify the code below.
        if self._peek_kind(_TokenKind.RPAR) is None:
            if self._peek_kind(_TokenKind.VAR) is not None:
                self._tape.move_by(1)

            first_param = self._parse_formal_parameter()
            if first_param is None:
                return None

            formal_parameters.append(first_param)

            while True:
                if self._peek_kind(_TokenKind.RPAR) is not None:
                    break

                if self._nibble_kind(_TokenKind.SEMI) is None:
                    return None

                if self._peek_kind(_TokenKind.VAR) is not None:
                    self._tape.move_by(1)

                param = self._parse_formal_parameter()
                if param is None:
                    return None

                formal_parameters.append(param)

        if self._nibble_kind(_TokenKind.RPAR) is None:
            return None

        if self._nibble_kind(_TokenKind.SEMI) is None:
            return None

        # endregion Procedure head

        algorithm_head = self._parse_algorithm_head()
        if algorithm_head is None:
            return None

        # region Body statements
        body = []  # type: List[Stmt]

        while True:
            if self._peek_kind(_TokenKind.END_PROCEDURE) is not None:
                break

            stmt = self._parse_stmt()
            if stmt is None:
                return None

            body.append(stmt)

        # endregion Body statements

        if self._nibble_kind(_TokenKind.END_PROCEDURE) is None:
            return None

        token = self._nibble_kind(_TokenKind.SEMI)
        if token is None:
            return None

        self._last_parsed_token = token
        return ProcedureDeclaration(
            position=position,
            identifier=identifier,
            formal_parameters=formal_parameters,
            head=algorithm_head,
            body=body,
        )

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def _parse_rule_declaration(self) -> Optional[RuleDeclaration]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.RULE)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        token = self._nibble_kind(_TokenKind.IDENTIFIER)
        if token is None:
            return None

        identifier = Identifier(token.text)

        if self._nibble_kind(_TokenKind.FOR) is None:
            return None

        if self._nibble_kind(_TokenKind.LPAR) is None:
            return None

        token = self._nibble_kind(_TokenKind.IDENTIFIER)
        if token is None:
            return None

        # region FOR entities
        for_entities = [Identifier(token.text)]  # type: List[Identifier]

        while True:
            if self._peek_kind(_TokenKind.RPAR) is not None:
                self._tape.move_by(1)
                break

            if self._nibble_kind(_TokenKind.COMMA) is None:
                return None

            token = self._nibble_kind(_TokenKind.IDENTIFIER)
            if token is None:
                return None

            for_entities.append(Identifier(token.text))

        if self._nibble_kind(_TokenKind.SEMI) is None:
            return None

        # endregion FOR entities

        algorithm_head = self._parse_algorithm_head()
        if algorithm_head is None:
            return None

        # region Body statements
        body = []  # type: List[Stmt]

        while True:
            if (
                self._peek_kind(_TokenKind.WHERE) is not None
                or self._peek_kind(_TokenKind.END_RULE) is not None
            ):
                break

            stmt = self._parse_stmt()
            if stmt is None:
                return None

            body.append(stmt)

        # endregion Body statements

        # region Where clause
        where = []  # type: List[DomainRule]

        if self._peek_kind(_TokenKind.WHERE) is not None:
            token = self._nibble_kind(_TokenKind.WHERE)
            if token is None:
                return None

            while True:
                # NOTE (mristin):
                # We check if we're at the end of the where clause -- look ahead to
                # see if next token ends the rule.
                if self._peek_kind(_TokenKind.END_RULE) is not None:
                    break

                domain_rule = self._parse_domain_rule()
                if domain_rule is None:
                    return None

                where.append(domain_rule)

        # endregion Where clause

        if self._nibble_kind(_TokenKind.END_RULE) is None:
            return None

        token = self._nibble_kind(_TokenKind.SEMI)
        if token is None:
            return None

        self._last_parsed_token = token
        return RuleDeclaration(
            position=position,
            identifier=identifier,
            for_entities=for_entities,
            head=algorithm_head,
            body=body,
            where=where,
        )

    _InterfaceSpecificationKind = typing.Literal[_TokenKind.REFERENCE, _TokenKind.USE]

    _INTERFACE_SPECIFICATION_KIND_SET: FrozenSet[_InterfaceSpecificationKind] = (
        frozenset(get_args(_InterfaceSpecificationKind))
    )

    @_affect_parsing_stack
    @_ensure_last_parsed_token_is_semi_on_success
    @_ensure_parse_result_coincides_with_last_parsed_token_and_errors
    def parse_schema(self) -> Optional[Schema]:
        if len(self.errors) > 0:
            return None

        token = self._nibble_kind(_TokenKind.SCHEMA)
        if token is None:
            return None

        position = _Parser._position_from_token(token)

        token = self._nibble_kind(_TokenKind.IDENTIFIER)
        if token is None:
            return None

        identifier = Identifier(token.text)

        if self._nibble_kind(_TokenKind.SEMI) is None:
            return None

        # Initialize collections for schema contents
        reference_clauses = []  # type: List[ReferenceClause]
        use_clauses = []  # type: List[UseClause]
        constant_definitions = []  # type: List[ConstantDefinition]
        entity_declarations = []  # type: List[EntityDeclaration]
        function_declarations = []  # type: List[FunctionDeclaration]
        procedure_declarations = []  # type: List[ProcedureDeclaration]
        type_declarations = []  # type: List[TypeDeclaration]
        rule_declarations = []  # type: List[RuleDeclaration]

        # region Interface specifications
        while True:
            if self._peek_kind(_TokenKind.REFERENCE) is not None:
                reference_clause = self._parse_reference_clause()
                if reference_clause is None:
                    return None
                reference_clauses.append(reference_clause)

            elif self._peek_kind(_TokenKind.USE) is not None:
                use_clause = self._parse_use_clause()
                if use_clause is None:
                    return None
                use_clauses.append(use_clause)

            else:
                break

        # endregion

        if self._peek_kind(_TokenKind.CONSTANT) is not None:
            maybe_constant_definitions = self._parse_constant_declaration()
            if maybe_constant_definitions is None:
                return None

            constant_definitions = maybe_constant_definitions

        # region Declarations

        while True:
            if self._peek_kind(_TokenKind.END_SCHEMA) is not None:
                break

            if self._peek_kind(_TokenKind.ENTITY) is not None:
                entity_declaration = self._parse_entity_declaration()
                if entity_declaration is None:
                    return None
                entity_declarations.append(entity_declaration)

            elif self._peek_kind(_TokenKind.TYPE) is not None:
                type_declaration = self._parse_type_declaration()
                if type_declaration is None:
                    return None
                type_declarations.append(type_declaration)

            elif self._peek_kind(_TokenKind.FUNCTION) is not None:
                function_declaration = self._parse_function_declaration()
                if function_declaration is None:
                    return None
                function_declarations.append(function_declaration)

            elif self._peek_kind(_TokenKind.PROCEDURE) is not None:
                procedure_declaration = self._parse_procedure_declaration()
                if procedure_declaration is None:
                    return None
                procedure_declarations.append(procedure_declaration)

            elif self._peek_kind(_TokenKind.RULE) is not None:
                rule_declaration = self._parse_rule_declaration()
                if rule_declaration is None:
                    return None
                rule_declarations.append(rule_declaration)

            else:
                token = self._tape.token()
                if token is None:
                    self._emit_error(
                        "Unexpected end of input while parsing schema body"
                    )
                else:
                    self._emit_error(
                        f"Unexpected token {token.kind.name!r} "
                        f"while parsing schema body: {token.text!r}"
                    )
                return None

        # endregion Declarations

        token = self._nibble_kind(_TokenKind.END_SCHEMA)
        if token is None:
            return None

        token = self._nibble_kind(_TokenKind.SEMI)
        if token is None:
            return None

        self._last_parsed_token = token
        return Schema(
            position=position,
            identifier=identifier,
            reference_clauses=reference_clauses,
            use_clauses=use_clauses,
            constant_definitions=constant_definitions,
            entity_declarations=entity_declarations,
            function_declarations=function_declarations,
            procedure_declarations=procedure_declarations,
            type_declarations=type_declarations,
            rule_declarations=rule_declarations,
        )


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def parse(text: str) -> Tuple[Optional[Schema], Optional[List[Error]]]:
    """Parse recursively the text as an Express schema."""
    tokens, ok = _lex(text)
    if not ok:
        if len(tokens) == 0:
            return None, [
                Error(message="Failed to tokenize the input at all", line=0, column=0)
            ]

        start = tokens[-1].start + len(tokens[-1].text)
        unlexed_tail = text[start : start + 20]

        return None, [
            Error(
                message=(
                    f"Failed to tokenize the input "
                    f"at {tokens[-1].position}: {unlexed_tail}"
                ),
                line=tokens[-1].position.lineno,
                column=tokens[-1].position.column,
            )
        ]

    tokens = [token for token in tokens if token.kind is not _TokenKind.COMMENT]

    tape = _TokenTape(tokens)
    parser = _Parser(tape=tape)

    schema = parser.parse_schema()

    if len(parser.errors) > 0:
        return None, parser.errors

    assert schema is not None
    return schema, None


# endregion Parse

# region Dumping
_I = "  "


def _indent_but_first_line(text: str, indention: str) -> str:
    """
    Indent all but the first of the given ``text`` by ``indention``.

    For example, this helps you insert indented blocks into formatted string literals.
    """
    indented_lines = []  # type: List[str]
    for i, line in enumerate(text.splitlines()):
        if i == 0:
            indented_lines.append(line)
        else:
            if len(line) > 0:
                indented_lines.append(indention + line)
            else:
                indented_lines.append(line)

    return "\n".join(indented_lines)


_DUMPABLE_PRIMITIVE = Union[
    Node,
    LogicalValue,
    AlgorithmHead,
    bytes,
    int,
    decimal.Decimal,
    str,
    enum.Enum,
    Position,
]
_DUMPABLE = Union[_DUMPABLE_PRIMITIVE, Sequence[_DUMPABLE_PRIMITIVE]]

_DUMPABLE_PRIMITIVE_AS_TUPLE = get_args(_DUMPABLE_PRIMITIVE)


def _dump_structure(that: Union[Node, AlgorithmHead]) -> str:
    """Translate the structure recursively into text."""
    annotations = collections.OrderedDict()

    for base in reversed(that.__class__.__mro__):
        if not hasattr(base, "__annotations__"):
            continue

        annotations.update(base.__annotations__)

    fields = []  # type: List[Tuple[Identifier, _DUMPABLE]]
    for name in annotations.keys():
        value = getattr(that, name, None)

        if value is not None:
            # noinspection PyTypeChecker
            fields.append((Identifier(name), value))

    return _structure_to_text(name=Identifier(that.__class__.__name__), fields=fields)


def _dump_position(that: Position) -> str:
    return str(that)


def _dump_literal(that: Union[LogicalValue, bytes, int, decimal.Decimal, str]) -> str:
    """Translate ``that`` literal to text."""
    if isinstance(that, decimal.Decimal):
        return str(that)
    elif isinstance(that, LogicalValue):
        return that.name
    elif isinstance(that, decimal.Decimal):
        return str(that)
    else:
        return repr(that)


def _dump_enum(that: enum.Enum) -> str:
    """Translate ``that`` enum literal to text."""
    return f"{that.__class__.__name__}.{that.name}"


def _dump_sequence(that: Sequence[_DUMPABLE_PRIMITIVE]) -> str:
    """Translate ``that`` sequence to text."""
    if len(that) == 0:
        return "[]"

    if len(that) == 1:
        return f"[{_dump(that[0])}]"
    else:
        dumped_parts_joined = ",\n".join(_dump(part) for part in that)

        return f"""\
[
{_I}{_indent_but_first_line(dumped_parts_joined, _I)}
]"""


def _structure_to_text(
    name: Identifier, fields: Sequence[Tuple[Identifier, _DUMPABLE]]
) -> str:
    """Translate the given structure to text."""
    if len(fields) == 0:
        return f"{name}()"

    field_parts = [
        f"{field_name}={_indent_but_first_line(_dump(field), _I)}"
        for field_name, field in fields
    ]

    field_parts_joined = ",\n".join(field_parts)

    return f"""{name}(
{_I}{_indent_but_first_line(field_parts_joined, _I)}
)"""


def _is_dumpable(value: Any) -> bool:
    if isinstance(value, _DUMPABLE_PRIMITIVE_AS_TUPLE):
        return True

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return all(isinstance(v, _DUMPABLE_PRIMITIVE_AS_TUPLE) for v in value)

    return False


def _dump(that: _DUMPABLE) -> str:
    """
    Translate ``that`` to text recursively.

    The unspecified properties (*i.e.*, ``None``) are omitted.
    """
    assert _is_dumpable(that), (
        f"Unexpected runtime type {type(that)} of something we want to dump: {that}; "
        f"expected only: {_DUMPABLE}"
    )

    # noinspection PyUnreachableCode
    if isinstance(that, (Node, AlgorithmHead)):
        return _dump_structure(that)
    elif isinstance(that, (LogicalValue, bytes, int, decimal.Decimal, str)):
        return _dump_literal(that)
    elif isinstance(that, enum.Enum):
        return _dump_enum(that)
    elif isinstance(that, Position):
        return _dump_position(that)
    elif isinstance(that, collections.abc.Sequence):
        return _dump_sequence(that)
    else:
        # noinspection PyUnreachableCode
        assert_never(that)


def dump(that: Node) -> str:
    """Translate the node to text."""
    return _dump(that)


# endregion Dumping
