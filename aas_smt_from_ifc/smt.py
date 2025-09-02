"""Translate the intermediate representation into AAS submodel templates."""

import enum
import inspect
import itertools
import json
from typing import (
    Callable,
    List,
    Optional,
    Sequence,
    Any,
    Union,
    MutableMapping,
    Mapping,
    Protocol,
    cast,
    Iterable,
)

from aas_core3 import (
    jsonization as aas_jsonization,
    types as aas_types,
    verification as aas_verification,
)
from express_schema import lex
from icontract import ensure, require

from aas_smt_from_ifc import ir, re_escaping
from aas_smt_from_ifc.common import (
    NonNegativeInt,
    assert_never,
)


def is_concrete_subtype_of_ifc_root(entity: ir.Entity) -> bool:
    """Check whether the entity is a concrete entity and a subtype of ``IfcRoot``."""
    if entity.abstract:
        return False

    stack = list(entity.supertypes)
    while len(stack) > 0:
        supertype = stack.pop()
        if supertype.identifier == "IfcRoot":
            return True

        stack.extend(supertype.supertypes)

    return False


@ensure(lambda result: result.type == aas_types.ReferenceTypes.EXTERNAL_REFERENCE)
def _external_reference(value: str) -> aas_types.Reference:
    result = aas_types.Reference(
        type=aas_types.ReferenceTypes.EXTERNAL_REFERENCE,
        keys=[aas_types.Key(type=aas_types.KeyTypes.GLOBAL_REFERENCE, value=value)],
    )

    return result


def _enumeration_as_property(enumeration: ir.Enumeration) -> aas_types.Property:
    assert len(list(aas_verification.verify_identifier(enumeration.identifier))) == 0

    prop = aas_types.Property(
        id_short=enumeration.identifier,
        value_type=aas_types.DataTypeDefXSD.STRING,
        qualifiers=[
            aas_types.Qualifier(
                type="SMT/AllowedValue",
                value_type=aas_types.DataTypeDefXSD.STRING,
                value="|".join(
                    re_escaping.escape_literal(value) for value in enumeration.values
                ),
            )
        ],
    )

    return prop


@ensure(lambda result: result.type == "SMT/minLength")
def _min_length_qualifier(min_length: NonNegativeInt) -> aas_types.Qualifier:
    return aas_types.Qualifier(
        type="SMT/minLength",
        value_type=aas_types.DataTypeDefXSD.UNSIGNED_LONG,
        value=str(min_length),
    )


@ensure(lambda result: result.type == "SMT/maxLength")
def _max_length_qualifier(min_length: NonNegativeInt) -> aas_types.Qualifier:
    return aas_types.Qualifier(
        type="SMT/maxLength",
        value_type=aas_types.DataTypeDefXSD.UNSIGNED_LONG,
        value=str(min_length),
    )


@ensure(lambda result: not (result is not None) or result.type == "SMT/AllowedRange")
def _try_allowed_range_qualifier(
    tajp: Union[ir.IntegerType, ir.RealType, ir.NumberType],
) -> Optional[aas_types.Qualifier]:
    if tajp.min_value is None and tajp.max_value is None:
        return None

    if tajp.min_value is None:
        min_value = "(-INF"
    else:
        if tajp.min_value.inclusive:
            min_value = f"[{tajp.min_value.value}"
        else:
            min_value = f"({tajp.min_value.value}"

    if tajp.max_value is None:
        max_value = "INF)"
    else:
        if tajp.max_value.inclusive:
            max_value = f"{tajp.max_value.value}]"
        else:
            max_value = f"({tajp.max_value.value})"

    return aas_types.Qualifier(
        type="SMT/AllowedRange",
        value_type=aas_types.DataTypeDefXSD.STRING,
        value=f"{min_value},{max_value}",
    )


@ensure(lambda result: result.type is aas_types.ReferenceTypes.MODEL_REFERENCE)
def _model_reference_to_submodel_template(identifier: str) -> aas_types.Reference:
    return aas_types.Reference(
        type=aas_types.ReferenceTypes.MODEL_REFERENCE,
        keys=[aas_types.Key(type=aas_types.KeyTypes.SUBMODEL, value=identifier)],
    )


