# SPDX-FileCopyrightText: 2025 aas-smt-from-ifc AUTHORS
#
# SPDX-License-Identifier: MIT

"""Translate the schema into ifcopenshell to aas_core conversion code."""

from typing import cast, List, Sequence, Callable, Tuple
from icontract import require, ensure
from aas_smt_from_ifc import ir, smt
from aas_smt_from_ifc.common import assert_never

I = "    "
II = I * 2
III = I * 3
IIII = I * 4
IIIII = I * 5
IIIIII = I * 6


class _Rstripped(str):
    """
    Represent a block of text without trailing whitespace.
    The block can be both single-line or multi-line.
    """

    @require(
        lambda block: not block.endswith("\n")
        and not block.endswith(" ")
        and not block.endswith("\t")
    )
    def __new__(cls, block: str) -> "_Rstripped":
        return cast(_Rstripped, block)


def _is_stripped(text: str) -> bool:
    """Check that the ``text`` does not have leading and trailing whitespace."""
    return (
        not text.startswith("\n")
        and not text.startswith(" ")
        and not text.startswith("\t")
    ) and (
        not text.endswith("\n") and not text.endswith(" ") and not text.endswith("\t")
    )


class _Stripped(_Rstripped):
    """
    Represent a block of text without leading and trailing whitespace.
    The block of text can be both single-line and multi-line.
    """

    @require(lambda block: _is_stripped(block))
    def __new__(cls, block: str) -> "_Stripped":
        return cast(_Stripped, block)


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


def _generate_element_class_to_key_type() -> _Stripped:
    entries = []
    for cls, key_type in smt.AAS_KEY_TYPES_BY_CLASS.items():
        entries.append(f"aas_types.{cls.__name__}: aas_types.KeyTypes.{key_type.name}")
    entries_joined = ",\n".join(entries)
    return _Stripped(
        f"""\
_AAS_KEY_TYPES_BY_CLASS = {{
{I}{_indent_but_first_line(entries_joined, I)}
}}"""
    )


def _generate_entity_to_submodel_element_collection(entity: ir.Entity) -> _Stripped:
    return _Stripped(
        f'''\
def _{entity.identifier}_to_submodel_element_collection(
{I}instance: ifcopenshell.entity_instance,
{I}identify: Callable[[ifcopenshell.entity_instance], str],
{I}logger: Optional[Logger]
) -> aas_types.SubmodelElementCollection:
{I}"""
{I}Convert an instance of {entity.identifier}
{I}to a submodel element collection.

{I}The function ``identify`` determines the global identifiers of entities mapped
{I}to submodels.

{I}If ``logger`` is supplied, the violations of the schema will be written to it,
{I}and the translation will continue. Otherwise, a ``ValueError`` will be
{I}immediately raised.
{I}"""
{I}if not instance.is_a({repr(entity.identifier)}):
{II}raise ValueError(
{III}f"Expected an instance of {entity.identifier}, "
{III}f"but got an instance of {{instance.is_a()}}"
{II})
{I}declaration = _ENTITY_DECLARATION_MAP[instance.is_a()]
{I}return _to_submodel_element_collection_by_declaration(
{II}instance=instance,
{II}identify=identify,
{II}declaration=declaration,
{II}logger=logger
{I})'''
    )


def _generate_to_submodel_element_collection_map(
    entities_mapped_to_submodel_element_collections: Sequence[ir.Entity],
) -> _Stripped:
    entries = [
        (
            repr(entity.identifier),
            f"_{entity.identifier}_to_submodel_element_collection",
        )
        for entity in entities_mapped_to_submodel_element_collections
    ]

    entries_joined = ",\n".join(
        f"""\
{key}: (
{I}{_indent_but_first_line(value, I)}
)"""
        for key, value in entries
    )

    return _Stripped(
        f"""\
# fmt: off
_TO_SUBMODEL_ELEMENT_COLLECTION_MAP: Mapping[
{I}str,
{I}Callable[
{II}[
{III}ifcopenshell.entity_instance,
{III}Callable[[ifcopenshell.entity_instance], str],
{III}Optional[Logger]
{II}],
{II}aas_types.SubmodelElementCollection
{I}]
] = {{
{I}{_indent_but_first_line(entries_joined, I)}
}}
# fmt: on"""
    )


def _generate_entity_to_submodel(
    entity: ir.Entity,
) -> _Stripped:
    return _Stripped(
        f'''\
def _{entity.identifier}_to_submodel(
{I}instance: ifcopenshell.entity_instance,
{I}identify: Callable[[ifcopenshell.entity_instance], str],
{I}logger: Optional[Logger]
) -> aas_types.Submodel:
{I}"""
{I}Convert an instance of {entity.identifier} to a submodel element collection.

{I}The function ``identify`` determines the global identifiers of entities mapped
{I}to submodels.

{I}If ``logger`` is supplied, the violations of the schema will be written to it,
{I}and the translation will continue. Otherwise, a ``ValueError`` will be immediately
{I}raised.
{I}"""
{I}if not instance.is_a({repr(entity.identifier)}):
{II}raise ValueError(
{III}f"Expected an instance of {entity.identifier}, "
{III}f"but got an instance of {{instance.is_a()}}"
{II})
{I}declaration = _ENTITY_DECLARATION_MAP[instance.is_a()]
{I}return _to_submodel_by_declaration(
{II}instance=instance,
{II}identify=identify,
{II}declaration=declaration,
{II}logger=logger
{I})'''
    )


def _generate_to_submodel_map(
    entities_mapped_to_submodels: Sequence[ir.Entity],
) -> _Stripped:
    entries = [
        (repr(entity.identifier), f"_{entity.identifier}_to_submodel")
        for entity in entities_mapped_to_submodels
    ]
    entries_joined = ",\n".join(f"{key}: {value}" for key, value in entries)
    return _Stripped(
        f"""\
_TO_SUBMODEL_MAP: Mapping[
{I}str,
{I}Callable[
{II}[
{III}ifcopenshell.entity_instance,
{III}Callable[[ifcopenshell.entity_instance], str],
{III}Optional[Logger]
{II}],
{II}aas_types.Submodel
{I}]
] = {{
{I}{_indent_but_first_line(entries_joined, I)}
}}"""
    )


