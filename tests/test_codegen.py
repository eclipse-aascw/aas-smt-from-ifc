# pylint: disable=missing-docstring

import unittest

from express_schema import parse

import tests.common
from aas_smt_from_ifc import ir, smt, codegen
from aas_smt_from_ifc.common import bullet_points


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

            schema, ir_errors = ir.translate(parsed=parsed_schema)

            if ir_errors is not None:
                ir_errors_bullet_points = bullet_points(ir_errors)
                raise AssertionError(
                    f"Unexpected errors when translating to "
                    f"Intermediate Representation:\n{ir_errors_bullet_points}"
                )

            assert schema is not None

            codegen.generate(
                schema=schema,
                base_namespace="https://aas-core-works.org",
                entity_is_submodel=smt.is_concrete_subtype_of_ifc_root,
            )

            # NOTE (mristin):
            # This is only a smoke test -- we test that we can successfully parse and
            # translate the schema.


if __name__ == "__main__":
    unittest.main()
