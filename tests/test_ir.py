# SPDX-FileCopyrightText: 2025 aas-smt-from-ifc AUTHORS
#
# SPDX-License-Identifier: MIT

# pylint: disable=missing-docstring
# pylint: disable=protected-access

import decimal
import unittest
from typing import List, Optional
from unittest.mock import Mock

from express_schema import parse, lex

import tests.common
from aas_smt_from_ifc import ir
from aas_smt_from_ifc.common import bullet_points


class TestTopologicalSort(unittest.TestCase):

    @staticmethod
    def _create_mock_entity(
        identifier: str, supertypes: Optional[List[ir.Entity]] = None
    ) -> ir.Entity:
        entity = Mock(spec=ir.Entity)
        entity.identifier = lex.Identifier(identifier)
        entity.supertypes = supertypes or []
        entity.subtypes = []
        return entity

    def test_empty_list(self) -> None:
        result, error = ir._topologically_sorted_entities([])
        self.assertIsNone(error)
        self.assertEqual([], result)

    def test_single_entity_no_supertypes(self) -> None:
        entity_a = self._create_mock_entity("A")

        result, error = ir._topologically_sorted_entities([entity_a])
        self.assertIsNone(error)
        self.assertEqual([entity_a], result)

    def test_simple_inheritance_chain(self) -> None:
        entity_a = self._create_mock_entity("A")
        entity_b = self._create_mock_entity("B", [entity_a])
        entity_c = self._create_mock_entity("C", [entity_b])

        result, error = ir._topologically_sorted_entities(
            [entity_c, entity_b, entity_a]
        )
        self.assertIsNone(error)
        self.assertEqual([entity_a, entity_b, entity_c], result)

    def test_multiple_inheritance(self) -> None:
        entity_a = self._create_mock_entity("A")
        entity_b = self._create_mock_entity("B")
        entity_c = self._create_mock_entity("C", [entity_a, entity_b])

        result, error = ir._topologically_sorted_entities(
            [entity_c, entity_b, entity_a]
        )

        assert error is None
        assert result is not None

        self.assertIn(entity_a, result)
        self.assertIn(entity_b, result)
        self.assertIn(entity_c, result)
        self.assertTrue(result.index(entity_a) < result.index(entity_c))
        self.assertTrue(result.index(entity_b) < result.index(entity_c))

    def test_diamond_inheritance(self) -> None:
        entity_a = self._create_mock_entity("A")
        entity_b = self._create_mock_entity("B", [entity_a])
        entity_c = self._create_mock_entity("C", [entity_a])
        entity_d = self._create_mock_entity("D", [entity_b, entity_c])

        result, error = ir._topologically_sorted_entities(
            [entity_d, entity_c, entity_b, entity_a]
        )
        assert error is None
        assert result is not None

        self.assertTrue(result.index(entity_a) < result.index(entity_b))
        self.assertTrue(result.index(entity_a) < result.index(entity_c))
        self.assertTrue(result.index(entity_b) < result.index(entity_d))
        self.assertTrue(result.index(entity_c) < result.index(entity_d))

    def test_circular_dependency_detection(self) -> None:
        entity_a = self._create_mock_entity("A")
        entity_b = self._create_mock_entity("B", [entity_a])

        # Create circular dependency: A -> B and B -> A
        # noinspection PyPropertyAccess
        entity_a.supertypes = [entity_b]  # type: ignore

        result, error = ir._topologically_sorted_entities([entity_a, entity_b])
        assert error is not None
        assert result is None

        self.assertEqual("Supertype cycle detected: ('A', 'B'), ('B', 'A')", error)

    def test_complex_hierarchy(self) -> None:
        entity_a = self._create_mock_entity("A")
        entity_b = self._create_mock_entity("B")
        entity_c = self._create_mock_entity("C", [entity_a])
        entity_d = self._create_mock_entity("D", [entity_a, entity_b])
        entity_e = self._create_mock_entity("E", [entity_c, entity_d])

        result, error = ir._topologically_sorted_entities(
            [entity_e, entity_d, entity_c, entity_b, entity_a]
        )
        assert error is None
        assert result is not None

        # We verify that all entities are present.
        self.assertEqual(len(result), 5)

        self.assertTrue(result.index(entity_a) < result.index(entity_c))
        self.assertTrue(result.index(entity_a) < result.index(entity_d))
        self.assertTrue(result.index(entity_b) < result.index(entity_d))
        self.assertTrue(result.index(entity_c) < result.index(entity_e))
        self.assertTrue(result.index(entity_d) < result.index(entity_e))

    def test_self_circular_dependency(self) -> None:
        entity_a = self._create_mock_entity("A")

        # NOTE (mristin):
        # This is a self-reference.
        # noinspection PyPropertyAccess
        entity_a.supertypes = [entity_a]  # type: ignore

        result, error = ir._topologically_sorted_entities([entity_a])
        assert result is None
        assert error is not None

        self.assertEqual("Supertype cycle detected: ('A', 'A')", error)


