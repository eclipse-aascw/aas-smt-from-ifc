# SPDX-FileCopyrightText: 2025 aas-smt-from-ifc AUTHORS
#
# SPDX-License-Identifier: MIT

"""Provide Intermediate Representation of an Express schema for better ergonomics."""

import decimal
import typing
from typing import (
    cast,
    Final,
    Sequence,
    Mapping,
    List,
    Optional,
    Tuple,
    MutableMapping,
    Set,
    Union,
    Iterator,
    Generic,
    TypeVar,
)

import networkx
from icontract import ensure, require
from express_schema import parse, lex

from aas_smt_from_ifc.common import (
    NonEmptySequence,
    bullet_points,
    NonNegativeInt,
    assert_never,
    assert_union_without_excluded,
)


# NOTE (mristin):
# We need to change internal values during the translation, so we turn off this warning
# intentionally.
# pylint: disable=protected-access


class BinaryType:
    """Represent a binary (blob) type dependent on constraints."""

    min_length: Final[Optional[NonNegativeInt]]
    max_length: Final[Optional[NonNegativeInt]]

    def __init__(
        self,
        min_length: Optional[NonNegativeInt] = None,
        max_length: Optional[NonNegativeInt] = None,
    ) -> None:
        self.min_length = min_length
        self.max_length = max_length


class BooleanType:
    """Represent a boolean (true/false) type."""

    def __init__(self) -> None:
        pass


T = TypeVar("T")


class Boundary(Generic[T]):
    """Represent a boundary of a range."""

    # NOTE (mristin):
    # We can not write Final type annotations with generic parameters in
    # class definition, so we put the type annotations in __init__.

    def __init__(self, inclusive: bool, value: T) -> None:
        self.inclusive: Final[bool] = inclusive
        self.value: Final[T] = value


class IntegerType:
    """Represent an integer type dependent on constraints."""

    # NOTE (mristin):
    # We introduce getters for min and max values to signal that external clients
    # should not change the respective values, while this module needs to change
    # them during translation.

    @property
    def min_value(self) -> Optional[Boundary[int]]:
        """Return the inferred lower bound from the domain rules."""
        return self._min_value

    @property
    def max_value(self) -> Optional[Boundary[int]]:
        """Return the inferred upper bound from the domain rules."""
        return self._max_value

    def __init__(
        self,
        min_value: Optional[Boundary[int]] = None,
        max_value: Optional[Boundary[int]] = None,
    ) -> None:
        self._min_value = min_value
        self._max_value = max_value


class LogicalType:
    """Represent a logical (true/false/unknown) type."""

    def __init__(self) -> None:
        pass


class NumberType:
    """Represent either an integer or a real."""

    min_value: Final[Optional[Boundary[Union[int, decimal.Decimal]]]]
    max_value: Final[Optional[Boundary[Union[int, decimal.Decimal]]]]

    def __init__(
        self,
        min_value: Optional[Boundary[Union[int, decimal.Decimal]]] = None,
        max_value: Optional[Boundary[Union[int, decimal.Decimal]]] = None,
    ) -> None:
        self.min_value = min_value
        self.max_value = max_value


class RealType:
    """Represent a real type dependent on constraints."""

    # NOTE (mristin):
    # We introduce getters for min and max values to signal that external clients
    # should not change the respective values, while this module needs to change
    # them during translation.

    @property
    def min_value(self) -> Optional[Boundary[decimal.Decimal]]:
        """Return the lower bound inferred from the domain rules."""
        return self._min_value

    @property
    def max_value(self) -> Optional[Boundary[decimal.Decimal]]:
        """Return the upper bound inferred from the domain rules."""
        return self._max_value

    def __init__(
        self,
        min_value: Optional[Boundary[decimal.Decimal]] = None,
        max_value: Optional[Boundary[decimal.Decimal]] = None,
    ) -> None:
        self._min_value = min_value
        self._max_value = max_value


class StringType:
    """Represent a string type dependent on constraints."""

    min_length: Final[Optional[NonNegativeInt]]
    max_length: Final[Optional[NonNegativeInt]]

    # NOTE (mristin):
    # We use a protected attribute to signal that it should be changed only
    # by this module.
    _choice: Optional[NonEmptySequence[str]]

    @property
    def choice(self) -> Optional[NonEmptySequence[str]]:
        """List allowed values."""
        return self._choice

    def __init__(
        self,
        min_length: Optional[NonNegativeInt] = None,
        max_length: Optional[NonNegativeInt] = None,
        choice: Optional[NonEmptySequence[str]] = None,
    ) -> None:
        self.min_length = min_length
        self.max_length = max_length
        self._choice = choice


class ArrayType:
    """Represent an array type dependent on constraints."""

    items: Final["Type"]
    optional: Final[bool]
    min_length: Final[Optional[NonNegativeInt]]
    max_length: Final[Optional[NonNegativeInt]]

    def __init__(
        self,
        items: "Type",
        min_length: Optional[NonNegativeInt] = None,
        max_length: Optional[NonNegativeInt] = None,
        optional: bool = False,
    ) -> None:
        self.items = items
        self.min_length = min_length
        self.max_length = max_length
        self.optional = optional


class BagType:
    """Represent a bag type dependent on constraints."""

    items: Final["Type"]
    min_length: Final[Optional[NonNegativeInt]]
    max_length: Final[Optional[NonNegativeInt]]

    def __init__(
        self,
        items: "Type",
        min_length: Optional[NonNegativeInt] = None,
        max_length: Optional[NonNegativeInt] = None,
    ) -> None:
        self.items = items
        self.min_length = min_length
        self.max_length = max_length


class ListType:
    """Represent a list type dependent on constraints."""

    items: Final["Type"]
    min_length: Final[Optional[NonNegativeInt]]
    max_length: Final[Optional[NonNegativeInt]]
    unique: Final[bool]

    def __init__(
        self,
        items: "Type",
        min_length: Optional[NonNegativeInt] = None,
        max_length: Optional[NonNegativeInt] = None,
        unique: bool = False,
    ) -> None:
        self.items = items
        self.min_length = min_length
        self.max_length = max_length
        self.unique = unique


class SetType:
    """Represent a set type dependent on constraints."""

    items: Final["Type"]
    min_length: Final[Optional[NonNegativeInt]]
    max_length: Final[Optional[NonNegativeInt]]

    def __init__(
        self,
        items: "Type",
        min_length: Optional[NonNegativeInt] = None,
        max_length: Optional[NonNegativeInt] = None,
    ) -> None:
        self.items = items
        self.min_length = min_length
        self.max_length = max_length


class Enumeration:
    """Represent a named enumeration with literals."""

    identifier: lex.Identifier
    values: Final[Sequence[lex.Identifier]]

    def __init__(
        self,
        identifier: lex.Identifier,
        values: Sequence[lex.Identifier],
    ) -> None:
        self.identifier = identifier
        self.values = values


class SelectType:
    """Represent a type selection, *i.e.*, a type variant a.k.a. a type union."""

    types: Final[Sequence[Union["DeclaredType", "Enumeration", "Entity"]]]

    def __init__(
        self,
        types: Sequence[Union["DeclaredType", "Enumeration", "Entity"]],
    ) -> None:
        self.types = types