@ensure(lambda result: result.type is aas_types.ReferenceTypes.MODEL_REFERENCE)
def _model_reference_to_drop_in(
    drop_ins_id: str, drop_in_key_type: aas_types.KeyTypes, drop_in_id_short: str
) -> aas_types.Reference:
    return aas_types.Reference(
        type=aas_types.ReferenceTypes.MODEL_REFERENCE,
        keys=[
            aas_types.Key(type=aas_types.KeyTypes.SUBMODEL, value=drop_ins_id),
            aas_types.Key(type=drop_in_key_type, value=drop_in_id_short),
        ],
    )


@ensure(lambda result: aas_types.SubmodelElement in result)
def _submodel_element_class_and_its_subclasses() -> List[type]:
    result = []  # type: List[type]

    for attr in dir(aas_types):
        value = getattr(aas_types, attr)

        if inspect.isclass(value) and issubclass(value, aas_types.SubmodelElement):
            result.append(value)

    return result


_TYPE_VALUE_LIST_ELEMENT_BY_CLASS = {
    aas_types.AnnotatedRelationshipElement: (
        aas_types.AASSubmodelElements.ANNOTATED_RELATIONSHIP_ELEMENT
    ),
    aas_types.BasicEventElement: aas_types.AASSubmodelElements.BASIC_EVENT_ELEMENT,
    aas_types.Blob: aas_types.AASSubmodelElements.BLOB,
    aas_types.Capability: aas_types.AASSubmodelElements.CAPABILITY,
    aas_types.DataElement: aas_types.AASSubmodelElements.DATA_ELEMENT,
    aas_types.Entity: aas_types.AASSubmodelElements.ENTITY,
    aas_types.EventElement: aas_types.AASSubmodelElements.EVENT_ELEMENT,
    aas_types.File: aas_types.AASSubmodelElements.FILE,
    aas_types.MultiLanguageProperty: aas_types.AASSubmodelElements.MULTI_LANGUAGE_PROPERTY,
    aas_types.Operation: aas_types.AASSubmodelElements.OPERATION,
    aas_types.Property: aas_types.AASSubmodelElements.PROPERTY,
    aas_types.Range: aas_types.AASSubmodelElements.RANGE,
    aas_types.ReferenceElement: aas_types.AASSubmodelElements.REFERENCE_ELEMENT,
    aas_types.RelationshipElement: aas_types.AASSubmodelElements.RELATIONSHIP_ELEMENT,
    aas_types.SubmodelElement: aas_types.AASSubmodelElements.SUBMODEL_ELEMENT,
    aas_types.SubmodelElementList: aas_types.AASSubmodelElements.SUBMODEL_ELEMENT_LIST,
    aas_types.SubmodelElementCollection: aas_types.AASSubmodelElements.SUBMODEL_ELEMENT_COLLECTION,
}

assert set(id(key) for key in _TYPE_VALUE_LIST_ELEMENT_BY_CLASS) == set(
    id(cls) for cls in _submodel_element_class_and_its_subclasses()
)

AAS_KEY_TYPES_BY_CLASS = {
    aas_types.AnnotatedRelationshipElement: aas_types.KeyTypes.ANNOTATED_RELATIONSHIP_ELEMENT,
    aas_types.AssetAdministrationShell: aas_types.KeyTypes.ASSET_ADMINISTRATION_SHELL,
    aas_types.BasicEventElement: aas_types.KeyTypes.BASIC_EVENT_ELEMENT,
    aas_types.Blob: aas_types.KeyTypes.BLOB,
    aas_types.Capability: aas_types.KeyTypes.CAPABILITY,
    aas_types.ConceptDescription: aas_types.KeyTypes.CONCEPT_DESCRIPTION,
    aas_types.DataElement: aas_types.KeyTypes.DATA_ELEMENT,
    aas_types.Entity: aas_types.KeyTypes.ENTITY,
    aas_types.EventElement: aas_types.KeyTypes.EVENT_ELEMENT,
    aas_types.File: aas_types.KeyTypes.FILE,
    aas_types.MultiLanguageProperty: aas_types.KeyTypes.MULTI_LANGUAGE_PROPERTY,
    aas_types.Operation: aas_types.KeyTypes.OPERATION,
    aas_types.Property: aas_types.KeyTypes.PROPERTY,
    aas_types.Range: aas_types.KeyTypes.RANGE,
    aas_types.Referable: aas_types.KeyTypes.REFERABLE,
    aas_types.ReferenceElement: aas_types.KeyTypes.REFERENCE_ELEMENT,
    aas_types.RelationshipElement: aas_types.KeyTypes.RELATIONSHIP_ELEMENT,
    aas_types.Submodel: aas_types.KeyTypes.SUBMODEL,
    aas_types.SubmodelElement: aas_types.KeyTypes.SUBMODEL_ELEMENT,
    aas_types.SubmodelElementCollection: aas_types.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
    aas_types.SubmodelElementList: aas_types.KeyTypes.SUBMODEL_ELEMENT_LIST,
}