def _generate_translate(
    default_identify_expr: _Stripped = _Stripped(
        "lambda an_instance: an_instance.GlobalId"
    ),
) -> List[_Stripped]:
    return [
        _Stripped(
            f'''\
def translate(
{I}instance: ifcopenshell.entity_instance,
{I}identify: Callable[
{II}[ifcopenshell.entity_instance],
{II}str
{I}] = {default_identify_expr},
{I}logger: Optional[Logger] = None
) -> Union[aas_types.Submodel, aas_types.SubmodelElementCollection]:
{I}"""
{I}Translate the instance of an IFC entity to AAS submodel or element collection.

{I}Some entities are mapped to submodels, and referenced, while others are
{I}mapped to submodel element collections and nested within the submodels.

{I}The function ``identify`` determines the global identifier of the entity instance
{I}which are mapped to submodels.

{I}If ``logger`` is supplied, the violations of the schema will be written to it,
{I}and the translation will continue. Otherwise, a ``ValueError`` will be immediately
{I}raised.
{I}"""
{I}entity_name = instance.is_a()
{I}concrete_to: Optional[
{II}Union[
{III}Callable[
{IIII}[
{IIIII}ifcopenshell.entity_instance,
{IIIII}Callable[[ifcopenshell.entity_instance], str],
{IIIII}Optional[Logger]
{IIII}],
{IIII}aas_types.Submodel
{III}],
{III}Callable[
{IIII}[
{IIIII}ifcopenshell.entity_instance,
{IIIII}Callable[[ifcopenshell.entity_instance], str],
{IIIII}Optional[Logger]
{IIII}],
{IIII}aas_types.SubmodelElementCollection
{III}]
{II}]
{I}]
{I}concrete_to = _TO_SUBMODEL_MAP.get(entity_name, None)
{I}if concrete_to is None:
{II}concrete_to = _TO_SUBMODEL_ELEMENT_COLLECTION_MAP.get(entity_name, None)
{I}if concrete_to is None:
{II}raise ValueError(
{III}f"We do not know how to map an instance of an entity {{entity_name}} "
{III}f"to its AAS correspondent."
{II})
{I}return concrete_to(instance, identify, logger)'''
        ),
        _Stripped(
            f'''\
def must_translate_to_submodel_element_collection(
{I}instance: ifcopenshell.entity_instance,
{I}identify: Callable[
{II}[ifcopenshell.entity_instance],
{II}str
{I}] = {default_identify_expr},
{I}logger: Optional[Logger] = None
) -> aas_types.SubmodelElementCollection:
{I}"""
{I}Translate the instance of an IFC entity to an AAS submodel element collection.

{I}Some entities are mapped to submodels, and referenced, while others are
{I}mapped to submodel element collections and nested within the submodels.

{I}When you use this function, it is assumed that you are certain that the entity
{I}should be mapped to a submodel element collection. If that is not the case,
{I}a ``ValueError`` will be thrown.

{I}The function ``identify`` determines the global identifier of the entity instance
{I}which are mapped to submodels.

{I}If ``logger`` is supplied, the violations of the schema will be written to it,
{I}and the translation will continue. Otherwise, a ``ValueError`` will be immediately
{I}raised.
{I}"""
{I}entity_name = instance.is_a()
{I}if entity_name in _TO_SUBMODEL_MAP:
{II}raise ValueError(
{III}f"You are trying to map an instance of {{entity_name}} to "
{III}f"a submodel element collection, but it must be mapped to "
{III}f"a submodel element collection."
{II})
{I}concrete_to = _TO_SUBMODEL_ELEMENT_COLLECTION_MAP.get(entity_name, None)
{I}if concrete_to is None:
{II}raise ValueError(
{III}f"We do not know how to map an instance of the entity {{entity_name}} "
{III}f"to its AAS correspondent."
{II})
{I}return concrete_to(instance, identify, logger)'''
        ),
    ]