class DeclaredType:
    """
    Represent a reference to a type declaration.

    We diverge in the intermediate representation from the NamedType in the parse
    layer since we can distinguish here between enumeration, entity and declared type.
    """

    identifier: Final[lex.Identifier]

    # NOTE (mristin):
    # We introduce the getter for the type selection to stress that the external
    # clients should not mutate the object, while this internal module can.
    @property
    def tajp(self) -> "Type":
        """Return the underlying type definition."""
        return self._tajp

    parsed: Final[parse.TypeDeclaration]

    def __init__(
        self, identifier: lex.Identifier, tajp: "Type", parsed: parse.TypeDeclaration
    ) -> None:
        self.identifier = identifier
        self._tajp = tajp
        self.parsed = parsed


def resolve_type(tajp: "Type") -> "TypeWithoutDeclaredType":
    """
    Resolve, i.e., de-reference the type beneath ``tajp``.

    For a declared type, we return the underlying type definition. For all other types,
    we return them as-are.
    """
    while isinstance(tajp, DeclaredType):
        tajp = tajp.tajp

    return tajp


class Attribute:
    """Represent a named attribute of an entity."""

    name: Final[lex.Identifier]
    optional: Final[bool]
    tajp: "Type"

    # NOTE (mristin):
    # We use protected setters (prefixed with ``_``) to highlight that they should be
    # used only internally, in this module, while external users should use only
    # getters.

    _specified_for: "Entity"

    @property
    def specified_for(self) -> "Entity":
        """Return the entity for which the attribute was specified for."""
        return self._specified_for

    def _set_specified_for(self, entity: "Entity") -> None:
        self._specified_for = entity

    parsed: Final[parse.ExplicitAttributeDefinition]

    def __init__(
        self,
        name: lex.Identifier,
        optional: bool,
        tajp: "Type",
        specified_for: "Entity",
        parsed: parse.ExplicitAttributeDefinition,
    ) -> None:
        self.name = name
        self.optional = optional
        self.tajp = tajp

        self._set_specified_for(specified_for)

        self.parsed = parsed


class Entity:
    """Represent an entity in a schema."""

    identifier: Final[lex.Identifier]

    # NOTE (mristin):
    # We diverge in naming here since we could not wrap our head around the naming
    # of Express schema -- subtype-of means supertypes and supertype-of means subtypes.

    # NOTE (mristin):
    # We use protected setters (prefixed with ``_``) to highlight that they should be
    # used only internally, in this module, while external users should use only
    # getters.

    _supertypes: Sequence["Entity"]

    @property
    def supertypes(self) -> Sequence["Entity"]:
        """Get the super-types of the entity, *i.e.*, the parent entities."""
        return self._supertypes

    def _set_supertypes(self, supertypes: Sequence["Entity"]) -> None:
        self._supertypes = supertypes

    _subtypes: Sequence["Entity"]

    @property
    def subtypes(self) -> Sequence["Entity"]:
        """The subtypes of the entity, *i.e.*, the children entities."""
        return self._subtypes

    def _set_subtypes(self, subtypes: Sequence["Entity"]) -> None:
        self._subtypes = subtypes

    _descendant_concrete_entities: Sequence["Entity"]

    @property
    def descendant_concrete_entities(self) -> Sequence["Entity"]:
        """The concrete entities underlying this entity, excluding itself."""
        return self._descendant_concrete_entities

    # fmt: off
    @require(
        lambda self, descendant_concrete_entities:
        self not in descendant_concrete_entities
    )
    # fmt: on
    def _set_descendant_concrete_entities(
        self, descendant_concrete_entities: Sequence["Entity"]
    ) -> None:
        self._descendant_concrete_entities = descendant_concrete_entities

    abstract: Final[bool]

    _attributes: Sequence["Attribute"]
    _attribute_by_name: Mapping[lex.Identifier, Attribute]

    @property
    def attributes(self) -> Sequence["Attribute"]:
        """Get the attributes of the entity."""
        return self._attributes

    @property
    def attribute_by_name(self) -> Mapping[lex.Identifier, Attribute]:
        """Get attributes mapped by their name."""
        return self._attribute_by_name

    def _set_attributes(self, attributes: Sequence["Attribute"]) -> None:
        self._attributes = attributes
        self._attribute_by_name = {attr.name: attr for attr in attributes}

    parsed: Final[parse.EntityDeclaration]

    def __init__(
        self,
        identifier: lex.Identifier,
        supertypes: Sequence["Entity"],
        subtypes: Sequence["Entity"],
        descendant_concrete_entities: Sequence["Entity"],
        abstract: bool,
        attributes: Sequence["Attribute"],
        parsed: parse.EntityDeclaration,
    ) -> None:
        self.identifier = identifier

        self._set_supertypes(supertypes)
        self._set_subtypes(subtypes)
        self._set_descendant_concrete_entities(descendant_concrete_entities)

        self.abstract = abstract

        self._set_attributes(attributes)

        self.parsed = parsed

    def __repr__(self) -> str:
        return f"<{self.__class__.__qualname__} {self.identifier} at 0x{id(self):x}>"


class Schema:
    """Represent an Express schema."""

    identifier: Final[lex.Identifier]

    declared_types: Final[Sequence[DeclaredType]]
    declared_types_by_id: Final[Mapping[lex.Identifier, DeclaredType]]
    declared_types_topologically_sorted: Final[Sequence[DeclaredType]]

    enumerations: Final[Sequence[Enumeration]]
    enumerations_by_id: Final[Mapping[lex.Identifier, Enumeration]]

    entities: Final[Sequence[Entity]]
    entities_by_id: Final[Mapping[lex.Identifier, Entity]]
    entities_topologically_sorted: Final[Sequence[Entity]]

    parsed: Final[parse.Schema]

    def __init__(
        self,
        identifier: lex.Identifier,
        declared_types: Sequence[DeclaredType],
        enumerations: Sequence[Enumeration],
        entities: Sequence[Entity],
        parsed: parse.Schema,
    ) -> None:
        self.identifier = identifier

        self.declared_types = declared_types
        self.declared_types_by_id = {
            declared_type.identifier: declared_type for declared_type in declared_types
        }
        declared_types_topologically_sorted, sort_error = (
            _topologically_sorted_declared_types(declared_types)
        )
        assert sort_error is None, (
            "Unexpected error in topological sort of the declared types "
            "-- expected to catch this error before: {sort_error}"
        )
        assert declared_types_topologically_sorted is not None
        self.declared_types_topologically_sorted = declared_types_topologically_sorted

        self.enumerations = enumerations
        self.enumerations_by_id = {
            enumeration.identifier: enumeration for enumeration in enumerations
        }

        self.entities = entities
        self.parsed = parsed
        self.entities_by_id = {entity.identifier: entity for entity in entities}

        entities_topologically_sorted, sort_error = _topologically_sorted_entities(
            entities
        )
        assert sort_error is None, (
            "Unexpected error in topological sort of the entities -- expected to catch"
            f"this error before: {sort_error}"
        )
        assert entities_topologically_sorted is not None

        self.entities_topologically_sorted = entities_topologically_sorted