def _assert_aas_key_types_by_class_covers_everything() -> None:
    id_to_key = {id(key): key for key in AAS_KEY_TYPES_BY_CLASS}

    for cls in _submodel_element_class_and_its_subclasses():
        if id(cls) not in id_to_key:
            raise AssertionError(
                f"The class {cls} is present in submodel element class and "
                f"its subclasses, but not in _AAS_KEY_TYPES_BY_CLASS."
            )


_assert_aas_key_types_by_class_covers_everything()


class EntityTranslation(enum.Enum):
    """Capture how a concrete entity is translated to the AAS universe."""

    SUBMODEL = "Submodel"
    SUBMODEL_ELEMENT_COLLECTION = "SubmodelElementCollection"


# fmt: off
@ensure(
    lambda entities, result:
    all(
        result[entity] is None
        for entity in entities
        if entity.abstract
    ),
    "Abstract entities have no concrete representation."
)
# fmt: on
def map_entity_translations(
    entities: Sequence[ir.Entity], entity_is_submodel: Callable[[ir.Entity], bool]
) -> MutableMapping[ir.Entity, Optional[EntityTranslation]]:
    """Map and cache the entity translation according to ``entity_is_submodel``."""
    result = dict()  # type: MutableMapping[ir.Entity, Optional[EntityTranslation]]

    for entity in entities:
        if entity.abstract:
            result[entity] = None
        else:
            if entity_is_submodel(entity):
                result[entity] = EntityTranslation.SUBMODEL
            else:
                result[entity] = EntityTranslation.SUBMODEL_ELEMENT_COLLECTION

    return result