class TestTranslate(unittest.TestCase):

    def test_empty_schema(self) -> None:
        schema_text = "SCHEMA test_schema; END_SCHEMA;"

        parsed_schema, parse_errors = parse.parse(schema_text)
        assert parse_errors is None
        assert parsed_schema is not None

        ir_schema, ir_errors = ir.translate(parsed_schema)
        assert ir_errors is None
        assert ir_schema is not None

        self.assertEqual(len(ir_schema.entities), 0)

    def test_inheritance_hierarchy(self) -> None:
        schema_text = """
        SCHEMA test_schema;

        ENTITY A;
            attr_a : INTEGER;
        END_ENTITY;

        ENTITY B;
            attr_b : STRING;
        END_ENTITY;

        ENTITY C
            SUBTYPE OF (A, B);
            attr_c : REAL;
        END_ENTITY;

        END_SCHEMA;
        """

        parsed_schema, parse_errors = parse.parse(schema_text)
        assert parse_errors is None
        assert parsed_schema is not None

        ir_schema, ir_errors = ir.translate(parsed_schema)
        assert ir_errors is None
        assert ir_schema is not None

        self.assertEqual(len(ir_schema.entities), 3)

        entity_a = ir_schema.entities_by_id[lex.Identifier("A")]
        entity_b = ir_schema.entities_by_id[lex.Identifier("B")]
        entity_c = ir_schema.entities_by_id[lex.Identifier("C")]

        # Check supertypes
        # noinspection PyTypeChecker
        self.assertListEqual([], entity_a.supertypes)  # type: ignore
        # noinspection PyTypeChecker
        self.assertListEqual([], entity_b.supertypes)  # type: ignore
        # noinspection PyTypeChecker
        self.assertListEqual([entity_a, entity_b], entity_c.supertypes)  # type: ignore

        # Check subtypes
        # noinspection PyTypeChecker
        self.assertListEqual([], entity_c.subtypes)  # type: ignore
        # noinspection PyTypeChecker
        self.assertListEqual([entity_c], entity_a.subtypes)  # type: ignore
        # noinspection PyTypeChecker
        self.assertListEqual([entity_c], entity_b.subtypes)  # type: ignore

        # Check attributes
        self.assertListEqual(
            [lex.Identifier("attr_a")], [attr.name for attr in entity_a.attributes]
        )

        self.assertListEqual(
            [lex.Identifier("attr_b")], [attr.name for attr in entity_b.attributes]
        )

        # Entity C should have inherited attr_a and attr_b, and have its own attr_c.
        self.assertListEqual(
            [
                lex.Identifier("attr_a"),
                lex.Identifier("attr_b"),
                lex.Identifier("attr_c"),
            ],
            [attr.name for attr in entity_c.attributes],
        )

        assert (
            entity_c.attribute_by_name[lex.Identifier("attr_a")].specified_for
            is entity_a
        )

        assert (
            entity_c.attribute_by_name[lex.Identifier("attr_b")].specified_for
            is entity_b
        )

        assert (
            entity_c.attribute_by_name[lex.Identifier("attr_c")].specified_for
            is entity_c
        )