def _specifies_nested_unnamed_enumeration(type_selection: parse.TypeSelection) -> bool:
    """Check whether the type selection specifies an unnamed enumeration within it."""
    if isinstance(type_selection, parse.EnumType):
        return False

    stack = [type_selection]

    while len(stack) > 0:
        current_type = stack.pop()

        if isinstance(current_type, parse.EnumType):
            return True

        elif isinstance(
            current_type,
            (
                parse.BinaryType,
                parse.BooleanType,
                parse.IntegerType,
                parse.LogicalType,
                parse.NamedType,
                parse.NumberType,
                parse.RealType,
                parse.StringType,
            ),
        ):
            pass

        elif isinstance(
            current_type,
            (parse.ArrayType, parse.BagType, parse.ListType, parse.SetType),
        ):
            if isinstance(current_type.of, parse.GenericType):
                raise NotImplementedError(
                    "We did not implement the handling of generic types. Please "
                    "contact the developers if you need this feature."
                )

            stack.append(current_type.of)

        elif isinstance(current_type, parse.SelectType):
            stack.extend(current_type.values)

        else:
            # noinspection PyTypeChecker
            assert_never(current_type)

    return False


def _list_referenced_named_types(
    type_selection: parse.TypeSelection,
) -> Iterator[lex.Identifier]:
    """Go over the type selection and list all the named types referenced from it."""
    if isinstance(type_selection, parse.NamedType):
        yield type_selection.reference
    elif isinstance(
        type_selection,
        (
            parse.BinaryType,
            parse.BooleanType,
            parse.IntegerType,
            parse.LogicalType,
            parse.NumberType,
            parse.RealType,
            parse.StringType,
        ),
    ):
        pass
    elif isinstance(
        type_selection, (parse.ArrayType, parse.BagType, parse.ListType, parse.SetType)
    ):
        if isinstance(type_selection.of, parse.GenericType):
            raise NotImplementedError(
                "We did not handle the in-lining of generic types. Please contact "
                "the developers if you need this feature."
            )

        yield from _list_referenced_named_types(type_selection.of)
    elif isinstance(type_selection, parse.EnumType):
        pass
    elif isinstance(type_selection, parse.SelectType):
        for value in type_selection.values:
            yield from _list_referenced_named_types(value)
    else:
        # noinspection PyTypeChecker
        assert_never(type_selection)


def _try_evaluate_expr_as_int(expr: parse.Expr) -> Optional[int]:
    """Try to evaluate a simple expression as an integer value."""
    if isinstance(expr, parse.IntegerLiteral):
        return expr.value

    elif isinstance(expr, parse.UnaryExpr):
        if expr.op is parse.UnaryOp.PLUS:
            return _try_evaluate_expr_as_int(expr.operand)
        elif expr.op is parse.UnaryOp.NEG:
            inner_value = _try_evaluate_expr_as_int(expr.operand)
            return -inner_value if inner_value is not None else None
        else:
            return None

    elif isinstance(expr, parse.BinaryExpr):
        left = _try_evaluate_expr_as_int(expr)
        if left is None:
            return None

        right = _try_evaluate_expr_as_int(expr)
        if right is None:
            return None

        assert isinstance(left, int)
        assert isinstance(right, int)

        if expr.op is parse.BinaryOp.ADD:
            return left + right

        elif expr.op is parse.BinaryOp.SUBTRACT:
            return left - right

        elif expr.op is parse.BinaryOp.MULTIPLY:
            return left * right

        elif expr.op is parse.BinaryOp.INTEGER_DIVIDE:
            return left // right

        elif expr.op is parse.BinaryOp.MODULO:
            return left % right

        elif expr.op is parse.BinaryOp.POWER:
            result = left**right
            assert isinstance(result, int)
            return result
        else:
            return None

    else:
        return None


def _try_evaluate_expr_as_decimal(expr: parse.Expr) -> Optional[decimal.Decimal]:
    """Try to evaluate a simple expression as a decimal value."""
    if isinstance(expr, parse.RealLiteral):
        return expr.value
    elif isinstance(expr, parse.IntegerLiteral):
        return decimal.Decimal(expr.value)

    elif isinstance(expr, parse.UnaryExpr):
        if expr.op is parse.UnaryOp.PLUS:
            return _try_evaluate_expr_as_decimal(expr.operand)
        elif expr.op is parse.UnaryOp.NEG:
            inner_value = _try_evaluate_expr_as_decimal(expr.operand)
            return -inner_value if inner_value is not None else None
        else:
            return None

    elif isinstance(expr, parse.BinaryExpr):
        left = _try_evaluate_expr_as_decimal(expr.left)
        if left is None:
            return None

        right = _try_evaluate_expr_as_decimal(expr.right)
        if right is None:
            return None

        if expr.op is parse.BinaryOp.ADD:
            return left + right

        elif expr.op is parse.BinaryOp.SUBTRACT:
            return left - right

        elif expr.op is parse.BinaryOp.MULTIPLY:
            return left * right

        elif expr.op is parse.BinaryOp.REAL_DIVIDE:
            return left / right

        elif expr.op is parse.BinaryOp.POWER:
            return left**right

        else:
            return None

    else:
        return None


def _try_min_max_length_from_width_and_fixed(
    width: Optional[parse.Expr], fixed: bool
) -> Tuple[Optional[NonNegativeInt], Optional[NonNegativeInt]]:
    """
    Try to evaluate the width and fixed of a bounded string or binary type.

    If width is not defined or if width can not be evaluated as simple integer,
    return (None, None).
    """
    min_length = None  # type: Optional[NonNegativeInt]
    max_length = None  # type: Optional[NonNegativeInt]
    if width is not None:
        evaluated_width = _try_evaluate_expr_as_int(width)
        if evaluated_width is not None and evaluated_width >= 0:
            if fixed:
                min_length = max_length = NonNegativeInt(evaluated_width)
            else:
                max_length = NonNegativeInt(evaluated_width)

    return min_length, max_length


def _try_min_max_length_from_bound_spec(
    bound_spec: Optional[parse.BoundSpec],
) -> Tuple[Optional[NonNegativeInt], Optional[NonNegativeInt]]:
    """
    Try to evaluate the bound spec as a min and max length.

    If the bound spec is not defined or if lower and upper bound can not be evaluated
    as simple integers, return (None, None).
    """
    min_length = None  # type: Optional[NonNegativeInt]
    max_length = None  # type: Optional[NonNegativeInt]
    if bound_spec is not None:
        lower_bound = _try_evaluate_expr_as_int(bound_spec.lower)
        upper_bound = _try_evaluate_expr_as_int(bound_spec.upper)
        if lower_bound is not None and lower_bound >= 0:
            min_length = NonNegativeInt(lower_bound)

        if upper_bound is not None and upper_bound >= 0:
            max_length = NonNegativeInt(upper_bound)

    return min_length, max_length


@ensure(lambda result: (result[0] is not None) ^ (result[1] is not None))
def _dereference_named_type(
    identifier: lex.Identifier,
    declared_types_by_id: Mapping[lex.Identifier, DeclaredType],
    enumerations_by_id: Mapping[lex.Identifier, Enumeration],
    entities_by_id: Mapping[lex.Identifier, Entity],
) -> Tuple[Optional[Union[DeclaredType, Enumeration, Entity]], Optional[str]]:
    dereferenced_type = declared_types_by_id.get(identifier, None)
    if dereferenced_type is not None:
        return dereferenced_type, None

    dereferenced_enumeration = enumerations_by_id.get(identifier, None)
    if dereferenced_enumeration is not None:
        return dereferenced_enumeration, None

    dereferenced_entity = entities_by_id.get(identifier, None)
    if dereferenced_entity is not None:
        return dereferenced_entity, None

    return None, (
        f"The type with an identifier {identifier!r} is referenced, "
        f"but its declaration could not be found."
    )