# fmt: off
@ensure(
    lambda result: result.qualifiers is None,
    "No qualifiers are set; the client must set them after the creation."
)
@ensure(
    lambda result: result.semantic_id is None,
    "No semantic is set; the client must set it after the creation."
)
@ensure(
    lambda result:
    not isinstance(result, aas_types.SubmodelElementList) or result.value is None,
    "No representative element set in the list; "
    "the client must set it after the creation."
)
@ensure(
    lambda result:
    not isinstance(result, aas_types.SubmodelElementCollection) or result.value is None,
    "No elements specified in the collections; "
    "the client must set them after the creation."
)
# fmt: on
def representative_element(
    tajp: ir.Type,
    entity_translation_map: Mapping[ir.Entity, Optional[EntityTranslation]],
) -> aas_types.SubmodelElement:
    """Create the submodel element corresponding to the Express type."""
    if isinstance(tajp, ir.BinaryType):
        return aas_types.Property(value_type=aas_types.DataTypeDefXSD.BASE_64_BINARY)

    elif isinstance(tajp, ir.BooleanType):
        return aas_types.Property(value_type=aas_types.DataTypeDefXSD.BOOLEAN)

    elif isinstance(tajp, (ir.IntegerType, ir.RealType)):
        if isinstance(tajp, ir.IntegerType):
            value_type = aas_types.DataTypeDefXSD.LONG
        elif isinstance(tajp, ir.RealType):
            value_type = aas_types.DataTypeDefXSD.DOUBLE
        else:
            # noinspection PyTypeChecker
            assert_never(tajp)

        return aas_types.Property(value_type=value_type)

    elif isinstance(tajp, ir.LogicalType):
        return aas_types.Property(value_type=aas_types.DataTypeDefXSD.STRING)

    elif isinstance(tajp, ir.NumberType):
        return aas_types.SubmodelElementCollection()

    elif isinstance(tajp, ir.StringType):
        return aas_types.Property(value_type=aas_types.DataTypeDefXSD.STRING)

    elif isinstance(tajp, (ir.ArrayType, ir.BagType, ir.ListType, ir.SetType)):
        item_element: aas_types.SubmodelElement

        if isinstance(tajp, ir.ArrayType) and tajp.optional:
            # NOTE (mristin):
            # In case of optional arrays, the representative item element is
            # a collection with a single element ``value``, which might or might not
            # be set.
            item_element = aas_types.SubmodelElementCollection()
        else:
            item_element = representative_element(
                tajp=tajp.items, entity_translation_map=entity_translation_map
            )

        element = aas_types.SubmodelElementList(
            type_value_list_element=_TYPE_VALUE_LIST_ELEMENT_BY_CLASS[
                item_element.__class__
            ]
        )

        if isinstance(item_element, (aas_types.Property, aas_types.Range)):
            element.value_type_list_element = item_element.value_type

        return element

    elif isinstance(tajp, ir.SelectType):
        return aas_types.SubmodelElementCollection()

    elif isinstance(tajp, ir.Enumeration):
        return aas_types.Property(value_type=aas_types.DataTypeDefXSD.STRING)

    elif isinstance(tajp, ir.Entity):
        assert not tajp.abstract or len(tajp.descendant_concrete_entities) > 0, (
            f"Abstract entities must have at least one descendant concrete entity, "
            f"but the entity {tajp.identifier!r} has no concrete descendant entity."
        )

        # NOTE (mristin):
        # We explicitly translate all entities with concrete descendants into
        # a type selection since the template language does not allow us to
        # model it otherwise.
        if len(tajp.descendant_concrete_entities) > 0:
            return aas_types.SubmodelElementCollection()

        assert not tajp.abstract

        entity_translation = entity_translation_map[tajp]

        assert entity_translation is not None, (
            f"Concrete translation must be given for concrete entities, "
            f"but it is lacking for the entity {tajp.identifier!r}."
        )

        if entity_translation is EntityTranslation.SUBMODEL:
            return aas_types.ReferenceElement()

        elif entity_translation is EntityTranslation.SUBMODEL_ELEMENT_COLLECTION:
            return aas_types.SubmodelElementCollection()

        else:
            # noinspection PyTypeChecker
            assert_never(entity_translation)

    elif isinstance(tajp, ir.DeclaredType):
        return representative_element(
            tajp=ir.resolve_type(tajp), entity_translation_map=entity_translation_map
        )

    else:
        # noinspection PyTypeChecker
        assert_never(tajp)


@ensure(lambda tajp, result: len(tajp.types) <= len(result))
def flatten_select_type(tajp: ir.SelectType) -> List[ir.TypeWithoutSelectType]:
    """Flatten recursively the types of the union of unions."""
    # NOTE (mristin):
    # The numbers in Express schema are a union type of integers and reals. We are
    # unsure how to deal with them here. Theoretically, we could consider them
    # in the union of unions and flatten them that way. However, if they appear
    # in declared types, we want to reference the declared type as a drop-in, and
    # that would mean that they have to be represented as a collection, and thus
    # could not be included in the union of unions.
    #
    # We finally decided to always represent numbers as numbers, even when
    # they appear in a type selection.

    result = []  # type: List[ir.TypeWithoutSelectType]

    for selected_type in tajp.types:
        resolved_selected_type = ir.resolve_type(selected_type)

        if isinstance(resolved_selected_type, ir.SelectType):
            result.extend(flatten_select_type(resolved_selected_type))

        else:
            assert not isinstance(selected_type, ir.SelectType)
            result.append(selected_type)

    return result