class TestConcreteTypes(unittest.TestCase):

    def test_empty_entities(self) -> None:
        schema_text = "SCHEMA test_schema; END_SCHEMA;"

        parsed_schema, parse_errors = parse.parse(schema_text)
        assert parse_errors is None
        assert parsed_schema is not None

        ir_schema, ir_errors = ir.translate(parsed_schema)
        assert ir_errors is None
        assert ir_schema is not None

        self.assertEqual(len(ir_schema.entities), 0)

    def test_concrete_classes_without_subtypes(self) -> None:
        schema_text = """
        SCHEMA test_schema;

        ENTITY ConcreteA;
            attr_a : INTEGER;
        END_ENTITY;

        ENTITY ConcreteB;
            attr_b : STRING;
        END_ENTITY;

        END_SCHEMA;
        """

        parsed_schema, parse_errors = parse.parse(schema_text)
        assert parse_errors is None, (
            f"One or more parse errors:\n" f"{bullet_points(map(str, parse_errors))}"
        )
        assert parsed_schema is not None

        ir_schema, ir_errors = ir.translate(parsed_schema)
        assert ir_errors is None
        assert ir_schema is not None

        entity_a = ir_schema.entities_by_id[lex.Identifier("ConcreteA")]
        entity_b = ir_schema.entities_by_id[lex.Identifier("ConcreteB")]

        # Both entities should be concrete and only include themselves in concrete_types
        self.assertFalse(entity_a.abstract)
        self.assertFalse(entity_b.abstract)
        self.assertEqual([], list(entity_a.descendant_concrete_entities))
        self.assertEqual([], list(entity_b.descendant_concrete_entities))

    def test_linear_inheritance(self) -> None:
        schema_text = """
        SCHEMA test_schema;

        ENTITY AbstractGrandparent
            ABSTRACT SUPERTYPE OF (ConcreteParent);
            attr_gp : INTEGER;
        END_ENTITY;

        ENTITY ConcreteParent
            SUPERTYPE OF (ConcreteChild)
            SUBTYPE OF (AbstractGrandparent);
            attr_p : STRING;
        END_ENTITY;

        ENTITY ConcreteChild
            SUBTYPE OF (ConcreteParent);
            attr_c : REAL;
        END_ENTITY;

        END_SCHEMA;
        """

        parsed_schema, parse_errors = parse.parse(schema_text)
        assert parse_errors is None, (
            f"One or more parse errors:\n" f"{bullet_points(map(str, parse_errors))}"
        )
        assert parsed_schema is not None

        ir_schema, ir_errors = ir.translate(parsed_schema)
        assert ir_errors is None
        assert ir_schema is not None

        grandparent = ir_schema.entities_by_id[lex.Identifier("AbstractGrandparent")]
        parent = ir_schema.entities_by_id[lex.Identifier("ConcreteParent")]
        child = ir_schema.entities_by_id[lex.Identifier("ConcreteChild")]

        # Check abstractness
        self.assertTrue(grandparent.abstract)
        self.assertFalse(parent.abstract)
        self.assertFalse(child.abstract)

        # Check concrete types
        self.assertEqual(
            [child, parent], list(grandparent.descendant_concrete_entities)
        )
        self.assertEqual([child], list(parent.descendant_concrete_entities))
        self.assertEqual([], list(child.descendant_concrete_entities))

    def test_multiple_inheritance(self) -> None:
        schema_text = """
        SCHEMA test_schema;

        ENTITY AbstractA
            ABSTRACT SUPERTYPE OF (ONEOF (ConcreteC, ConcreteD));
            attr_a : INTEGER;
        END_ENTITY;

        ENTITY AbstractB
            ABSTRACT SUPERTYPE OF (ONEOF (ConcreteC, ConcreteD));
            attr_b : STRING;
        END_ENTITY;

        ENTITY ConcreteC
            SUBTYPE OF (AbstractA, AbstractB);
            attr_c : REAL;
        END_ENTITY;

        ENTITY ConcreteD
            SUBTYPE OF (AbstractA);
            attr_d : BOOLEAN;
        END_ENTITY;

        END_SCHEMA;
        """

        parsed_schema, parse_errors = parse.parse(schema_text)
        assert parse_errors is None, (
            f"One or more parse errors:\n" f"{bullet_points(map(str, parse_errors))}"
        )
        assert parsed_schema is not None

        ir_schema, ir_errors = ir.translate(parsed_schema)
        assert ir_errors is None
        assert ir_schema is not None

        abstract_a = ir_schema.entities_by_id[lex.Identifier("AbstractA")]
        abstract_b = ir_schema.entities_by_id[lex.Identifier("AbstractB")]
        concrete_c = ir_schema.entities_by_id[lex.Identifier("ConcreteC")]
        concrete_d = ir_schema.entities_by_id[lex.Identifier("ConcreteD")]

        # Check abstractness
        self.assertTrue(abstract_a.abstract)
        self.assertTrue(abstract_b.abstract)
        self.assertFalse(concrete_c.abstract)
        self.assertFalse(concrete_d.abstract)

        # Check concrete types
        # AbstractA should have both ConcreteC and ConcreteD as concrete types
        self.assertEqual(
            [concrete_d, concrete_c], list(abstract_a.descendant_concrete_entities)
        )
        # AbstractB should only have ConcreteC as concrete type
        self.assertEqual([concrete_c], list(abstract_b.descendant_concrete_entities))
        # Concrete entities should only have themselves
        self.assertEqual([], list(concrete_c.descendant_concrete_entities))
        self.assertEqual([], list(concrete_d.descendant_concrete_entities))