@ensure(
    lambda result: (result[0] is not None) ^ (result[1] is not None),
    "Either a result or an error",
)
def _recursively_translate_type_selection(
    type_selection: parse.TypeSelection,
    declared_types_by_id: Mapping[lex.Identifier, DeclaredType],
    enumerations_by_id: Mapping[lex.Identifier, Enumeration],
    entities_by_id: Mapping[lex.Identifier, Entity],
) -> Tuple[Optional["Type"], Optional[str]]:
    """
    De-reference the named types in the given type selection recursively.

    Return the in-lined type, or an error, if any.
    """
    if isinstance(type_selection, parse.NamedType):
        dereferenced_type, error = _dereference_named_type(
            identifier=type_selection.reference,
            declared_types_by_id=declared_types_by_id,
            enumerations_by_id=enumerations_by_id,
            entities_by_id=entities_by_id,
        )

        if error is not None:
            return None, error

        assert dereferenced_type is not None

        return dereferenced_type, None

    elif isinstance(type_selection, parse.BinaryType):
        min_length, max_length = _try_min_max_length_from_width_and_fixed(
            width=type_selection.width, fixed=type_selection.fixed
        )

        return BinaryType(min_length=min_length, max_length=max_length), None

    elif isinstance(type_selection, parse.BooleanType):
        return BooleanType(), None

    elif isinstance(type_selection, parse.IntegerType):
        return IntegerType(), None

    elif isinstance(type_selection, parse.LogicalType):
        return LogicalType(), None

    elif isinstance(type_selection, parse.NumberType):
        return NumberType(), None

    elif isinstance(type_selection, parse.RealType):
        return RealType(), None

    elif isinstance(type_selection, parse.StringType):
        min_length, max_length = _try_min_max_length_from_width_and_fixed(
            width=type_selection.width, fixed=type_selection.fixed
        )

        return StringType(min_length=min_length, max_length=max_length), None

    elif isinstance(
        type_selection, (parse.ArrayType, parse.BagType, parse.ListType, parse.SetType)
    ):
        if isinstance(type_selection.of, parse.GenericType):
            raise NotImplementedError(
                "Translating generic types is currently not supported. Please contact "
                "the developers if you need this feature."
            )

        items_type, error = _recursively_translate_type_selection(
            type_selection=type_selection.of,
            declared_types_by_id=declared_types_by_id,
            enumerations_by_id=enumerations_by_id,
            entities_by_id=entities_by_id,
        )
        if error is not None:
            return None, error
        assert items_type is not None

        min_length, max_length = _try_min_max_length_from_bound_spec(
            type_selection.bound_spec
        )

        if isinstance(type_selection, parse.ArrayType):
            return (
                ArrayType(
                    items=items_type,
                    min_length=min_length,
                    max_length=max_length,
                    optional=type_selection.optional,
                ),
                None,
            )
        elif isinstance(type_selection, parse.BagType):
            return (
                BagType(items=items_type, min_length=min_length, max_length=max_length),
                None,
            )
        elif isinstance(type_selection, parse.ListType):
            return (
                ListType(
                    items=items_type,
                    unique=type_selection.unique,
                    min_length=min_length,
                    max_length=max_length,
                ),
                None,
            )
        elif isinstance(type_selection, parse.SetType):
            return (
                SetType(items=items_type, min_length=min_length, max_length=max_length),
                None,
            )
        else:
            # noinspection PyTypeChecker
            assert_never(type_selection)

    elif isinstance(type_selection, parse.EnumType):
        raise AssertionError(
            "Named enumerations were supposed to be handled before and skipped here. "
            "We were also supposed to raise a not-implemented-error before if there "
            "are unnamed nested enumerations."
        )

    elif isinstance(type_selection, parse.SelectType):
        types = []  # type: List[Union[DeclaredType, Enumeration, Entity]]
        for named_type in type_selection.values:
            dereferenced_type, error = _dereference_named_type(
                identifier=named_type.reference,
                declared_types_by_id=declared_types_by_id,
                enumerations_by_id=enumerations_by_id,
                entities_by_id=entities_by_id,
            )

            if error is not None:
                return None, error

            assert dereferenced_type is not None

            types.append(dereferenced_type)

        return SelectType(types=types), None

    else:
        # noinspection PyTypeChecker
        assert_never(type_selection)


BoundaryComparisonBinaryOp = Union[
    typing.Literal[parse.BinaryOp.LESS_THAN],
    typing.Literal[parse.BinaryOp.GREATER_THAN],
    typing.Literal[parse.BinaryOp.LESS_EQUAL],
    typing.Literal[parse.BinaryOp.GREATER_EQUAL],
    typing.Literal[parse.BinaryOp.EQUAL],
]


class _TypeDomainRuleMatcher:
    """Try to match AST patterns on different domain rules in type declarations."""

    # pylint: disable=missing-docstring

    @staticmethod
    def _try_boundary_comparison_binary_op(
        op: parse.BinaryOp,
    ) -> Optional[BoundaryComparisonBinaryOp]:
        for arg in typing.get_args(BoundaryComparisonBinaryOp):
            if op is typing.get_args(arg)[0]:
                return cast(BoundaryComparisonBinaryOp, op)

        return None

    @staticmethod
    def try_self_in_list_of_strings(expr: parse.Expr) -> Optional[List[str]]:
        if not (
            isinstance(expr, parse.BinaryExpr)
            and expr.op is parse.BinaryOp.IN
            and isinstance(expr.left, parse.Self)
            and isinstance(expr.right, parse.AggregateLiteral)
        ):
            return None

        if not all(
            isinstance(element.expr, parse.StringLiteral)
            for element in expr.right.elements
        ):
            return None

        result = []  # type: List[str]
        for element in expr.right.elements:
            assert isinstance(element.expr, parse.StringLiteral)

            if element.repetition is None:
                result.append(element.expr.value)
            else:
                # noinspection PyTypeChecker
                repetition = _try_evaluate_expr_as_int(element.repetition)
                if repetition is None:
                    return None

                result.extend([element.expr.value] * repetition)

        return result

    @staticmethod
    def try_self_compare_integer_or_real(
        expr: parse.Expr,
    ) -> Optional[Tuple[BoundaryComparisonBinaryOp, Union[int, decimal.Decimal]]]:
        if not (
            isinstance(expr, parse.BinaryExpr) and isinstance(expr.left, parse.Self)
        ):
            return None

        op = _TypeDomainRuleMatcher._try_boundary_comparison_binary_op(expr.op)
        if op is None:
            return None

        right: Optional[Union[int, decimal.Decimal]]

        right = _try_evaluate_expr_as_int(expr.right)
        if right is not None:
            return op, right

        right = _try_evaluate_expr_as_decimal(expr.right)
        if right is not None:
            return op, right

        return None

    @staticmethod
    def try_self_interval(
        expr: parse.Expr,
    ) -> Optional[
        Tuple[
            Union[int, decimal.Decimal],
            BoundaryComparisonBinaryOp,
            BoundaryComparisonBinaryOp,
            Union[int, decimal.Decimal],
        ]
    ]:
        if not isinstance(expr, parse.Interval):
            return None

        if not isinstance(expr.center, parse.Self):
            return None

        left_to_center = _TypeDomainRuleMatcher._try_boundary_comparison_binary_op(
            expr.left_to_center
        )
        if left_to_center is None:
            return None

        center_to_right = _TypeDomainRuleMatcher._try_boundary_comparison_binary_op(
            expr.center_to_right
        )
        if center_to_right is None:
            return None

        left: Optional[Union[int, decimal.Decimal]]
        left = _try_evaluate_expr_as_int(expr.left)
        if left is None:
            left = _try_evaluate_expr_as_decimal(expr.left)

        if left is None:
            return None

        right: Optional[Union[int, decimal.Decimal]]
        right = _try_evaluate_expr_as_int(expr.right)
        if right is None:
            right = _try_evaluate_expr_as_decimal(expr.right)

        if right is None:
            return None

        return left, left_to_center, center_to_right, right