def _generate_structural_type_blocks() -> List[_Stripped]:
    return [
        _Stripped(
            f'''\
class _StructuralType(abc.ABC):
{I}"""Match the type of a value at runtime and translate it to an element."""
{I}@abc.abstractmethod
{I}def match(self, value: Any) -> bool:
{II}"""Check whether the ``value`` conforms to the type."""
{II}raise NotImplementedError()

{I}@abc.abstractmethod
{I}def translate(
{II}self,
{II}value: Any,
{II}identify: Callable[[ifcopenshell.entity_instance], str]
{I}) -> aas_types.SubmodelElement:
{II}"""
{II}Translate the ``value`` to the corresponding element.

{II}The function ``identify`` determines the global identifiers of entities mapped
{II}to submodels.
{II}"""
{II}raise NotImplementedError()'''
        ),
        _Stripped(
            f'''\
class _Boolean(_StructuralType):
{I}def match(self, value: Any) -> bool:
{II}if hasattr(value, "wrappedValue"):
{III}value = value.wrappedValue
{II}return isinstance(value, bool)

{I}def translate(
{II}self,
{II}value: Any,
{II}identify: Callable[[ifcopenshell.entity_instance], str]
{I}) -> aas_types.SubmodelElement:
{II}if hasattr(value, "wrappedValue"):
{III}value = value.wrappedValue

{II}assert isinstance(value, bool)
{II}return aas_types.Property(

{III}value_type=aas_types.DataTypeDefXSD.BOOLEAN,
{III}value=_bool_as_xs_bool_value(value)
{II})

{I}def __str__(self) -> str:
{II}return "BOOLEAN"'''
        ),
        _Stripped(
            f'''\
class _Integer(_StructuralType):
{I}def match(self, value: Any) -> bool:
{II}if hasattr(value, "wrappedValue"):
{III}value = value.wrappedValue

{II}return isinstance(value, int)

{I}def translate(
{II}self,
{II}value: Any,
{II}identify: Callable[[ifcopenshell.entity_instance], str]
{I}) -> aas_types.SubmodelElement:
{II}if hasattr(value, "wrappedValue"):
{III}value = value.wrappedValue

{II}assert isinstance(value, int)
{II}return aas_types.Property(
{III}value_type=aas_types.DataTypeDefXSD.LONG,
{III}value=str(value)
{II})

{I}def __str__(self) -> str:
{II}return "INTEGER"'''
        ),
        _Stripped(
            f'''\
class _Real(_StructuralType):
{I}def match(self, value: Any) -> bool:
{II}if hasattr(value, "wrappedValue"):

{III}value = value.wrappedValue
{II}return isinstance(value, (int, float))

{I}def translate(
{II}self,
{II}value: Any,
{II}identify: Callable[[ifcopenshell.entity_instance], str]
{I}) -> aas_types.SubmodelElement:
{II}if hasattr(value, "wrappedValue"):
{III}value = value.wrappedValue

{II}assert isinstance(value, (int, float))
{II}return aas_types.Property(
{III}value_type=aas_types.DataTypeDefXSD.DOUBLE,
{III}value=str(value)
{II})

{I}def __str__(self) -> str:
{II}return "REAL"'''
        ),
        _Stripped(
            f'''\
class _Number(_StructuralType):
{I}def match(self, value: Any) -> bool:
{II}if hasattr(value, "wrappedValue"):
{III}value = value.wrappedValue

{II}return isinstance(value, (int, float))

{I}def translate(
{II}self,
{II}value: Any,
{II}identify: Callable[[ifcopenshell.entity_instance], str]
{I}) -> aas_types.SubmodelElement:
{II}if hasattr(value, "wrappedValue"):
{III}value = value.wrappedValue
{II}assert isinstance(value, (int, float))
{II}return _number_to_collection(value)

{I}def __str__(self) -> str:
{II}return "NUMBER"'''
        ),
        _Stripped(
            f'''\
class _Logical(_StructuralType):
{I}def match(self, value: Any) -> bool:
{II}if hasattr(value, "wrappedValue"):
{III}value = value.wrappedValue
{II}return (
{III}value is None
{III}or isinstance(value, bool)
{III}or (isinstance(value, str) and value == "UNKNOWN")
{II})

{I}def translate(
{II}self,
{II}value: Any,
{II}identify: Callable[[ifcopenshell.entity_instance], str]
{I}) -> aas_types.SubmodelElement:
{II}if hasattr(value, "wrappedValue"):
{III}value = value.wrappedValue
{II}assert (
{III}value is None
{III}or isinstance(value, bool)
{III}or (isinstance(value, str) and value == "UNKNOWN")
{II})
{II}return aas_types.Property(
{III}semantic_id=_REFERENCE_TO_LOGICAL_DROP_IN,
{III}value_type=aas_types.DataTypeDefXSD.STRING,
{III}value=_logical_as_str(value)
{II})

{I}def __str__(self) -> str:
{II}return "LOGICAL"'''
        ),
        _Stripped(
            """\
_BASE64_RE = re.compile(r'^[A-Za-z0-9+/]+={{0,2}}$')"""
        ),
        _Stripped(
            f'''\
class _Binary(_StructuralType):
{I}def __init__(
{II}self,
{II}min_length: Optional[int] = None,
{II}max_length: Optional[int] = None
{I}) -> None:
{II}self.min_length = min_length
{II}self.max_length = max_length

{I}def match(self, value: Any) -> bool:
{II}# NOTE (mristin):
{II}# The IFC Open Shell often does not distinguish between base64-encoded
{II}# strings and bytes, so we have to handle both here.
{II}# This might lead to confusion -- if there is an explicit STRING holding
{II}# a base64-encoded value, we can not tell it apart from BINARY.
{II}if hasattr(value, "wrappedValue"):
{III}value = value.wrappedValue
{II}if isinstance(value, str):
{III}if len(value) % 4 != 0:
{IIII}return False
{III}if _BASE64_RE.match(value) is None:
{IIII}return False
{III}length = 3 * (len(value) // 4) - value.count("=")
{III}if self.min_length is not None and length < self.min_length:
{IIII}return False
{III}if self.max_length is not None and length > self.max_length:
{IIII}return False
{III}return True
{II}elif isinstance(value, bytes):
{III}if self.min_length is not None and len(value) < self.min_length:
{IIII}return False
{III}if self.max_length is not None and len(value) > self.max_length:
{IIII}return False
{III}return True
{II}else:
{III}raise ValueError("Expected either str or bytes, but got: {{value}}")

{I}def translate(
{II}self,
{II}value: Any,
{II}identify: Callable[[ifcopenshell.entity_instance], str]
{I}) -> aas_types.SubmodelElement:
{II}if hasattr(value, "wrappedValue"):
{III}value = value.wrappedValue
{II}assert isinstance(value, (str, bytes))
{II}return _binary_to_property(value)

{I}def __str__(self) -> str:
{II}if self.min_length is None and self.max_length is None:
{III}return "BINARY"
{II}if self.min_length == self.max_length:
{III}return f"BINARY ({{self.max_length}}) FIXED"
{II}if self.min_length is None and self.max_length is not None:
{III}return f"BINARY ({{self.max_length}})"
{II}return f"BINARY ({{self.min_length}}, ?)"'''
        ),
        _Stripped(
            f'''\
class _String(_StructuralType):
{I}def __init__(
{II}self,
{II}min_length: Optional[int] = None,
{II}max_length: Optional[int] = None,
{II}choice: Optional[List[str]] = None
{I}) -> None:
{II}self.min_length = min_length
{II}self.max_length = max_length
{II}self.choice_set = set(choice) if choice is not None else None

{I}def match(self, value: Any) -> bool:
{II}if hasattr(value, "wrappedValue"):
{III}value = value.wrappedValue

{II}if not isinstance(value, str):
{III}return False

{II}if self.min_length is not None and len(value) < self.min_length:
{III}return False

{II}if self.max_length is not None and len(value) > self.max_length:
{III}return False

{II}if self.choice_set is not None and value not in self.choice_set:
{III}return False

{II}return True

{I}def translate(
{II}self,
{II}value: Any,
{II}identify: Callable[[ifcopenshell.entity_instance], str]
{I}) -> aas_types.SubmodelElement:
{II}if hasattr(value, "wrappedValue"):
{III}value = value.wrappedValue
{II}return aas_types.Property(
{III}value_type=aas_types.DataTypeDefXSD.STRING,
{III}value=value
{II})

{I}def __str__(self) -> str:
{II}if self.min_length is None and self.max_length is None:
{III}return "STRING"
{II}if self.min_length == self.max_length:
{III}return f"STRING ({{self.max_length}}) FIXED"
{II}if self.min_length is None and self.max_length is not None:
{III}return f"STRING ({{self.max_length}})"
{II}return f"STRING ({{self.min_length}}, ?)"'''
        ),
        _Stripped(
            f"""\
def _type_value_list_element_from_of_structural_type(
{I}of: "_StructuralTypeUnion"
) -> aas_types.AASSubmodelElements:
{I}while isinstance(of, _DeclaredType):
{II}of = of.structural_type
{I}assert not isinstance(of, _DeclaredType)
{I}if isinstance(
{II}of,
{II}(_Boolean, _Logical, _Integer, _Real, _Binary, _String)
{I}):
{II}type_value_list_element = aas_types.AASSubmodelElements.PROPERTY
{I}elif isinstance(of, _Number):
{II}type_value_list_element = (
{III}aas_types.AASSubmodelElements.SUBMODEL_ELEMENT_COLLECTION
{II})
{I}elif isinstance(
{II}of,
{II}(_Array, _Bag, _List, _Set)
{I}):
{II}type_value_list_element = (
{III}aas_types.AASSubmodelElements.SUBMODEL_ELEMENT_LIST
{II})
{I}elif isinstance(of, _Select):
{II}type_value_list_element = (
{III}aas_types.AASSubmodelElements.SUBMODEL_ELEMENT_COLLECTION
{II})
{I}elif isinstance(of, _Entity):
{II}if of.identifier in _TO_SUBMODEL_MAP:
{III}type_value_list_element = (
{IIII}aas_types.AASSubmodelElements.REFERENCE_ELEMENT
{III})
{II}elif of.identifier in _TO_SUBMODEL_ELEMENT_COLLECTION_MAP:
{III}type_value_list_element = (
{IIII}aas_types.AASSubmodelElements.SUBMODEL_ELEMENT_COLLECTION
{III})
{II}else:
{III}raise ValueError(
{IIII}f"Unexpected instance of entity {{of.identifier}}"
{III})
{I}elif isinstance(of, _Enumeration):
{II}type_value_list_element = aas_types.AASSubmodelElements.PROPERTY
{I}else:
{II}assert_never(of)
{I}return type_value_list_element"""
        ),
        _Stripped(
            f"""\
def _value_type_list_element_from_of_structural_type(
{I}of: "_StructuralTypeUnion"
) -> Optional[aas_types.DataTypeDefXSD]:
{I}while isinstance(of, _DeclaredType):
{II}of = of.structural_type
{I}assert not isinstance(of, _DeclaredType)
{I}if isinstance(of, _Boolean):
{II}return aas_types.DataTypeDefXSD.BOOLEAN
{I}elif isinstance(of, _Logical):
{II}return aas_types.DataTypeDefXSD.STRING
{I}elif isinstance(of, _Integer):
{II}return aas_types.DataTypeDefXSD.LONG
{I}elif isinstance(of, _Real):
{II}return aas_types.DataTypeDefXSD.DOUBLE
{I}elif isinstance(of, _Binary):
{II}return aas_types.DataTypeDefXSD.BASE_64_BINARY
{I}elif isinstance(of, _String):
{II}return aas_types.DataTypeDefXSD.STRING
{I}elif isinstance(of, _Enumeration):
{II}return aas_types.DataTypeDefXSD.STRING
{I}else:
{II}return None"""
        ),
        _Stripped(
            f"""\
class _Array(_StructuralType):
{I}def __init__(
{II}self,
{II}of: "_StructuralTypeUnion",
{II}min_length: Optional[int] = None,
{II}max_length: Optional[int] = None,
{II}optional: bool = False
{I}) -> None:
{II}self.of = of
{II}self.min_length = min_length
{II}self.max_length = max_length
{II}self.optional = optional

{I}def match(self, value: Any) -> bool:
{II}if not isinstance(value, collections.abc.Sequence):
{III}return False

{II}if self.min_length is not None and len(value) < self.min_length:
{III}return False

{II}if self.max_length is not None and len(value) > self.max_length:
{III}return False

{II}if self.optional:
{III}if not all(item is None or self.of.match(item) for item in value):

{IIII}return False

{II}else:
{III}if not all(self.of.match(item) for item in value):
{IIII}return False

{II}return True

{I}def translate(
{II}self,
{II}value: Any,
{II}identify: Callable[[ifcopenshell.entity_instance], str]
{I}) -> aas_types.SubmodelElement:
{II}assert isinstance(value, collections.abc.Sequence)
{II}elements: Optional[List[aas_types.SubmodelElement]]
{II}if self.optional:
{III}elements = []
{III}for item in value:
{IIII}value_element = self.of.translate(item, identify)
{IIII}value_element.id_short = "value"
{IIII}elements.append(
{IIIII}aas_types.SubmodelElementCollection(
{IIIIII}value=[value_element]
{IIIII})
{IIII})
{II}else:
{III}elements = [
{IIII}self.of.translate(item, identify)
{IIII}for item in value
{III}]
{II}type_value_list_element: aas_types.AASSubmodelElements
{II}value_type_list_element: Optional[aas_types.DataTypeDefXSD] = None
{II}if self.optional:
{III}type_value_list_element = (
{IIII}aas_types.AASSubmodelElements.SUBMODEL_ELEMENT_COLLECTION
{III})
{II}else:
{III}type_value_list_element=(
{IIII}_type_value_list_element_from_of_structural_type(self.of)
{III})
{III}value_type_list_element=(
{IIII}_value_type_list_element_from_of_structural_type(self.of)
{III})
{II}return aas_types.SubmodelElementList(
{III}value=elements if len(elements) > 0 else None,
{III}type_value_list_element=type_value_list_element,
{III}value_type_list_element=value_type_list_element,
{III}order_relevant=True
{II})

{I}def __str__(self) -> str:
{II}optional = " OPTIONAL " if self.optional else ""
{II}if self.min_length is None and self.max_length is None:
{III}return f"ARRAY {{optional}}OF {{self.of}}"
{II}min_length = (
{III}str(self.min_length)
{III}if self.min_length is not None
{III}else "?"
{II})
{II}max_length = (
{III}str(self.max_length)
{III}if self.max_length is not None
{III}else "?"
{II})
{II}return (
{III}f"ARRAY [{{min_length}}:{{max_length}}] {{optional}}OF {{self.of}}"
{II})"""
        ),
        _Stripped(
            f"""\
class _Bag(_StructuralType):
{I}def __init__(
{II}self,
{II}of: "_StructuralTypeUnion",
{II}min_length: Optional[int] = None,
{II}max_length: Optional[int] = None,
{I}) -> None:
{II}self.of = of
{II}self.min_length = min_length
{II}self.max_length = max_length

{I}def match(self, value: Any) -> bool:
{II}if not isinstance(value, collections.abc.Sequence):
{III}return False

{II}if self.min_length is not None and len(value) < self.min_length:
{III}return False

{II}if self.max_length is not None and len(value) > self.max_length:
{III}return False

{II}if not all(self.of.match(item) for item in value):
{III}return False

{II}return True

{I}def translate(
{II}self,
{II}value: Any,
{II}identify: Callable[[ifcopenshell.entity_instance], str]
{I}) -> aas_types.SubmodelElement:
{II}assert isinstance(value, collections.abc.Sequence)
{II}elements: Optional[List[aas_types.SubmodelElement]]
{II}elements = [
{III}self.of.translate(item, identify)
{III}for item in value
{II}]
{II}return aas_types.SubmodelElementList(
{III}value=elements if len(elements) > 0 else None,
{III}type_value_list_element=(
{IIII}_type_value_list_element_from_of_structural_type(self.of)
{III}),
{III}value_type_list_element=(
{IIII}_value_type_list_element_from_of_structural_type(self.of)
{III}),
{III}order_relevant=False
{II})

{I}def __str__(self) -> str:
{II}if self.min_length is None and self.max_length is None:
{III}return f"BAG OF {{self.of}}"
{II}min_length = (
{III}str(self.min_length)
{III}if self.min_length is not None
{III}else "?"
{II})
{II}max_length = (
{III}str(self.max_length)
{III}if self.max_length is not None
{III}else "?"
{II})
{II}return (
{III}f"BAG [{{min_length}}:{{max_length}}] OF {{self.of}}"
{II})"""
        ),
        _Stripped(
            f"""\
class _List(_StructuralType):
{I}def __init__(
{II}self,
{II}of: "_StructuralTypeUnion",
{II}min_length: Optional[int] = None,
{II}max_length: Optional[int] = None,
{I}) -> None:
{II}self.of = of
{II}self.min_length = min_length
{II}self.max_length = max_length

{I}def match(self, value: Any) -> bool:
{II}if not isinstance(value, collections.abc.Sequence):
{III}return False
{II}if self.min_length is not None and len(value) < self.min_length:
{III}return False
{II}if self.max_length is not None and len(value) > self.max_length:
{III}return False
{II}if not all(self.of.match(item) for item in value):
{III}return False
{II}return True

{I}def translate(
{II}self,
{II}value: Any,
{II}identify: Callable[[ifcopenshell.entity_instance], str]
{I}) -> aas_types.SubmodelElement:
{II}assert isinstance(value, collections.abc.Sequence)
{II}elements: Optional[List[aas_types.SubmodelElement]]
{II}elements = [
{III}self.of.translate(item, identify)
{III}for item in value
{II}]
{II}return aas_types.SubmodelElementList(
{III}value=elements if len(elements) > 0 else None,
{III}type_value_list_element=(
{IIII}_type_value_list_element_from_of_structural_type(self.of)
{III}),
{III}value_type_list_element=(
{IIII}_value_type_list_element_from_of_structural_type(self.of)
{III}),
{III}order_relevant=True
{II})

{I}def __str__(self) -> str:
{II}if self.min_length is None and self.max_length is None:
{III}return f"LIST OF {{self.of}}"
{II}min_length = (
{III}str(self.min_length)
{III}if self.min_length is not None
{III}else "?"
{II})
{II}max_length = (
{III}str(self.max_length)
{III}if self.max_length is not None
{III}else "?"
{II})
{II}return (
{III}f"LIST [{{min_length}}:{{max_length}}] OF {{self.of}}"
{II})"""
        ),
        _Stripped(
            f"""\
class _Set(_StructuralType):
{I}def __init__(
{II}self,
{II}of: "_StructuralTypeUnion",
{II}min_length: Optional[int] = None,
{II}max_length: Optional[int] = None,
{I}) -> None:
{II}self.of = of
{II}self.min_length = min_length
{II}self.max_length = max_length

{I}def match(self, value: Any) -> bool:
{II}if not isinstance(value, collections.abc.Sequence):
{III}return False
{II}if self.min_length is not None and len(value) < self.min_length:
{III}return False
{II}if self.max_length is not None and len(value) > self.max_length:
{III}return False
{II}if not all(self.of.match(item) for item in value):
{III}return False
{II}return True

{I}def translate(
{II}self,
{II}value: Any,
{II}identify: Callable[[ifcopenshell.entity_instance], str]
{I}) -> aas_types.SubmodelElement:
{II}assert isinstance(value, collections.abc.Sequence)
{II}elements: Optional[List[aas_types.SubmodelElement]]
{II}elements = [
{III}self.of.translate(item, identify)
{III}for item in value
{II}]
{II}return aas_types.SubmodelElementList(
{III}value=elements if len(elements) > 0 else None,
{III}type_value_list_element=(
{IIII}_type_value_list_element_from_of_structural_type(self.of)
{III}),
{III}value_type_list_element=(
{IIII}_value_type_list_element_from_of_structural_type(self.of)
{III}),
{III}order_relevant=True
{II})

{I}def __str__(self) -> str:
{II}if self.min_length is None and self.max_length is None:
{III}return f"SET OF {{self.of}}"
{II}min_length = (
{III}str(self.min_length)
{III}if self.min_length is not None
{III}else "?"
{II})
{II}max_length = (
{III}str(self.max_length)
{III}if self.max_length is not None
{III}else "?"
{II})
{II}return (
{III}f"SET [{{min_length}}:{{max_length}}] OF {{self.of}}"
{II})"""
        ),
        _Stripped(
            f"""\
def _flatten_select_choice(
{I}choice: Sequence[Union["_DeclaredType", "_Entity", "_Enumeration"]]
) -> List[Union["_DeclaredType", "_Entity", "_Enumeration"]]:
{I}result = []  # type: List[Union["_DeclaredType", "_Entity", "_Enumeration"]]
{I}for selected_type in choice:
{II}resolved_type = selected_type  # type: "_StructuralTypeUnion"
{II}while isinstance(resolved_type, _DeclaredType):
{III}resolved_type = resolved_type.structural_type
{II}assert not isinstance(resolved_type, _DeclaredType)
{II}if not isinstance(resolved_type, _Select):
{III}result.append(selected_type)
{III}continue
{II}result.extend(_flatten_select_choice(resolved_type.choice))
{I}return result"""
        ),
        _Stripped(
            f'''\
class _Select(_StructuralType):
{I}def __init__(
{II}self,
{II}choice: Sequence[
{III}Union["_DeclaredType", "_Entity", "_Enumeration"]
{II}]
{I}) -> None:
{II}# NOTE (mristin):
{II}# We flatten here the selection to account for union of unions.
{II}# The selections are just another name for union types (a.k.a. sum types).
{II}self.choice = _flatten_select_choice(choice)

{I}def match(self, value: Any) -> bool:
{II}return any(
{III}selected_type.match(value)
{III}for selected_type in self.choice
{II})

{I}def translate(
{II}self,
{II}value: Any,
{II}identify: Callable[[ifcopenshell.entity_instance], str]
{I}) -> aas_types.SubmodelElement:
{II}for selected_type in self.choice:
{III}if selected_type.match(value):
{IIII}element = selected_type.translate(value, identify)
{IIII}element.id_short = "value"
{IIII}element.semantic_id=_model_reference(
{IIIII}[
{IIIIII}(aas_types.KeyTypes.SUBMODEL, _DROP_INS_IRI),
{IIIIII}(_AAS_KEY_TYPES_BY_CLASS[element.__class__], selected_type.identifier)
{IIIII}]
{IIII})
{IIII}return aas_types.SubmodelElementCollection(
{IIIII}value=[element]
{IIII})
{II}raise ValueError(
{III}f"None of the types in the select choice matched {{value}}"
{II})

{I}def __str__(self) -> str:
{II}entries_joined = ",\\n".join(
{III}str(selected_type)
{III}for selected_type in self.choice
{II})
{II}return f"SELECT({{entries_joined}})"'''
        ),
        _Stripped(
            f"""\
class _Entity(_StructuralType):
{I}def __init__(
{II}self,
{II}identifier: str
{I}) -> None:
{II}self.identifier = identifier

{I}def match(self, value: Any) -> bool:
{II}return (
{III}isinstance(value, ifcopenshell.entity_instance)
{III}and value.is_a(self.identifier)
{II})

{I}def translate(
{II}self,
{II}value: Any,
{II}identify: Callable[[ifcopenshell.entity_instance], str]
{I}) -> aas_types.SubmodelElement:
{II}assert (
{III}isinstance(value, ifcopenshell.entity_instance)
{III}and value.is_a(self.identifier)
{II})
{II}entity_name = value.is_a()

{II}if entity_name in _TO_SUBMODEL_MAP:
{III}return aas_types.ReferenceElement(
{IIII}value=_model_reference(
{IIIII}[(aas_types.KeyTypes.SUBMODEL, identify(value))]
{IIII})
{III})

{II}elif entity_name in _TO_SUBMODEL_ELEMENT_COLLECTION_MAP:
{III}return must_translate_to_submodel_element_collection(
{IIII}instance=value,
{IIII}identify=identify
{III})

{II}else:
{III}raise ValueError(
{IIII}f"We do not know how to map an instance of the entity {{entity_name}} "
{IIII}f"to its AAS correspondent."
{III})

{I}def __str__(self) -> str:
{II}return self.identifier"""
        ),
        _Stripped(
            f"""\
class _Enumeration(_StructuralType):
{I}def __init__(
{II}self,
{II}identifier: str,
{II}choice: Sequence[str]
{I}) -> None:
{II}self.identifier = identifier
{II}self.choice_set = set(choice)

{I}def match(self, value: Any) -> bool:
{II}return isinstance(value, str) and value in self.choice_set

{I}def translate(
{II}self,
{II}value: Any,
{II}identify: Callable[[ifcopenshell.entity_instance], str]
{I}) -> aas_types.SubmodelElement:
{II}assert isinstance(value, str)

{II}return aas_types.Property(
{III}semantic_id=aas_types.Reference(
{IIII}type=aas_types.ReferenceTypes.MODEL_REFERENCE,
{IIII}keys=[
{IIIII}aas_types.Key(
{IIIIII}type=aas_types.KeyTypes.SUBMODEL,
{IIIIII}value=_DROP_INS_IRI
{IIIII}),
{IIIII}aas_types.Key(
{IIIIII}type=aas_types.KeyTypes.PROPERTY,
{IIIIII}value=self.identifier
{IIIII})
{IIII}]
{III}),
{II}value_type=aas_types.DataTypeDefXSD.STRING,
{II}value=value
{II})

{I}def __str__(self) -> str:
{II}return self.identifier"""
        ),
        _Stripped(
            f"""\
class _DeclaredType(_StructuralType):
{I}def __init__(
{II}self,
{II}identifier: str,
{II}structural_type: "_StructuralTypeUnion"
{I}) -> None:
{II}self.identifier = identifier
{II}self.structural_type = structural_type

{I}def match(self, value: Any) -> bool:
{II}return self.structural_type.match(value)

{I}def translate(
{II}self,
{II}value: Any,
{II}identify: Callable[[ifcopenshell.entity_instance], str]
{I}) -> aas_types.SubmodelElement:
{II}return self.structural_type.translate(value, identify)

{I}def __str__(self) -> str:
{II}return self.identifier"""
        ),
        _Stripped(
            f"""\
_StructuralTypeUnion = Union[
{I}_Boolean,
{I}_Logical,
{I}_Integer,
{I}_Real,
{I}_Number,
{I}_Binary,
{I}_String,
{I}_Array,
{I}_Bag,
{I}_List,
{I}_Set,
{I}_Select,
{I}_Entity,
{I}_Enumeration,
{I}_DeclaredType
]"""
        ),
        _Stripped(
            f"""\
class _Attribute:
{I}def __init__(
{II}self,
{II}name: str,
{II}structural_type: _StructuralTypeUnion,
{II}optional: bool = False,
{I}) -> None:
{II}self.name = name
{II}self.structural_type = structural_type
{II}self.optional = optional"""
        ),
        _Stripped(
            f"""\
class _EntityDeclaration:
{I}def __init__(
{II}self,
{II}identifier: str,
{II}attributes: List[_Attribute]
{I}) -> None:
{II}self.identifier = identifier
{II}self.attributes = attributes"""
        ),
    ]


