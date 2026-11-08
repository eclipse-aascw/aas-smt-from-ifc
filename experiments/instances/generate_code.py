# SPDX-FileCopyrightText: 2025 aas-smt-from-ifc AUTHORS
#
# SPDX-License-Identifier: MIT

# pylint: disable=missing-docstring

import os.path
import pathlib

from express_schema import parse

import tests.common
from aas_smt_from_ifc import ir, codegen, smt
from aas_smt_from_ifc.common import bullet_points

# NOTE (aaronzi, 2026-11-05):
# The code generator does not emit any copyright or license information, so we
# prepend the header to the generated modules ourselves. Otherwise, the headers
# would be lost on every re-generation. The generated code is translated from
# the IFC schemas, so the header also attributes the schema to buildingSMART,
# as the terms of the schemas ask for.
#
# REUSE-IgnoreStart
_LICENSE_HEADER = """\
# SPDX-FileCopyrightText: 2025 aas-smt-from-ifc AUTHORS
#
# SPDX-License-Identifier: MIT

"""
# REUSE-IgnoreEnd

_ATTRIBUTION = """\
# Generated from the EXPRESS schema {schema_file} of the Industry Foundation
# Classes (IFC) by buildingSMART International Limited, published at
# https://standards.buildingsmart.org/IFC/RELEASE/.

"""


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
        target_path.write_text(
            _LICENSE_HEADER + _ATTRIBUTION.format(schema_file=schema_path.name) + code,
            encoding="utf-8",
        )
        print(f"Written to: {target_path}")


if __name__ == "__main__":
    main()