class _TypeDomainRulesInterpreter:
    """Try to understand a set of domain rules for a type declaration."""

    # pylint: disable=missing-docstring

    @staticmethod
    def try_self_choice(
        domain_rules: Sequence[parse.DomainRule],
    ) -> Optional[List[str]]:
        """Try to parse domain rules as restricting the self on a choice."""
        choice_set = None  # type: Optional[Set[str]]
        first_choice = None  # type: Optional[List[str]]

        for domain_rule in domain_rules:
            choice = _TypeDomainRuleMatcher.try_self_in_list_of_strings(
                domain_rule.expr
            )
            if choice is not None:
                if choice_set is None:
                    choice_set = set(choice)
                    first_choice = choice
                else:
                    choice_set.intersection_update(choice)

        if first_choice is not None:
            assert choice_set is not None

            choice_intersection = [
                literal for literal in first_choice if literal in choice_set
            ]

            return choice_intersection

        return None

    @staticmethod
    def try_self_min_max_value(
        domain_rules: Sequence[parse.DomainRule], number_type: typing.Type[T]
    ) -> Tuple[Optional[Boundary[T]], Optional[Boundary[T]]]:
        """Try to infer the range of the self."""
        lower_bounds = []  # type: List[Boundary[T]]
        upper_bounds = []  # type: List[Boundary[T]]

        for domain_rule in domain_rules:
            op_value = _TypeDomainRuleMatcher.try_self_compare_integer_or_real(
                domain_rule.expr
            )
            if op_value is not None:
                op, value = op_value

                if isinstance(value, number_type):
                    if op is parse.BinaryOp.EQUAL:
                        return (
                            Boundary(inclusive=True, value=value),
                            Boundary(inclusive=True, value=value),
                        )
                    elif op is parse.BinaryOp.LESS_THAN:
                        upper_bounds.append(Boundary(inclusive=False, value=value))
                    elif op is parse.BinaryOp.LESS_EQUAL:
                        upper_bounds.append(Boundary(inclusive=True, value=value))
                    elif op is parse.BinaryOp.GREATER_THAN:
                        lower_bounds.append(Boundary(inclusive=False, value=value))
                    elif op is parse.BinaryOp.GREATER_EQUAL:
                        lower_bounds.append(Boundary(inclusive=True, value=value))
                    else:
                        # noinspection PyTypeChecker
                        assert_never(op)

            left_op_op_right = _TypeDomainRuleMatcher.try_self_interval(
                expr=domain_rule.expr
            )
            if left_op_op_right is not None:
                left, left_to_center, center_to_right, right = left_op_op_right

                if isinstance(left, number_type) and isinstance(right, number_type):
                    # We handle left_to_center comparison first (left op self).
                    if left_to_center is parse.BinaryOp.LESS_THAN:
                        # left < self
                        lower_bounds.append(Boundary(inclusive=False, value=left))
                    elif left_to_center is parse.BinaryOp.LESS_EQUAL:
                        # left <= self
                        lower_bounds.append(Boundary(inclusive=True, value=left))
                    elif left_to_center is parse.BinaryOp.GREATER_THAN:
                        # left > self
                        upper_bounds.append(Boundary(inclusive=False, value=left))
                    elif left_to_center is parse.BinaryOp.GREATER_EQUAL:
                        # left >= self
                        upper_bounds.append(Boundary(inclusive=True, value=left))
                    elif left_to_center is parse.BinaryOp.EQUAL:
                        # left = self
                        return (
                            Boundary(inclusive=True, value=left),
                            Boundary(inclusive=True, value=left),
                        )
                    else:
                        # noinspection PyTypeChecker
                        assert_never(left_to_center)

                    # We now handle center_to_right comparison (self op right).
                    if center_to_right is parse.BinaryOp.LESS_THAN:
                        # self < right
                        upper_bounds.append(Boundary(inclusive=False, value=right))
                    elif center_to_right is parse.BinaryOp.LESS_EQUAL:
                        # self <= right
                        upper_bounds.append(Boundary(inclusive=True, value=right))
                    elif center_to_right is parse.BinaryOp.GREATER_THAN:
                        # self > right
                        lower_bounds.append(Boundary(inclusive=False, value=right))
                    elif center_to_right is parse.BinaryOp.GREATER_EQUAL:
                        # self >= right
                        lower_bounds.append(Boundary(inclusive=True, value=right))
                    elif center_to_right is parse.BinaryOp.EQUAL:
                        # self = right, exact match
                        return (
                            Boundary(inclusive=True, value=right),
                            Boundary(inclusive=True, value=right),
                        )
                    else:
                        # noinspection PyTypeChecker
                        assert_never(center_to_right)

        sorted_lower_bounds = sorted(
            lower_bounds,
            key=lambda boundary: (boundary.value, 1 if not boundary.inclusive else 0),
        )
        lower_bound = sorted_lower_bounds[-1] if len(sorted_lower_bounds) > 0 else None

        sorted_upper_bounds = sorted(
            upper_bounds,
            key=lambda boundary: (boundary.value, 0 if not boundary.inclusive else 1),
        )
        upper_bound = sorted_upper_bounds[0] if len(sorted_upper_bounds) > 0 else None

        return lower_bound, upper_bound