def _generate_enumeration_map(enumerations: Sequence[ir.Enumeration]) -> _Stripped:
    entries = []  # type: List[Tuple[_Stripped, _Stripped]]
    for enumeration in enumerations:
        literals_joined = ",\n".join(repr(literal) for literal in enumeration.values)
        entries.append(
            (
                _Stripped(repr(enumeration.identifier)),
                _Stripped(
                    f"""\
_Enumeration(
{I}identifier={repr(enumeration.identifier)},
{I}choice=[
{II}{_indent_but_first_line(literals_joined, II)}
{I}]
)"""
                ),
            )
        )
    entries_joined = ",\n".join(f"{key}: {value}" for key, value in entries)
    return _Stripped(
        f"""\
_ENUMERATION_MAP: Final[Mapping[str, _Enumeration]] = {{
{I}{_indent_but_first_line(entries_joined, I)}
}}"""
    )


def _generate_structural_type_expr_for_entity(
    entity: ir.Entity, declared_type_map_expr: str
) -> _Stripped:
    # NOTE (mristin):
    # If there are multiple concrete descendants, we define the structural type
    # as a selection, due to the limitations of the submodel template language
    # which forces a closed-world principle on us.
    if len(entity.descendant_concrete_entities) > 0:
        select_identifier = f"{entity.identifier}_select"

        if len(select_identifier) > 30:
            return _Stripped(
                f"""\
{declared_type_map_expr}[
{I}{repr(select_identifier)}
]"""
            )
        else:
            return _Stripped(f"{declared_type_map_expr}[{repr(select_identifier)}]")

    else:
        assert not entity.abstract, (
            f"Unexpected abstract entity {entity.identifier!r} with "
            f"no concrete descendants"
        )
        return _Stripped(f"_Entity(identifier={repr(entity.identifier)})")