# fmt: off
@ensure(
    lambda result:
    result.id_short is None,
    "The ID-short is expected be set by the caller."
)
# fmt: on
def _type_as_submodel_element(
    tajp: ir.Type,
    drop_ins_id: str,
    smt_id_prefix: str,
    entity_translation_map: Mapping[ir.Entity, Optional[EntityTranslation]],
) -> aas_types.SubmodelElement:
    element = representative_element(
        tajp=tajp, entity_translation_map=entity_translation_map
    )

    # NOTE (mristin):
    # Now we set / enhance the representative element to specify the constraints
    # through qualifiers, include item element *etc.*

    if isinstance(tajp, ir.BinaryType):
        qualifiers = []  # type: List[aas_types.Qualifier]
        if tajp.min_length is not None:
            qualifiers.append(_min_length_qualifier(tajp.min_length))

        if tajp.max_length is not None:
            qualifiers.append(_max_length_qualifier(tajp.max_length))

        if len(qualifiers) > 0:
            element.qualifiers = qualifiers

    elif isinstance(tajp, ir.BooleanType):
        pass

    elif isinstance(tajp, (ir.IntegerType, ir.RealType)):
        allowed_range_qualifier = _try_allowed_range_qualifier(tajp=tajp)

        if allowed_range_qualifier is not None:
            element.qualifiers = [allowed_range_qualifier]

    elif isinstance(tajp, ir.LogicalType):
        element.semantic_id = _model_reference_to_drop_in(
            drop_ins_id=drop_ins_id,
            drop_in_key_type=aas_types.KeyTypes.PROPERTY,
            drop_in_id_short="Logical",
        )

    elif isinstance(tajp, ir.NumberType):
        element.semantic_id = _model_reference_to_drop_in(
            drop_ins_id=drop_ins_id,
            drop_in_key_type=aas_types.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
            drop_in_id_short="Number",
        )

    elif isinstance(tajp, ir.StringType):
        qualifiers = []
        if tajp.min_length is not None:
            qualifiers.append(_min_length_qualifier(tajp.min_length))

        if tajp.max_length is not None:
            qualifiers.append(_max_length_qualifier(tajp.max_length))

        if len(qualifiers) > 0:
            element.qualifiers = qualifiers

        if tajp.choice is not None:
            qualifiers.append(
                aas_types.Qualifier(
                    type="SMT/AllowedValue",
                    value_type=aas_types.DataTypeDefXSD.STRING,
                    value="|".join(
                        re_escaping.escape_literal(value) for value in tajp.choice
                    ),
                )
            )

    elif isinstance(tajp, (ir.ArrayType, ir.BagType, ir.ListType, ir.SetType)):
        item_element = _type_as_submodel_element(
            tajp=tajp.items,
            drop_ins_id=drop_ins_id,
            smt_id_prefix=smt_id_prefix,
            entity_translation_map=entity_translation_map,
        )

        if isinstance(tajp, ir.ArrayType) and tajp.optional:
            # NOTE (mristin):
            # An optional array means that some of the entries are undefined, so we
            # have to represent it as a sequence of optional items, where each optional
            # item is a collection with a single optional ``value`` element.
            defined_element = item_element
            defined_element.id_short = "value"
            defined_element.qualifiers = [
                aas_types.Qualifier(
                    type="SMT/Cardinality",
                    value_type=aas_types.DataTypeDefXSD.STRING,
                    value="ZeroToOne",
                )
            ]

            item_element = aas_types.SubmodelElementCollection(value=[defined_element])

        if item_element.qualifiers is None:
            item_element.qualifiers = []

        item_element.qualifiers.append(
            aas_types.Qualifier(
                type="SMT/Cardinality",
                value_type=aas_types.DataTypeDefXSD.STRING,
                value="OneToMany",
            )
        )

        assert isinstance(element, aas_types.SubmodelElementList), (
            "The representative element for arrays, bags, lists and sets must be "
            "a submodel element list."
        )

        element.value = [item_element]

        qualifiers = []
        if tajp.min_length is not None:
            qualifiers.append(_min_length_qualifier(tajp.min_length))

        if tajp.max_length is not None:
            qualifiers.append(_max_length_qualifier(tajp.max_length))

        if len(qualifiers) > 0:
            element.qualifiers = qualifiers

        if isinstance(tajp, (ir.ArrayType, ir.ListType)):
            element.order_relevant = True
        elif isinstance(tajp, (ir.BagType, ir.SetType)):
            element.order_relevant = False
        else:
            # noinspection PyTypeChecker
            assert_never(tajp)

    elif isinstance(tajp, ir.SelectType):
        assert isinstance(element, aas_types.SubmodelElementCollection), (
            "We represent the sum types (a.k.a. union types, select types) "
            "with a collection."
        )

        items = []  # type: List[aas_types.SubmodelElement]

        for i, selected_type in enumerate(flatten_select_type(tajp)):
            item = _type_as_submodel_element(
                tajp=selected_type,
                drop_ins_id=drop_ins_id,
                smt_id_prefix=smt_id_prefix,
                entity_translation_map=entity_translation_map,
            )

            item.id_short = f"value{i}"

            item.qualifiers = [
                aas_types.Qualifier(
                    type="SMT/AllowedIdShort",
                    value_type=aas_types.DataTypeDefXSD.STRING,
                    value="value",
                )
            ]

            items.append(item)

        element.value = items

    elif isinstance(tajp, ir.Enumeration):
        element.semantic_id = _model_reference_to_drop_in(
            drop_ins_id=drop_ins_id,
            drop_in_key_type=aas_types.KeyTypes.PROPERTY,
            drop_in_id_short=tajp.identifier,
        )

    elif isinstance(tajp, ir.Entity):
        assert not tajp.abstract or len(tajp.descendant_concrete_entities) > 0, (
            f"Abstract entities must have at least one descendant concrete entity, "
            f"but the entity {tajp.identifier!r} has no concrete descendant entity."
        )

        # NOTE (mristin):
        # We explicitly translate all entities with concrete descendants into
        # a type selection since the template language does not allow us to
        # model it otherwise.
        if len(tajp.descendant_concrete_entities) > 0:
            element.semantic_id = _model_reference_to_drop_in(
                drop_ins_id=drop_ins_id,
                drop_in_key_type=aas_types.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
                drop_in_id_short=f"{tajp.identifier}_select",
            )

        else:
            entity_translation = entity_translation_map[tajp]
            assert entity_translation is not None, (
                f"Concrete translation must be given for concrete entities, "
                f"but it is lacking for the entity {tajp.identifier!r}."
            )

            if entity_translation is EntityTranslation.SUBMODEL:
                element.semantic_id = _model_reference_to_submodel_template(
                    identifier=f"{smt_id_prefix}/{tajp.identifier}"
                )

            elif entity_translation is EntityTranslation.SUBMODEL_ELEMENT_COLLECTION:
                element.semantic_id = _model_reference_to_drop_in(
                    drop_ins_id=drop_ins_id,
                    drop_in_key_type=aas_types.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
                    drop_in_id_short=tajp.identifier,
                )

            else:
                # noinspection PyTypeChecker
                assert_never(entity_translation)

    elif isinstance(tajp, ir.DeclaredType):
        element.semantic_id = _model_reference_to_drop_in(
            drop_ins_id=drop_ins_id,
            drop_in_key_type=AAS_KEY_TYPES_BY_CLASS[element.__class__],
            drop_in_id_short=tajp.identifier,
        )
    else:
        # noinspection PyTypeChecker
        assert_never(tajp)

    return element