# fmt: off
@require(
    lambda declared_types, declared_types_by_id:
    all(
        declared_type.identifier in declared_types_by_id
        and declared_type is declared_types_by_id[declared_type.identifier]
        for declared_type in declared_types
    ),
    "Declared types and their mapping by identifier must be consistent."
)
# fmt: on
def _resolve_declared_types_in_situ(
    declared_types: Sequence[DeclaredType],
    declared_types_by_id: Mapping[lex.Identifier, DeclaredType],
    enumerations_by_id: Mapping[lex.Identifier, Enumeration],
    entities_by_id: Mapping[lex.Identifier, Entity],
) -> Optional[NonEmptySequence[str]]:
    """
    Resolve the underlying types beneath the declared types.

    The values of ``declared_types_by_id`` are modified in-place.

    This command also takes care of inferring the constraints from the domain rules and
    imposing them on the underlying type.
    """
    # NOTE (mristin):
    # We need to disable the warning related to writes of protected attributes as we
    # indeed have to internally modify them.
    # pylint: disable=attribute-defined-outside-init

    errors = []  # type: List[str]

    for declared_type in declared_types:
        # NOTE (mristin):
        # We diverge here in the intermediate representation from the parse layer as we
        # treat type declarations of enumerations as first-class citizens instead of
        # treating them as type declaration.
        if isinstance(declared_type.parsed.type_selection, parse.EnumType):
            continue

        tajp, error = _recursively_translate_type_selection(
            type_selection=declared_type.parsed.type_selection,
            declared_types_by_id=declared_types_by_id,
            enumerations_by_id=enumerations_by_id,
            entities_by_id=entities_by_id,
        )

        if error is not None:
            errors.append(
                f"Failed to translate the type selection "
                f"for the type declaration {declared_type.identifier!r}: {error}"
            )
            continue

        assert tajp is not None

        declared_type._tajp = tajp

    if len(errors) > 0:
        return NonEmptySequence(errors)

    for declared_type in declared_types:
        # NOTE (mristin):
        # We use a shortcut here for readability. The tajp will be modified in place,
        # *i.e.*, we will add inferred constraints.
        tajp = declared_type.tajp

        # NOTE (mristin):
        # We need to infer the domain rules here so that the inferred constraints are
        # passed over down the inlining.

        if isinstance(tajp, StringType):
            choice = _TypeDomainRulesInterpreter.try_self_choice(
                domain_rules=declared_type.parsed.domain_rules
            )
            if choice is not None and len(choice) > 0:
                tajp._choice = NonEmptySequence(choice)

        elif isinstance(tajp, IntegerType):
            min_value_int: Optional[Boundary[int]]
            max_value_int: Optional[Boundary[int]]

            min_value_int, max_value_int = (
                _TypeDomainRulesInterpreter.try_self_min_max_value(
                    domain_rules=declared_type.parsed.domain_rules, number_type=int
                )
            )

            if min_value_int is not None:
                tajp._min_value = min_value_int

            if max_value_int is not None:
                tajp._max_value = max_value_int

        elif isinstance(tajp, RealType):
            min_value_real: Optional[Boundary[decimal.Decimal]]
            max_value_real: Optional[Boundary[decimal.Decimal]]

            min_value_real, max_value_real = (
                _TypeDomainRulesInterpreter.try_self_min_max_value(
                    domain_rules=declared_type.parsed.domain_rules,
                    number_type=decimal.Decimal,
                )
            )

            if min_value_real is not None:
                tajp._min_value = min_value_real

            if max_value_real is not None:
                tajp._max_value = max_value_real
        else:
            pass

    return None


def _topologically_sorted_declared_types(
    declared_types: Sequence[DeclaredType],
) -> Tuple[Optional[List[DeclaredType]], Optional[str]]:
    """
    Sort declared types in topological order by following the named references.

    Return the topologically sorted declared types, or an error, if any.
    """
    if len(declared_types) == 0:
        return [], None

    # noinspection PyTypeChecker
    graph: networkx.DiGraph[str] = networkx.DiGraph()

    for declared_type in declared_types:
        graph.add_node(declared_type.identifier)

        stack = [declared_type.tajp]
        while len(stack) > 0:
            top = stack.pop()

            if isinstance(top, (ArrayType, BagType, ListType, SetType)):
                stack.append(top.items)

            elif isinstance(top, SelectType):
                stack.extend(top.types)

            elif isinstance(top, DeclaredType):
                graph.add_edge(declared_type.identifier, top.identifier)
                stack.append(top.tajp)

    declared_type_by_identifier: Mapping[str, DeclaredType] = {
        declared_type.identifier: declared_type for declared_type in declared_types
    }

    try:
        topologically_sorted = list(networkx.topological_sort(graph))
    except networkx.exception.NetworkXUnfeasible:
        # NOTE (mristin):
        # This repeats the search over the graph, but as it happens only in exceptional
        # situations, the hit in time complexity is limited.
        cycle = networkx.find_cycle(graph)
        cycle_joined = ", ".join(str(edge) for edge in cycle)
        return None, f"Cycle between declared types detected: {cycle_joined}"

    return [
        declared_type_by_identifier[identifier]
        for identifier in reversed(topologically_sorted)
    ], None


def _translate_entity_without_subtypes_and_attributes(
    parsed: parse.EntityDeclaration,
) -> Entity:
    entity = Entity(
        identifier=parsed.identifier,
        # NOTE (mristin):
        # We have a chicken-and-egg problem here. We need to create entities and
        # reference them in subtype-of at the same time. At this point, we make
        # an empty list, but we will mutate it internally at the later stage, once
        # all the entity objects are created.
        supertypes=[],
        subtypes=[],
        descendant_concrete_entities=[],
        abstract=isinstance(parsed.supertype_declaration, parse.AbstractSupertype),
        attributes=[],
        parsed=parsed,
    )

    return entity


def _over_antecedent_types(entity: Entity) -> Iterator[Entity]:
    """
    Iterate recursively over all the antecedent types of the entity.

    Duplicates are excluded.
    """
    # NOTE (mristin):
    # We use ``id(.)`` for tracking the entities.
    yielded_set = set()  # type: Set[int]

    stack = list(entity.supertypes)

    while len(stack) > 0:
        top = stack.pop()

        if id(top) not in yielded_set:
            yield top
            yielded_set.add(id(top))

        stack.extend(top.supertypes)


@ensure(
    lambda entities: all(
        entity.supertypes is not None
        and entity.subtypes is not None
        and all(entity in supertype.subtypes for supertype in entity.supertypes)
        and all(entity in subtype.supertypes for subtype in entity.subtypes)
        for entity in entities
    )
)
def _dereference_sub_and_supertypes_of_entities_in_situ(
    entities: Sequence[Entity],
) -> Optional[NonEmptySequence[str]]:
    """
    Perform all de-referencing operations on entities in-place.

    This modification is necessary since we need to *create* the entities first *before*
    we can de-reference them.
    """
    entity_by_identifier = {entity.identifier: entity for entity in entities}

    errors = []  # type: List[str]

    for entity in entities:
        # NOTE (mristin):
        # We could not de-reference subtype-of before we created all the entity objects.
        # Now that all the entities are translated into intermediate representation,
        # we de-reference them as subtypes. Even though the ``supertypes``  is
        # immutable, we override the restriction as it is intended for
        # external users, not internal modifications.

        supertypes_of_entity = []  # type: List[Entity]

        if entity.parsed.subtype_declaration is not None:
            for named_ref in entity.parsed.subtype_declaration.of:
                supertype = entity_by_identifier.get(named_ref.identifier, None)
                if supertype is None:
                    errors.append(
                        f"The parent entity of {entity.identifier} in its subtype-of "
                        f"was not found: {named_ref.identifier!r}"
                    )
                    continue

                supertypes_of_entity.append(supertype)

        # noinspection PyProtectedMember
        entity._set_supertypes(supertypes_of_entity)  # pylint: disable=protected-access

    if len(errors) > 0:
        return NonEmptySequence(errors)

    subtypes_by_entity = dict()  # type: MutableMapping[Entity, List[Entity]]
    for entity in entities:
        for supertype in entity.supertypes:
            subtypes_of_supertype = subtypes_by_entity.get(supertype, None)
            if subtypes_of_supertype is None:
                subtypes_of_supertype = []
                subtypes_by_entity[supertype] = subtypes_of_supertype

            subtypes_of_supertype.append(entity)

    for entity, subtypes in subtypes_by_entity.items():
        # NOTE (mristin):
        # Similarly as the note above, we can not de-reference entities before we create
        # them, so we can not determine the subtypes. Even though the ``subtypes``  is
        # immutable, we override the restriction as it is intended for
        # external users, not internal modifications.

        # noinspection PyProtectedMember
        entity._set_subtypes(subtypes)  # pylint: disable=protected-access

    # NOTE (mristin):
    # Now we can stack all the concrete entities bottom-up.
    descendant_concrete_entities_by_entity = (
        dict()
    )  # type: MutableMapping[Entity, List[Entity]]

    # NOTE (mristin):
    # We use ``id(.)`` to keep a set of entities.
    descendants_concrete_entity_set_by_entity = (
        dict()
    )  # type: MutableMapping[Entity, Set[int]]

    for entity in entities:
        descendant_concrete_entities_by_entity[entity] = []
        descendants_concrete_entity_set_by_entity[entity] = set()

    stack = []  # type: List[Entity]
    for entity in entities:
        # NOTE (mristin):
        # We start from the leaf entities so that we can build the concrete entity
        # lists bottom-up.
        if len(entity.subtypes) == 0:
            stack.append(entity)

    while len(stack) > 0:
        top = stack.pop()
        if top.abstract:
            continue

        top_id = id(top)

        for antecedent_type in _over_antecedent_types(top):
            if top_id not in descendants_concrete_entity_set_by_entity[antecedent_type]:
                descendant_concrete_entities_by_entity[antecedent_type].append(top)
                descendants_concrete_entity_set_by_entity[antecedent_type].add(top_id)

        # NOTE (mristin):
        # We proceed bottom-up.
        stack.extend(top.supertypes)

    for entity in entities:
        # noinspection PyProtectedMember
        entity._set_descendant_concrete_entities(
            descendant_concrete_entities_by_entity[entity]
        )

    return None