def _generate_structural_type_expr(
    tajp: ir.Type, declared_type_map_expr: str = "_DECLARED_TYPE_MAP"
) -> _Stripped:
    if isinstance(tajp, ir.BooleanType):
        return _Stripped("_Boolean()")
    elif isinstance(tajp, ir.LogicalType):
        return _Stripped("_Logical()")
    elif isinstance(tajp, ir.IntegerType):
        return _Stripped("_Integer()")
    elif isinstance(tajp, ir.RealType):
        return _Stripped("_Real()")
    elif isinstance(tajp, ir.NumberType):
        return _Stripped("_Number()")
    elif isinstance(tajp, ir.BinaryType):
        kwargs = []
        if tajp.min_length is not None:
            kwargs.append(f"min_length={tajp.min_length}")
        if tajp.max_length is not None:
            kwargs.append(f"max_length={tajp.max_length}")
        if len(kwargs) == 0:
            return _Stripped("_Binary()")
        kwargs_joined = ", ".join(kwargs)
        return _Stripped(f"_Binary({kwargs_joined})")
    elif isinstance(tajp, ir.StringType):
        kwargs = []
        if tajp.min_length is not None:
            kwargs.append(f"min_length={tajp.min_length}")
        if tajp.max_length is not None:
            kwargs.append(f"max_length={tajp.max_length}")
        if tajp.choice is not None:
            choice_joined = ",\n".join(repr(literal) for literal in tajp.choice)
            kwargs.append(
                f"""\
choice=[
{I}{_indent_but_first_line(choice_joined, I)}
]"""
            )
        if len(kwargs) == 0:
            return _Stripped("_String()")
        kwargs_joined = ", ".join(kwargs)
        return _Stripped(
            f"""\
_String(
{I}{_indent_but_first_line(kwargs_joined, I)}
)"""
        )
    elif isinstance(tajp, (ir.ArrayType, ir.BagType, ir.ListType, ir.SetType)):
        items_structural_type = _generate_structural_type_expr(
            tajp=tajp.items, declared_type_map_expr=declared_type_map_expr
        )
        kwargs = [f"of={items_structural_type}"]
        if tajp.min_length is not None:
            kwargs.append(f"min_length={tajp.min_length}")
        if tajp.max_length is not None:
            kwargs.append(f"max_length={tajp.max_length}")
        if isinstance(tajp, ir.ArrayType):
            if tajp.optional:
                kwargs.append("optional=True")
        kwargs_joined = ",\n".join(kwargs)
        aggregation_cls: str
        if isinstance(tajp, ir.ArrayType):
            aggregation_cls = "_Array"
        elif isinstance(tajp, ir.BagType):
            aggregation_cls = "_Bag"
        elif isinstance(tajp, ir.ListType):
            aggregation_cls = "_List"
        elif isinstance(tajp, ir.SetType):
            aggregation_cls = "_Set"
        else:
            # noinspection PyTypeChecker
            assert_never(tajp)
        return _Stripped(
            f"""\
{aggregation_cls}(
{I}{_indent_but_first_line(kwargs_joined, I)}
)"""
        )
    elif isinstance(tajp, ir.SelectType):
        choice = []  # type: List[str]
        for selected_type in tajp.types:
            if isinstance(selected_type, ir.Enumeration):
                choice.append(f"_ENUMERATION_MAP[{repr(selected_type.identifier)}]")
            elif isinstance(selected_type, ir.Entity):
                choice.append(
                    _generate_structural_type_expr_for_entity(
                        entity=selected_type,
                        declared_type_map_expr=declared_type_map_expr,
                    )
                )
            elif isinstance(selected_type, ir.DeclaredType):
                choice.append(
                    f"{declared_type_map_expr}[{repr(selected_type.identifier)}]"
                )
            else:
                # noinspection PyTypeChecker
                assert_never(selected_type)
        choice_joined = ",\n".join(choice)
        return _Stripped(
            f"""\
_Select(
{I}choice=[
{II}{_indent_but_first_line(choice_joined, II)}
{I}]
)"""
        )
    elif isinstance(tajp, ir.Entity):
        return _generate_structural_type_expr_for_entity(
            entity=tajp, declared_type_map_expr=declared_type_map_expr
        )
    elif isinstance(tajp, ir.Enumeration):
        return _Stripped(f"_ENUMERATION_MAP[{repr(tajp.identifier)}]")
    elif isinstance(tajp, ir.DeclaredType):
        if len(tajp.identifier) > 30:
            return _Stripped(
                f"""\
{declared_type_map_expr}[
{I}{repr(tajp.identifier)}
]"""
            )
        else:
            return _Stripped(f"{declared_type_map_expr}[{repr(tajp.identifier)}]")
    else:
        # noinspection PyTypeChecker
        assert_never(tajp)


