# pylint: disable=missing-docstring

import os.path
import pathlib

import tests.common
from aas_smt_from_ifc import parse, ir, codegen, smt
from aas_smt_from_ifc.common import bullet_points


def main() -> None:
    this_dir = pathlib.Path(os.path.realpath(__file__)).parent

    for schema_path in sorted((tests.common.TEST_DATA_DIR / "schemas").glob("*.exp")):
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

        code = codegen.generate(
            schema=schema,
            base_namespace="https://aas-smt-from-ifc.aas-core-works.org",
            entity_is_submodel=smt.is_concrete_subtype_of_ifc_root,
        )

        target_path = this_dir / f"{schema.identifier}.py"
        target_path.write_text(code, encoding="utf-8")
        print(f"Written to: {target_path}")


if __name__ == "__main__":
    main()