@require(
    lambda entities: all(entity.subtypes is not None for entity in entities),
    "Expected entity subtypes to be de-referenced properly before",
)
@ensure(
    lambda result: (result[0] is not None) ^ (result[1] is not None),
    "Either a result or an error",
)
def _topologically_sorted_entities(
    entities: Sequence[Entity],
) -> Tuple[Optional[List[Entity]], Optional[str]]:
    """
    Sort entities in topological order using subtype relationships.

    Return the topologically sorted entities, or an error, if any.
    """
    if len(entities) == 0:
        return [], None

    # noinspection PyTypeChecker
    graph: networkx.DiGraph[str] = networkx.DiGraph()

    for entity in entities:
        graph.add_node(entity.identifier)

        for supertype in entity.supertypes:
            graph.add_edge(entity.identifier, supertype.identifier)

    entity_by_identifier: Mapping[str, Entity] = {
        entity.identifier: entity for entity in entities
    }

    try:
        topologically_sorted = list(networkx.topological_sort(graph))
    except networkx.exception.NetworkXUnfeasible:
        # NOTE (mristin):
        # This repeats the search over the graph, but as it happens only in exceptional
        # situations, the hit in time complexity is limited.
        cycle = networkx.find_cycle(graph)
        cycle_joined = ", ".join(str(edge) for edge in cycle)
        return None, f"Supertype cycle detected: {cycle_joined}"

    return [
        entity_by_identifier[identifier]
        for identifier in reversed(topologically_sorted)
    ], None


# fmt: off
@require(
    lambda entities, entities_by_id:
    all(
        entity.identifier in entities_by_id
        and id(entity) == id(entities_by_id[entity.identifier])
        for entity in entities
    ),
    "Entity and entities mapped by identifier are consistent."
)
# fmt: on
def _resolve_entity_attributes_in_situ(
    entities: Sequence[Entity],
    declared_types_by_id: Mapping[lex.Identifier, DeclaredType],
    enumerations_by_id: Mapping[lex.Identifier, Enumeration],
    entities_by_id: Mapping[lex.Identifier, Entity],
) -> Optional[NonEmptySequence[str]]:
    """
    Resolve the attributes in-place by translating their type selections.

    Return errors, if any.
    """
    errors = []  # type: List[str]

    for entity in entities:
        attributes = []  # type: List[Attribute]

        for attribute_definition in entity.parsed.explicit_clauses:
            for attribute_expr in attribute_definition.attributes:
                if not isinstance(attribute_expr, parse.NameRef):
                    errors.append(
                        f"We only handle attributes defined as named references, "
                        f"but we got {parse.dump(attribute_expr)}"
                    )
                    continue

                if isinstance(attribute_definition.type_selection, parse.GenericType):
                    raise NotImplementedError(
                        "We currently do not handle inlining generic types in attribute "
                        "definitions. Please contact the developers if you need this "
                        "feature."
                    )

                tajp, error = _recursively_translate_type_selection(
                    type_selection=attribute_definition.type_selection,
                    declared_types_by_id=declared_types_by_id,
                    enumerations_by_id=enumerations_by_id,
                    entities_by_id=entities_by_id,
                )
                if error is not None:
                    errors.append(
                        f"Failed to translate the type "
                        f"of the attribute {attribute_expr.identifier!r}: {error}"
                    )
                    continue

                assert tajp is not None

                attribute = Attribute(
                    name=attribute_expr.identifier,
                    optional=attribute_definition.optional,
                    tajp=tajp,
                    specified_for=entity,
                    parsed=attribute_definition,
                )

                attributes.append(attribute)

        # noinspection PyProtectedMember
        entity._set_attributes(attributes)

    if len(errors) > 0:
        return NonEmptySequence(errors)

    return None


def _stack_attributes_across_entity_hierarchy_in_situ(
    entities: Sequence[Entity],
) -> Optional[str]:
    """
    Extend the attributes of each entity with the attributes of its supertypes.

    We can not do this at the parsing stage as we could not de-reference supertype
    entities before creating them, so we have to perform this modification in a separate
    step.

    Return error, if any.
    """
    ontology, error = _topologically_sorted_entities(entities)
    if error is not None:
        return error

    assert ontology is not None

    # NOTE (mristin):
    # This set is used for assertions. We have to use integers as ``Entity`` does not
    # support hashing, and we resort to ``id(.)``.
    processed_entity_id_set = set()  # type: set[int]

    errors = []  # type: List[str]

    for entity in ontology:
        assert all(
            id(supertype) in processed_entity_id_set for supertype in entity.supertypes
        ), (
            f"All supertypes are expected to be processed "
            f"before the entity {entity.identifier!r} "
            f"due to the topological sort."
        )

        processed_entity_id_set.add(id(entity))

        if len(entity.supertypes) == 0:
            continue

        attributes = []  # type: List[Attribute]

        # NOTE (mristin):
        # We need to use integers as Attribute does not allow hashing, and we resort
        # to ``id(.)``.
        attribute_set = set()  # type: Set[int]

        for supertype in entity.supertypes:
            for attribute in supertype.attributes:
                attribute_id = id(attribute)

                if attribute_id in attribute_set:
                    continue

                attributes.append(attribute)
                attribute_set.add(attribute_id)

        attributes.extend(entity.attributes)

        attribute_by_name = dict()  # type: MutableMapping[str, Attribute]
        for attribute in attributes:
            conflict_attribute = attribute_by_name.get(attribute.name, None)
            if conflict_attribute is not None:

                conflict_attribute_description: str
                if conflict_attribute.specified_for is entity:
                    conflict_attribute_description = (
                        f"attribute {conflict_attribute.name!r}"
                    )
                else:
                    conflict_attribute_description = (
                        f"attribute {conflict_attribute.name!r} inherited from "
                        f"{conflict_attribute.specified_for.identifier}"
                    )

                attribute_description: str
                if attribute.specified_for is entity:
                    attribute_description = f"attribute {attribute.name!r}"
                else:
                    attribute_description = (
                        f"attribute {attribute.name!r} inherited from "
                        f"{attribute.specified_for.identifier}"
                    )

                errors.append(
                    f"The entity {entity.identifier!r} has an attribute conflict: "
                    f"{conflict_attribute_description} and {attribute_description}"
                )

            else:
                attribute_by_name[attribute.name] = attribute

        if len(errors) > 0:
            return bullet_points(errors)

        # noinspection PyProtectedMember
        entity._set_attributes(attributes)  # pylint: disable=protected-access

    return None