# fmt: off
@require(
    lambda entities_with_selection:
    all(
        len(entity.descendant_concrete_entities) > 0
        for entity in entities_with_selection
    )
)
# fmt: on
def _generate_declared_type_map(
    declared_types_topologically_sorted: Sequence[ir.DeclaredType],
    entities_with_selection: Sequence[ir.Entity],
) -> List[_Stripped]:
    statements = [
        _Stripped(
            """\
declared_type_map: MutableMapping[str, "_DeclaredType"] = dict()"""
        )
    ]  # type: List[_Stripped]
    # NOTE (mristin):
    # We represent the entities with concrete descendant entities as select types
    # (a.k.a. sum types, union types). To avoid repetition, we introduce them as
    # declared types.
    #
    # We have to introduce them before the actual declared types as the declared
    # types might depend on entities.
    for entity in entities_with_selection:
        concrete_entities = []
        if not entity.abstract:
            concrete_entities.append(entity)
        concrete_entities.extend(entity.descendant_concrete_entities)
        entity_exprs = [
            f"_Entity(identifier={repr(entity.identifier)})"
            for entity in concrete_entities
        ]
        entity_exprs_joined = ",\n".join(entity_exprs)
        select_expr = _Stripped(
            f"""\
_Select(
{I}choice=[
{II}{_indent_but_first_line(entity_exprs_joined, II)}
{I}]
)"""
        )
        select_key = f"{entity.identifier}_select"
        statements.append(
            _Stripped(
                f"""\
declared_type_map[{repr(select_key)}] = _DeclaredType(
{I}identifier={repr(select_key)},
{I}structural_type={_indent_but_first_line(select_expr, I)}
)"""
            )
        )
    for declared_type in declared_types_topologically_sorted:
        structural_type_expr = _generate_structural_type_expr(
            tajp=declared_type.tajp, declared_type_map_expr="declared_type_map"
        )
        statements.append(
            _Stripped(
                f"""\
declared_type_map[{repr(declared_type.identifier)}] = _DeclaredType(
{I}identifier={repr(declared_type.identifier)},
{I}structural_type={_indent_but_first_line(structural_type_expr, I)}
)"""
            )
        )
    statements_joined = "\n\n".join(statements)
    return [
        _Stripped(
            f"""\
def _construct_declared_type_map() -> Mapping[str, "_DeclaredType"]:
{I}{_indent_but_first_line(statements_joined, I)}
{I}return declared_type_map"""
        ),
        _Stripped(
            f"""\
_DECLARED_TYPE_MAP: Final[Mapping[str, "_DeclaredType"]] = (
{I}_construct_declared_type_map()
)"""
        ),
    ]