# fmt: off
@ensure(
    lambda result:
    result.id_short is None,
    "The client must set the ID-short"
)
@require(lambda entity: len(entity.descendant_concrete_entities) > 0)
# fmt: on
def _entity_to_select_collection(
    entity: ir.Entity,
    drop_ins_id: str,
    smt_id_prefix: str,
    entity_translation_map: Mapping[ir.Entity, Optional[EntityTranslation]],
) -> aas_types.SubmodelElementCollection:
    concrete_entities = []

    if not entity.abstract:
        concrete_entities.append(entity)

    concrete_entities.extend(entity.descendant_concrete_entities)

    elements: List[aas_types.SubmodelElement] = []

    # NOTE (mristin):
    # We want to make sure that we do not mix up the ``concrete_entity`` and
    # ``entity`` variable.
    del entity

    for i, concrete_entity in enumerate(concrete_entities):
        assert not concrete_entity.abstract
        entity_translation = entity_translation_map[concrete_entity]

        assert (
            entity_translation is not None
        ), "Entity translation must be defined for concrete entities."

        element: Union[aas_types.ReferenceElement, aas_types.SubmodelElementCollection]

        if entity_translation is EntityTranslation.SUBMODEL:
            element = aas_types.ReferenceElement(
                semantic_id=_model_reference_to_submodel_template(
                    identifier=f"{smt_id_prefix}/{concrete_entity.identifier}"
                )
            )

        elif entity_translation is EntityTranslation.SUBMODEL_ELEMENT_COLLECTION:
            element = aas_types.SubmodelElementCollection(
                semantic_id=_model_reference_to_drop_in(
                    drop_ins_id=drop_ins_id,
                    drop_in_key_type=aas_types.KeyTypes.SUBMODEL_ELEMENT_COLLECTION,
                    drop_in_id_short=concrete_entity.identifier,
                )
            )

        else:
            # noinspection PyTypeChecker
            assert_never(entity_translation)

        element.id_short = f"value{i}"

        elements.append(element)

    assert len(elements) > 0, (
        "At least one select entry expected if there was "
        "at least one concrete descendant entity."
    )

    return aas_types.SubmodelElementCollection(value=elements)