class TestInterpretingOfTypeDeclarationDomainRules(unittest.TestCase):
    def test_string_choice_intersection_from_multiple_domain_rules(self) -> None:
        schema_text = """
        SCHEMA test_schema;

        TYPE RestrictedString = STRING;
            WHERE
                WR1: SELF IN ['apple', 'banana', 'cherry'];
                WR2: SELF IN ['apple', 'banana', 'date'];
        END_TYPE;

        ENTITY SomeEntity;
            someAttribute: RestrictedString;
        END_ENTITY;

        END_SCHEMA;
        """

        parsed_schema, parse_errors = parse.parse(schema_text)
        assert parse_errors is None, list(map(str, parse_errors))
        assert parsed_schema is not None

        schema, translation_errors = ir.translate(parsed=parsed_schema)
        assert translation_errors is None
        assert schema is not None

        some_entity = schema.entities_by_id[lex.Identifier("SomeEntity")]
        tajp = some_entity.attribute_by_name[lex.Identifier("someAttribute")].tajp

        assert isinstance(tajp, ir.DeclaredType)
        self.assertEqual(tajp.identifier, "RestrictedString")

        resolved_tajp = ir.resolve_type(tajp)
        assert isinstance(resolved_tajp, ir.StringType)
        assert resolved_tajp.choice is not None

        # This is an intersection.
        self.assertEqual(["apple", "banana"], resolved_tajp.choice)

    def test_integer_bounds_from_multiple_constraints(self) -> None:
        schema_text = """
        SCHEMA test_schema;

        TYPE BoundedInteger = INTEGER;
            WHERE
                WR1: SELF >= 5;
                WR2: SELF <= 100;
                WR3: SELF > 5;
                WR4: SELF < 100;
                WR3: SELF > 3;
                WR3: SELF < 150;
        END_TYPE;

        ENTITY SomeEntity;
            someAttribute: BoundedInteger;
        END_ENTITY;

        END_SCHEMA;
        """

        parsed_schema, parse_errors = parse.parse(schema_text)
        assert parse_errors is None, list(map(str, parse_errors))
        assert parsed_schema is not None

        schema, translation_errors = ir.translate(parsed=parsed_schema)
        assert translation_errors is None
        assert schema is not None

        some_entity = schema.entities_by_id[lex.Identifier("SomeEntity")]
        tajp = some_entity.attribute_by_name[lex.Identifier("someAttribute")].tajp

        assert isinstance(tajp, ir.DeclaredType)
        self.assertEqual(tajp.identifier, "BoundedInteger")

        resolved_tajp = ir.resolve_type(tajp)
        assert isinstance(resolved_tajp, ir.IntegerType)

        # The most strict bounds are picked.

        assert resolved_tajp.min_value is not None
        self.assertEqual(5, resolved_tajp.min_value.value)
        self.assertFalse(resolved_tajp.min_value.inclusive)

        assert resolved_tajp.max_value is not None
        self.assertEqual(100, resolved_tajp.max_value.value)
        self.assertFalse(resolved_tajp.max_value.inclusive)

    def test_real_bounds_from_interval_and_individual_constraints(self) -> None:
        schema_text = """
        SCHEMA test_schema;

        TYPE BoundedReal = REAL;
            WHERE
                WR1: 1.5 <= SELF <= 10.5;
                WR2: SELF >= 2.0;
                WR3: SELF < 9.0;
        END_TYPE;

        ENTITY SomeEntity;
            someAttribute: BoundedReal;
        END_ENTITY;

        END_SCHEMA;
        """

        parsed_schema, parse_errors = parse.parse(schema_text)
        assert parse_errors is None, list(map(str, parse_errors))
        assert parsed_schema is not None

        schema, translation_errors = ir.translate(parsed=parsed_schema)
        assert translation_errors is None
        assert schema is not None

        some_entity = schema.entities_by_id[lex.Identifier("SomeEntity")]
        tajp = some_entity.attribute_by_name[lex.Identifier("someAttribute")].tajp

        assert isinstance(tajp, ir.DeclaredType)
        self.assertEqual(tajp.identifier, "BoundedReal")

        resolved_tajp = ir.resolve_type(tajp)
        assert isinstance(resolved_tajp, ir.RealType)

        # The most strict bounds are picked.

        assert resolved_tajp.min_value is not None
        self.assertEqual(decimal.Decimal("2.0"), resolved_tajp.min_value.value)
        self.assertTrue(resolved_tajp.min_value.inclusive)

        assert resolved_tajp.max_value is not None
        self.assertEqual(decimal.Decimal("9.0"), resolved_tajp.max_value.value)
        self.assertFalse(resolved_tajp.max_value.inclusive)

    def test_integer_equality_constraint(self) -> None:
        schema_text = """
        SCHEMA test_schema;

        TYPE ExactInteger = INTEGER;
            WHERE
                WR1: SELF = 42;
        END_TYPE;

        ENTITY SomeEntity;
            someAttribute: ExactInteger;
        END_ENTITY;

        END_SCHEMA;
        """

        parsed_schema, parse_errors = parse.parse(schema_text)
        assert parse_errors is None, list(map(str, parse_errors))
        assert parsed_schema is not None

        schema, translation_errors = ir.translate(parsed=parsed_schema)
        assert translation_errors is None
        assert schema is not None

        some_entity = schema.entities_by_id[lex.Identifier("SomeEntity")]
        tajp = some_entity.attribute_by_name[lex.Identifier("someAttribute")].tajp

        assert isinstance(tajp, ir.DeclaredType)
        self.assertEqual(tajp.identifier, "ExactInteger")

        resolved_tajp = ir.resolve_type(tajp)
        assert isinstance(resolved_tajp, ir.IntegerType)

        # The bounds are exact for equality.

        assert resolved_tajp.min_value is not None
        self.assertEqual(42, resolved_tajp.min_value.value)
        self.assertTrue(resolved_tajp.min_value.inclusive)

        assert resolved_tajp.max_value is not None
        self.assertEqual(42, resolved_tajp.max_value.value)
        self.assertTrue(resolved_tajp.max_value.inclusive)

    def test_real_equality_constraint(self) -> None:
        schema_text = """
        SCHEMA test_schema;

        TYPE ExactReal = REAL;
            WHERE
                WR1: SELF = 3.14159;
        END_TYPE;

        ENTITY SomeEntity;
            someAttribute: ExactReal;
        END_ENTITY;

        END_SCHEMA;
        """

        parsed_schema, parse_errors = parse.parse(schema_text)
        assert parse_errors is None, list(map(str, parse_errors))
        assert parsed_schema is not None

        schema, translation_errors = ir.translate(parsed=parsed_schema)
        assert translation_errors is None
        assert schema is not None

        some_entity = schema.entities_by_id[lex.Identifier("SomeEntity")]
        tajp = some_entity.attribute_by_name[lex.Identifier("someAttribute")].tajp

        assert isinstance(tajp, ir.DeclaredType)
        self.assertEqual(tajp.identifier, "ExactReal")

        resolved_tajp = ir.resolve_type(tajp)
        assert isinstance(resolved_tajp, ir.RealType)

        # The bounds are exact for equality.

        assert resolved_tajp.min_value is not None
        self.assertEqual(decimal.Decimal("3.14159"), resolved_tajp.min_value.value)
        self.assertTrue(resolved_tajp.min_value.inclusive)

        assert resolved_tajp.max_value is not None
        self.assertEqual(decimal.Decimal("3.14159"), resolved_tajp.max_value.value)
        self.assertTrue(resolved_tajp.max_value.inclusive)

    def test_list_of_string_choice_type_constraint_inference(self) -> None:
        schema_text = """
        SCHEMA test_schema;

        TYPE Color = STRING;
            WHERE
                WR1: SELF IN ['red', 'green', 'blue'];
        END_TYPE;

        TYPE ColorList = LIST [1:5] OF Color;
        END_TYPE;

        ENTITY SomeEntity;
            colorAttribute: Color;
            colorListAttribute: ColorList;
        END_ENTITY;

        END_SCHEMA;
        """

        parsed_schema, parse_errors = parse.parse(schema_text)
        assert parse_errors is None, list(map(str, parse_errors))
        assert parsed_schema is not None

        schema, translation_errors = ir.translate(parsed=parsed_schema)
        assert translation_errors is None
        assert schema is not None

        some_entity = schema.entities_by_id[lex.Identifier("SomeEntity")]

        # The Color type should have the choice inferred.

        color_type = some_entity.attribute_by_name[
            lex.Identifier("colorAttribute")
        ].tajp
        assert isinstance(color_type, ir.DeclaredType)
        self.assertEqual(color_type.identifier, "Color")

        resolved_color_type = ir.resolve_type(color_type)
        assert isinstance(
            resolved_color_type, ir.StringType
        ), f"{type(resolved_color_type)=}"
        assert resolved_color_type.choice is not None
        self.assertEqual(["red", "green", "blue"], resolved_color_type.choice)

        # The ColorList type should also have the choice constraint propagated
        # to its items.

        color_list_type = some_entity.attribute_by_name[
            lex.Identifier("colorListAttribute")
        ].tajp
        assert isinstance(color_list_type, ir.DeclaredType)
        self.assertEqual(color_list_type.identifier, "ColorList")

        resolved_color_list_type = ir.resolve_type(color_list_type)
        assert isinstance(resolved_color_list_type, ir.ListType)

        assert isinstance(resolved_color_list_type.items, ir.DeclaredType)

        resolved_items_type = ir.resolve_type(resolved_color_list_type.items)
        assert isinstance(resolved_items_type, ir.StringType)
        assert resolved_items_type.choice is not None
        self.assertEqual(["red", "green", "blue"], resolved_items_type.choice)

        # We also check the list bounds for completeness.
        assert resolved_color_list_type.min_length is not None
        self.assertEqual(1, resolved_color_list_type.min_length)

        assert resolved_color_list_type.max_length is not None
        self.assertEqual(5, resolved_color_list_type.max_length)

    def test_list_with_bound_spec_of_entity(self) -> None:
        schema_text = """
        SCHEMA test_schema;

        TYPE EntityList = LIST [1:10] OF SomeEntity;
        END_TYPE;

        ENTITY SomeEntity;
            someAttribute: EntityList;
        END_ENTITY;

        END_SCHEMA;
        """

        parsed_schema, parse_errors = parse.parse(schema_text)
        assert parse_errors is None, list(map(str, parse_errors))
        assert parsed_schema is not None

        schema, translation_errors = ir.translate(parsed=parsed_schema)
        assert translation_errors is None
        assert schema is not None

        some_entity = schema.entities_by_id[lex.Identifier("SomeEntity")]

        entity_list_type = some_entity.attribute_by_name[
            lex.Identifier("someAttribute")
        ].tajp

        assert isinstance(entity_list_type, ir.DeclaredType)
        self.assertEqual(entity_list_type.identifier, "EntityList")

        resolved_entity_list_type = ir.resolve_type(entity_list_type)
        assert isinstance(resolved_entity_list_type, ir.ListType)

        # The list must have the correct bounds.

        assert resolved_entity_list_type.min_length is not None
        self.assertEqual(1, resolved_entity_list_type.min_length)

        assert resolved_entity_list_type.max_length is not None
        self.assertEqual(10, resolved_entity_list_type.max_length)

        # The type of list items must reference the entity.
        self.assertIs(resolved_entity_list_type.items, some_entity)

    def test_list_with_bound_spec_of_enumeration(self) -> None:
        schema_text = """
        SCHEMA test_schema;

        TYPE SomeEnumeration = ENUMERATION OF (good, bad);
        END_TYPE;

        TYPE EnumerationList = LIST [2:8] OF SomeEnumeration;
        END_TYPE;
        
        ENTITY SomeEntity;
            someAttribute: EnumerationList;
        END_ENTITY;

        END_SCHEMA;
        """

        parsed_schema, parse_errors = parse.parse(schema_text)
        assert parse_errors is None, list(map(str, parse_errors))
        assert parsed_schema is not None

        schema, translation_errors = ir.translate(parsed=parsed_schema)
        assert translation_errors is None
        assert schema is not None

        some_entity = schema.entities_by_id[lex.Identifier("SomeEntity")]

        some_enumeration = schema.enumerations_by_id[lex.Identifier("SomeEnumeration")]

        enumeration_list_type = some_entity.attribute_by_name[
            lex.Identifier("someAttribute")
        ].tajp

        assert isinstance(enumeration_list_type, ir.DeclaredType)
        self.assertEqual(enumeration_list_type.identifier, "EnumerationList")

        resolved_enumeration_list_type = ir.resolve_type(enumeration_list_type)
        assert isinstance(resolved_enumeration_list_type, ir.ListType)

        # The list must have the correct bounds.

        assert resolved_enumeration_list_type.min_length is not None
        self.assertEqual(2, resolved_enumeration_list_type.min_length)

        assert resolved_enumeration_list_type.max_length is not None
        self.assertEqual(8, resolved_enumeration_list_type.max_length)

        # The type of the list items must reference the enumeration.

        self.assertIs(resolved_enumeration_list_type.items, some_enumeration)


class TestOnRealSchemas(unittest.TestCase):
    def test_smoke(self) -> None:
        schema_paths = list(
            sorted((tests.common.TEST_DATA_DIR / "schemas").glob("**/*.exp"))
        )

        for schema_path in schema_paths:
            text = schema_path.read_text(encoding="utf-8")
            parsed_schema, parse_errors = parse.parse(text)

            assert parse_errors is None
            assert parsed_schema is not None

            schema, translation_errors = ir.translate(parsed=parsed_schema)

            assert translation_errors is None
            assert schema is not None

            # NOTE (mristin):
            # This is only a smoke test -- we test that we can successfully parse and
            # translate the schema.


if __name__ == "__main__":
    unittest.main()