# fmt: off
@require(
    lambda entities:
    all(not entity.abstract for entity in entities),
    "Only concrete entities are declared since we only translate "
    "concrete entities at runtime."
)
# fmt: on
def _generate_entity_declaration_map(entities: Sequence[ir.Entity]) -> _Stripped:
    entries = []  # type: List[Tuple[_Stripped, _Stripped]]
    for entity in entities:
        attribute_exprs = []
        for attribute in entity.attributes:
            kwargs = [
                f"name={repr(attribute.name)}",
                f"structural_type={_generate_structural_type_expr(attribute.tajp)}",
            ]
            if attribute.optional:
                kwargs.append("optional=True")
            kwargs_joined = ",\n".join(kwargs)
            attribute_exprs.append(
                f"""\
_Attribute(
{I}{_indent_but_first_line(kwargs_joined, I)}
)"""
            )
        attribute_exprs_joined = ",\n".join(attribute_exprs)

        attributes_value = (
            "[]"
            if len(attribute_exprs) == 0
            else _Stripped(
                f"""\
[
{I}{_indent_but_first_line(attribute_exprs_joined, I)}
]"""
            )
        )

        declaration_expr = _Stripped(
            f"""\
_EntityDeclaration(
{I}identifier={repr(entity.identifier)},
{I}attributes={_indent_but_first_line(attributes_value, I)}
)"""
        )
        entries.append((_Stripped(repr(entity.identifier)), declaration_expr))
    entries_joined = ",\n".join(f"{key}: {value}" for key, value in entries)
    return _Stripped(
        f"""\
_ENTITY_DECLARATION_MAP: Final[Mapping[str, _EntityDeclaration]] = {{
{I}{_indent_but_first_line(entries_joined, I)}
}}"""
    )