# fmt: off
@ensure(
    lambda attributes, result:
    len(result) == len(attributes)
)
# fmt: on
def _attributes_to_elements(
    attributes: Sequence[ir.Attribute],
    drop_ins_id: str,
    smt_id_prefix: str,
    entity_translation_map: Mapping[ir.Entity, Optional[EntityTranslation]],
) -> List[aas_types.SubmodelElement]:
    """
    Translate the attributes to their representation as AAS elements.

    These elements are either to be included in a submodel template, if the entity
    is globally identifiable, or in a drop-in collection, if the entity is not
    globally identifiable and is represented as a drop-in.

    If there are no attributes, an empty list is returned. The caller should make sure
    that the constraint of the AAS meta-model is satisfied mandating that the lists
    are either None or non-empty.
    """
    result = []  # type: List[aas_types.SubmodelElement]

    for attribute in attributes:
        element = _type_as_submodel_element(
            tajp=attribute.tajp,
            drop_ins_id=drop_ins_id,
            smt_id_prefix=smt_id_prefix,
            entity_translation_map=entity_translation_map,
        )

        element.id_short = attribute.name

        if attribute.optional:
            element.qualifiers = [
                aas_types.Qualifier(
                    type="SMT/Cardinality",
                    value_type=aas_types.DataTypeDefXSD.STRING,
                    value="ZeroToOne",
                )
            ]
        else:
            element.qualifiers = [
                aas_types.Qualifier(
                    type="SMT/Cardinality",
                    value_type=aas_types.DataTypeDefXSD.STRING,
                    value="One",
                )
            ]

        result.append(element)

    return result


def _find_offender_and_dump_it(
    environment: aas_types.Environment, error: aas_verification.Error
) -> str:
    """Follow the path to the offending instance of the model and dump it as JSON."""
    obj = environment  # type: Any
    for segment in error.path.segments:
        if isinstance(segment, aas_verification.PropertySegment):
            obj = getattr(obj, segment.name)
        elif isinstance(segment, aas_verification.IndexSegment):
            assert isinstance(obj, list)
            obj = obj[segment.index]
        else:
            # noinspection PyTypeChecker
            assert_never(segment)

    jsonable = aas_jsonization.to_jsonable(obj)
    return json.dumps(jsonable, indent=2)


class _WithIdentifier(Protocol):
    identifier: lex.Identifier