@ensure(
    lambda result: (result[0] is not None) ^ (result[1] is not None),
    "Either a result or an error",
)
def translate(
    parsed: parse.Schema,
) -> Tuple[Optional[Schema], Optional[NonEmptySequence[str]]]:
    """Translate the parsed AST of a schema to its intermediate representation."""
    errors = []  # type: List[str]

    # region Translate enumerations

    enumerations = []  # type: List[Enumeration]

    # NOTE (mristin):
    # We handle declared enumerations as a special case since we want to map them
    # somehow with a name instead of in-lining them.
    for type_declaration in parsed.type_declarations:
        if isinstance(type_declaration.type_selection, parse.EnumType):
            enumerations.append(
                Enumeration(
                    identifier=type_declaration.identifier,
                    values=type_declaration.type_selection.values,
                )
            )

    for type_declaration in parsed.type_declarations:
        if _specifies_nested_unnamed_enumeration(type_declaration.type_selection):
            raise NotImplementedError(
                f"We have not implemented handling of unnamed enumerations "
                f"appearing in type declaration {type_declaration.identifier!r}. "
                f"Please contact the developers if you need this feature."
            )

    # endregion

    # region Translate entities

    # NOTE (mristin):
    # We first create entities without translating the sub/supertypes and attributes
    # so that we can reference them.

    entities = [
        Entity(
            identifier=entity_declaration.identifier,
            # NOTE (mristin):
            # We have a chicken-and-egg problem here. We need to create entities and
            # reference them in subtype-of at the same time. At this point, we make
            # an empty list, but we will mutate it internally at the later stage, once
            # all the entity objects are created.
            supertypes=[],
            subtypes=[],
            descendant_concrete_entities=[],
            abstract=(
                isinstance(
                    entity_declaration.supertype_declaration, parse.AbstractSupertype
                )
                or (
                    isinstance(
                        entity_declaration.supertype_declaration, parse.SupertypeOf
                    )
                    and entity_declaration.supertype_declaration.abstract
                )
            ),
            # NOTE (mristin):
            # This list is just a placeholder here, and will be populated in the later
            # stage, once we created all the entity objects, so that we can reference
            # them.
            attributes=[],
            parsed=entity_declaration,
        )
        for entity_declaration in parsed.entity_declarations
    ]  # type: List[Entity]

    dereferencing_errors = _dereference_sub_and_supertypes_of_entities_in_situ(
        entities=entities
    )

    if dereferencing_errors is not None:
        errors.extend(dereferencing_errors)

    if len(errors) > 0:
        return None, NonEmptySequence(errors)

    # NOTE (mristin):
    # The entities still lack the attributes since we did not parse
    # the type declarations yet.

    # endregion

    # region Translate type declarations

    enumerations_by_id = {
        enumeration.identifier: enumeration for enumeration in enumerations
    }
    entities_by_id = {entity.identifier: entity for entity in entities}

    # NOTE (mristin):
    # We create the objects representing the declared types so that we could reference
    # them. At a later stage, we will properly set the underlying type definitions.

    declared_types = [
        DeclaredType(
            identifier=type_declaration.identifier,
            # NOTE (mristin):
            # This is just a dummy value which we will override at a later stage, once
            # we created all the declared types as objects that we can reference to.
            tajp=BooleanType(),
            parsed=type_declaration,
        )
        for type_declaration in parsed.type_declarations
        # NOTE (mristin):
        # We diverge here in the intermediate representation from the parse layer as we
        # treat type declarations of enumerations as first-class citizens instead of
        # treating them as type declaration.
        if not isinstance(type_declaration.type_selection, parse.EnumType)
    ]

    declared_types_by_id = {
        declared_type.identifier: declared_type for declared_type in declared_types
    }

    resolution_errors = _resolve_declared_types_in_situ(
        declared_types=declared_types,
        declared_types_by_id=declared_types_by_id,
        enumerations_by_id=enumerations_by_id,
        entities_by_id=entities_by_id,
    )

    if resolution_errors is not None:
        return None, NonEmptySequence(
            [
                f"There were one or more errors when resolving type declarations: "
                f"{bullet_points(resolution_errors)}"
            ]
        )

    # NOTE (mristin):
    # We just run a smoke test with topological sort to ensure that there are no errors.
    _, sort_error = _topologically_sorted_declared_types(declared_types)
    if sort_error is not None:
        return None, NonEmptySequence([sort_error])

    # endregion

    # region Translate entity attributes

    # NOTE (mristin):
    # We now have all the ingredients -- inlined type declarations, enumerations and
    # entity objects so that we can resolve the attributes.

    attribute_resolution_errors = _resolve_entity_attributes_in_situ(
        entities=entities,
        declared_types_by_id=declared_types_by_id,
        enumerations_by_id=enumerations_by_id,
        entities_by_id=entities_by_id,
    )

    if attribute_resolution_errors is not None:
        errors.extend(attribute_resolution_errors)

    if len(errors) > 0:
        return None, NonEmptySequence(errors)

    _stack_attributes_across_entity_hierarchy_in_situ(entities=entities)

    # endregion

    return (
        Schema(
            identifier=parsed.identifier,
            declared_types=declared_types,
            enumerations=enumerations,
            entities=entities,
            parsed=parsed,
        ),
        None,
    )


Type = Union[
    BinaryType,
    BooleanType,
    IntegerType,
    LogicalType,
    NumberType,
    RealType,
    StringType,
    ArrayType,
    BagType,
    ListType,
    SetType,
    SelectType,
    Enumeration,
    Entity,
    DeclaredType,
]

TypeWithoutDeclaredType = Union[
    BinaryType,
    BooleanType,
    IntegerType,
    LogicalType,
    NumberType,
    RealType,
    StringType,
    ArrayType,
    BagType,
    ListType,
    SetType,
    SelectType,
    Enumeration,
    Entity,
]
assert_union_without_excluded(
    original_union=Type, subset_union=TypeWithoutDeclaredType, excluded=[DeclaredType]
)

TypeWithoutSelectType = Union[
    BinaryType,
    BooleanType,
    IntegerType,
    LogicalType,
    NumberType,
    RealType,
    StringType,
    ArrayType,
    BagType,
    ListType,
    SetType,
    Enumeration,
    Entity,
    DeclaredType,
]
assert_union_without_excluded(
    original_union=Type, subset_union=TypeWithoutSelectType, excluded=[SelectType]
)

TypeWithoutSelectAndDeclaredType = Union[
    BinaryType,
    BooleanType,
    IntegerType,
    LogicalType,
    NumberType,
    RealType,
    StringType,
    ArrayType,
    BagType,
    ListType,
    SetType,
    Enumeration,
    Entity,
]
assert_union_without_excluded(
    original_union=Type,
    subset_union=TypeWithoutSelectAndDeclaredType,
    excluded=[SelectType, DeclaredType],
)