@ensure(lambda result: result.endswith("\n"))
def generate(
    schema: ir.Schema,
    base_namespace: str,
    entity_is_submodel: Callable[
        [ir.Entity], bool
    ] = smt.is_concrete_subtype_of_ifc_root,
) -> str:
    """
    Generate the conversion code.
    The ``entity_is_submodel`` determines whether an entity is mapped to a submodel,
    or otherwise represented as a nested submodel element collection.
    """
    namespace = f"{base_namespace}/{schema.identifier}"
    blocks = [
        _Stripped(
            f'''\
"""Convert entity instances of {schema.identifier} to AAS."""'''
        ),
        _Stripped(
            f"""\
import abc
import base64
import collections.abc
import copy
import re
from typing import (
{I}Any,
{I}Callable,
{I}Final,
{I}List,
{I}Mapping,
{I}MutableMapping,
{I}Optional,
{I}Sequence,
{I}Tuple,
{I}Union
)
from typing_extensions import assert_never
import ifcopenshell
from aas_core3 import (
{I}types as aas_types
)"""
        ),
        _Stripped(
            f'''\
_DROP_INS_IRI: Final[str] = "{namespace}/drop-ins"'''
        ),
        _Stripped(
            f'''\
_SUBMODEL_TEMPLATES_IRI: Final[str] = "{namespace}/submodel-templates"'''
        ),
        _Stripped(
            f"""\
def _model_reference(
{I}keys: Sequence[Tuple[aas_types.KeyTypes, str]]
) -> aas_types.Reference:
{I}return aas_types.Reference(
{II}type=aas_types.ReferenceTypes.MODEL_REFERENCE,
{II}keys=[
{III}aas_types.Key(
{IIII}type=key_type,
{IIII}value=value
{III})
{III}for key_type, value in keys
{II}]
{I})"""
        ),
        _Stripped(
            f"""\
_REFERENCE_TO_NUMBER_DROP_IN: Final[aas_types.Reference] = _model_reference(
{I}[
{II}(aas_types.KeyTypes.SUBMODEL, _DROP_INS_IRI),
{II}(aas_types.KeyTypes.PROPERTY, "Number")
{I}],
)"""
        ),
        _Stripped(
            f"""\
_REFERENCE_TO_LOGICAL_DROP_IN: Final[aas_types.Reference] = _model_reference(
{I}[
{II}(aas_types.KeyTypes.SUBMODEL, _DROP_INS_IRI),
{II}(aas_types.KeyTypes.PROPERTY, "Logical")
{I}],
)"""
        ),
        _Stripped(
            f'''\
def _bool_as_xs_bool_value(
{I}value: bool
) -> str:
{I}"""Convert a boolean to the corresponding literal of ``xs:boolean``."""
{I}return "true" if value else "false"'''
        ),
        _Stripped(
            f'''\
def _binary_to_property(
{I}value: Union[bytes, str]
) -> aas_types.Property:
{I}"""Translate the given value of a BINARY into a property element."""
{I}property_value: str
{I}if isinstance(value, str):
{II}if len(value) % 4 != 0 or _BASE64_RE.match(value) is None:
{III}value_snippet = (
{IIII}value
{IIII}if len(value) < 128
{IIII}else f"{{value[:128]}} [...]"
{III})
{III}raise ValueError(
{IIII}f"The binary value represented as a string {{value_snippet}} "
{IIII}f"is not a valid base64 encoding."
{III})
{II}property_value = value
{I}elif isinstance(value, bytes):
{II}property_value = base64.b64encode(value).decode("utf-8")
{I}else:
{II}raise ValueError(f"Unexpected value: {{value}}")
{I}return aas_types.Property(
{II}value_type=aas_types.DataTypeDefXSD.BASE_64_BINARY,
{II}value=property_value
{I})'''
        ),
        _Stripped(
            f'''\
def _logical_as_str(
{I}value: Optional[Union[bool, str]]
) -> str:
{I}"""Convert a logical value to the corresponding string."""
{I}if value is None:
{II}return "UNKNOWN"
{I}if isinstance(value, str):
{II}if value == "UNKNOWN":
{III}return "UNKNOWN"
{II}else:
{III}raise ValueError("Unexpected logical value: {{value!r}}")
{I}assert isinstance(value, bool)
{I}return (
{II}"TRUE"
{II}if value
{II}else "FALSE"
{I})'''
        ),
        _Stripped(
            f'''\
def _number_to_collection(
{I}value: Union[int, float]
) -> aas_types.SubmodelElementCollection:
{I}"""
{I}Convert the number value to a collection with ``value`` element.
{I}Neither the ID-short nor the semantic ID will be set.
{I}"""
{I}if isinstance(value, int):
{II}value_type = aas_types.DataTypeDefXSD.LONG
{I}elif isinstance(value, float):
{II}value_type = aas_types.DataTypeDefXSD.DOUBLE
{I}else:
{II}raise ValueError(f"Unexpected number of type: {{type(value)}}")
{I}return aas_types.SubmodelElementCollection(
{II}semantic_id=copy.copy(_REFERENCE_TO_NUMBER_DROP_IN),
{II}value=[
{III}aas_types.Property(
{IIII}id_short="value",
{IIII}value_type=value_type,
{IIII}value=str(value)
{III})
{II}]
{I})'''
        ),
        _generate_element_class_to_key_type(),
    ]  # type: List[_Stripped]
    blocks.extend(_generate_structural_type_blocks())
    blocks.append(
        _Stripped(
            f'''\
class Logger:
{I}"""Log errors instead of raising exceptions on schema violations."""

{I}def __init__(
{II}self
{I}) -> None:
{II}self.messages = []  # type: List[str]

{I}def error(self, message: str) -> None:
{II}"""Log the error message."""
{II}self.messages.append(message)'''
        )
    )
    blocks.append(
        _Stripped(
            f'''\
def _to_elements_by_declaration(
{I}instance: ifcopenshell.entity_instance,
{I}identify: Callable[[ifcopenshell.entity_instance], str],
{I}declaration: _EntityDeclaration,
{I}logger: Optional[Logger]
) -> List[aas_types.SubmodelElement]:
{I}"""Translate the given instance into its elements following its declaration."""
{I}elements = []  # type: List[aas_types.SubmodelElement]
{I}for attribute in declaration.attributes:
{II}if not hasattr(instance, attribute.name):
{III}message = (
{IIII}f"Attribute {{attribute.name}} is missing "
{IIII}f"in an instance {{instance}} presumed "
{IIII}f"to be of entity {{declaration.identifier}}."
{III})

{III}if logger is not None:
{IIII}logger.error(message)
{IIII}continue

{III}raise ValueError(message)

{II}value = getattr(instance, attribute.name)
{II}if attribute.optional and value is None:
{III}continue

{II}if not attribute.structural_type.match(value):
{III}message = (
{IIII}f"Attribute {{attribute.name}} with value {{value}} "
{IIII}f"of instance {{instance}} does not match "
{IIII}f"the expected structural type {{attribute.structural_type}}; skipping"
{III})

{III}if logger is not None:
{IIII}logger.error(message)
{IIII}continue

{III}raise ValueError(message)

{II}element = attribute.structural_type.translate(value, identify)
{II}element.id_short = attribute.name
{II}elements.append(element)
{I}return elements'''
        )
    )
    blocks.append(
        _Stripped(
            f'''\
def _to_submodel_by_declaration(
{I}instance: ifcopenshell.entity_instance,
{I}identify: Callable[[ifcopenshell.entity_instance], str],
{I}declaration: _EntityDeclaration,
{I}logger: Optional[Logger]
) -> aas_types.Submodel:
{I}"""
{I}Translate an ``instance`` to a submodel following the ``declaration``.

{I}The function ``identify`` determines the global identifiers of entities mapped
{I}to submodels.

{I}If ``logger`` is supplied, the violations of the schema will be written to it,
{I}and the translation will continue. Otherwise, a ``ValueError`` will be immediately
{I}raised.
{I}"""
{I}elements = _to_elements_by_declaration(
{II}instance=instance,
{II}identify=identify,
{II}declaration=declaration,
{II}logger=logger
{I})
{I}return aas_types.Submodel(
{II}id=identify(instance),
{II}semantic_id=_model_reference(
{III}[
{IIII}(
{IIIII}aas_types.KeyTypes.SUBMODEL,
{IIIII}f"{{_SUBMODEL_TEMPLATES_IRI}}/{{declaration.identifier}}"
{IIII}),
{III}]
{II}),
{II}submodel_elements=elements if len(elements) > 0 else None
{I})'''
        )
    )
    blocks.append(
        _Stripped(
            f'''\
def _to_submodel_element_collection_by_declaration(
{I}instance: ifcopenshell.entity_instance,
{I}identify: Callable[[ifcopenshell.entity_instance], str],
{I}declaration: _EntityDeclaration,
{I}logger: Optional[Logger]
) -> aas_types.SubmodelElementCollection:
{I}"""
{I}Convert an ``instance`` to a submodel element collection by the ``declaration``.

{I}The function ``identify`` determines the global identifiers of entities mapped
{I}to submodels.

{I}If ``logger`` is supplied, the violations of the schema will be written to it,
{I}and the translation will continue. Otherwise, a ``ValueError`` will be immediately
{I}raised.
{I}"""
{I}elements = _to_elements_by_declaration(
{II}instance=instance,
{II}identify=identify,
{II}declaration=declaration,
{II}logger=logger
{I})
{I}return aas_types.SubmodelElementCollection(
{II}semantic_id=_model_reference(
{III}[
{IIII}(aas_types.KeyTypes.SUBMODEL, _DROP_INS_IRI),
{IIII}(aas_types.KeyTypes.SUBMODEL_ELEMENT_COLLECTION, declaration.identifier)
{III}]
{II}),
{II}value=elements if len(elements) > 0 else None
{I})'''
        )
    )
    for entity in schema.entities:
        if entity.abstract:
            continue
        if entity_is_submodel(entity):
            blocks.append(_generate_entity_to_submodel(entity=entity))
        else:
            blocks.append(
                _generate_entity_to_submodel_element_collection(entity=entity)
            )
    blocks.append(
        _generate_to_submodel_map(
            entities_mapped_to_submodels=[
                entity
                for entity in schema.entities
                if entity_is_submodel(entity) and not entity.abstract
            ]
        )
    )
    blocks.append(
        _generate_to_submodel_element_collection_map(
            entities_mapped_to_submodel_element_collections=[
                entity
                for entity in schema.entities
                if not entity_is_submodel(entity) and not entity.abstract
            ]
        )
    )
    blocks.extend(_generate_translate())
    blocks.append(_generate_enumeration_map(enumerations=schema.enumerations))
    blocks.extend(
        _generate_declared_type_map(
            declared_types_topologically_sorted=(
                schema.declared_types_topologically_sorted
            ),
            entities_with_selection=[
                entity
                for entity in schema.entities
                if len(entity.descendant_concrete_entities) > 0
            ],
        )
    )
    blocks.append(
        _generate_entity_declaration_map(
            entities=[entity for entity in schema.entities if not entity.abstract]
        )
    )
    blocks.append(
        _Stripped(
            f"""\
ENTITIES_MAPPED_TO_SUBMODELS: Final[Sequence[str]] = sorted(
{I}_TO_SUBMODEL_MAP.keys()
)"""
        )
    )
    blocks.append(
        _Stripped(
            f"""\
ENTITIES_MAPPED_TO_SUBMODEL_ELEMENT_COLLECTIONS: Final[Sequence[str]] = sorted(
{I}_TO_SUBMODEL_ELEMENT_COLLECTION_MAP.keys()
)"""
        )
    )
    return "\n\n".join(blocks) + "\n"