def translate(
    schema: ir.Schema,
    base_namespace: str,
    entity_is_submodel: Callable[[ir.Entity], bool] = is_concrete_subtype_of_ifc_root,
) -> aas_types.Environment:
    """
    Translate the Express schema into the AAS submodel templates.

    The ``entity_is_submodel`` determines whether an entity is mapped to a submodel,
    or otherwise to a template collection which goes into a separate submodel to serve
    as a drop-in.

    Return the result AAS environment with all the submodel templates, or errors,
    if any.
    """
    namespace = f"{base_namespace}/{schema.identifier}"

    environment = aas_types.Environment()

    smt_id_prefix = f"{namespace}/templates"

    drop_ins_id = f"{namespace}/drop-ins"
    drop_ins_submodel = aas_types.Submodel(id=drop_ins_id)

    for something in itertools.chain(
        cast(Iterable[_WithIdentifier], schema.declared_types),
        cast(Iterable[_WithIdentifier], schema.enumerations),
        cast(Iterable[_WithIdentifier], schema.entities),
    ):
        if something.identifier.lower().endswith("_select"):
            raise AssertionError(
                "We use '_select' suffix for entity selections (a.k.a. sum types), "
                f"but {something!r} identifier conflicts with it. Please contact "
                f"the developers if you need this feature."
            )

    # NOTE (mristin):
    # We check that reserved keywords do not show up as identifiers in any
    # of the declarations. This should have been detected at the parse stage, so
    # we only assert it here for correctness.
    for reserved_name in ("Number", "Logical"):
        assert reserved_name not in schema.declared_types_by_id, f"{reserved_name=}"
        assert reserved_name not in schema.enumerations_by_id, f"{reserved_name=}"
        assert reserved_name not in schema.entities_by_id, f"{reserved_name=}"

    drop_ins_submodel.submodel_elements = [
        # NOTE (mristin):
        # We manually define the representation of a number as a sum type of integers and
        # reals.
        aas_types.SubmodelElementCollection(
            id_short="Number",
            value=[
                aas_types.Property(
                    id_short="value_integer", value_type=aas_types.DataTypeDefXSD.LONG
                ),
                aas_types.Property(
                    id_short="value_real", value_type=aas_types.DataTypeDefXSD.DOUBLE
                ),
            ],
        ),
        # NOTE (mristin):
        # We represent a logical as a string with constrained choice.
        aas_types.Property(
            id_short="Logical",
            value_type=aas_types.DataTypeDefXSD.STRING,
            qualifiers=[
                aas_types.Qualifier(
                    type="SMT/AllowedValue",
                    value_type=aas_types.DataTypeDefXSD.STRING,
                    value="true|false|unknown",
                )
            ],
        ),
    ]

    for enumeration in schema.enumerations:
        drop_ins_submodel.submodel_elements.append(
            _enumeration_as_property(enumeration=enumeration)
        )

    entity_translation_map = map_entity_translations(
        entities=schema.entities, entity_is_submodel=entity_is_submodel
    )

    for declared_type in schema.declared_types:
        declared_type_element = _type_as_submodel_element(
            tajp=declared_type.tajp,
            drop_ins_id=drop_ins_id,
            smt_id_prefix=smt_id_prefix,
            entity_translation_map=entity_translation_map,
        )
        declared_type_element.id_short = declared_type.identifier

        drop_ins_submodel.submodel_elements.append(declared_type_element)

    environment.submodels = [drop_ins_submodel]

    for entity in schema.entities:
        if len(entity.descendant_concrete_entities) > 0:
            entity_select_collection = _entity_to_select_collection(
                entity=entity,
                drop_ins_id=drop_ins_id,
                smt_id_prefix=smt_id_prefix,
                entity_translation_map=entity_translation_map,
            )
            entity_select_collection.id_short = f"{entity.identifier}_select"

            drop_ins_submodel.submodel_elements.append(entity_select_collection)

        if entity.abstract:
            continue

        entity_elements = _attributes_to_elements(
            attributes=entity.attributes,
            drop_ins_id=drop_ins_id,
            smt_id_prefix=smt_id_prefix,
            entity_translation_map=entity_translation_map,
        )

        entity_translation = entity_translation_map[entity]

        assert (
            entity_translation is not None
        ), "Entity translation must be defined for concrete entities."

        if entity_translation is EntityTranslation.SUBMODEL:
            assert environment.submodels is not None
            environment.submodels.append(
                aas_types.Submodel(
                    id=f"{smt_id_prefix}/{entity.identifier}",
                    submodel_elements=(
                        entity_elements if len(entity_elements) > 0 else None
                    ),
                )
            )

        elif entity_translation is EntityTranslation.SUBMODEL_ELEMENT_COLLECTION:
            drop_ins_submodel.submodel_elements.append(
                aas_types.SubmodelElementCollection(
                    id_short=entity.identifier,
                    value=(entity_elements if len(entity_elements) > 0 else None),
                )
            )
        else:
            # noinspection PyTypeChecker
            assert_never(entity_translation)

    verification_errors = list(aas_verification.verify(environment))
    if len(verification_errors) > 0:
        errors_joined = "\n".join(
            f"{verification_error.path}: {verification_error.cause}"
            for verification_error in verification_errors
        )

        first_offender = _find_offender_and_dump_it(
            environment=environment, error=verification_errors[0]
        )

        raise AssertionError(
            "The resulting AAS environment is invalid -- "
            "there are one or more violations of AAS meta-model:\n"
            f"{errors_joined}\n\n"
            f"The first offender at {verification_errors[0].path} was:\n"
            f"{first_offender}"
        )

    return environment
