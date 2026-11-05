# SPDX-FileCopyrightText: 2025 aas-smt-from-ifc AUTHORS
#
# SPDX-License-Identifier: MIT

# pylint: disable=missing-docstring
# pylint: disable=protected-access

import json
import os
import unittest

from aas_core3 import jsonization as aas_jsonization
from express_schema import parse

import tests.common
from aas_smt_from_ifc import ir, smt
from aas_smt_from_ifc.common import bullet_points


class TestAgainstRecorded(unittest.TestCase):
    def test_against_golden_files(self) -> None:
        schema_paths = list(
            sorted((tests.common.TEST_DATA_DIR / "test_smt").glob("**/schema.express"))
        )

        case_dirs = [schema_path.parent for schema_path in schema_paths]
        case_dirs_by_name = {case_dir.name: case_dir for case_dir in case_dirs}

        selected_case_var = "AAS_SMT_FROM_IFC_TEST_SMT_CASE"
        selected_case_name = os.environ.get(selected_case_var, None)
        if selected_case_name is not None:
            if selected_case_name not in case_dirs_by_name:
                raise RuntimeError(
                    f"Unexpected case from environment variable {selected_case_var}"
                )

            run_case_dirs = [case_dirs_by_name[selected_case_name]]
        else:
            run_case_dirs = case_dirs

        for case_dir in run_case_dirs:
            if not case_dir.is_dir():
                continue

            schema_path = case_dir / "schema.express"

            text = schema_path.read_text(encoding="utf-8")
            parsed_schema, parse_errors = parse.parse(text)

            if parse_errors is not None:
                parse_errors_as_bullet_points = bullet_points(
                    str(parse_error) for parse_error in parse_errors
                )
                raise AssertionError(
                    f"There are one or more parsing errors in {schema_path}:\n"
                    f"{parse_errors_as_bullet_points}"
                )

            assert parsed_schema is not None

            schema, translation_errors = ir.translate(parsed=parsed_schema)

            if translation_errors is not None:
                raise AssertionError(
                    f"There are one or more translation errors in {schema_path}:\n"
                    f"{bullet_points(translation_errors)}"
                )

            assert schema is not None

            environment = smt.translate(
                schema=schema,
                base_namespace="https://aas-smt-from-ifc.aas-core-works.org",
                entity_is_submodel=smt.is_concrete_subtype_of_ifc_root,
            )

            got = json.dumps(aas_jsonization.to_jsonable(environment), indent=2)

            expected_result_path = case_dir / "environment.json"

            if tests.common.RECORDING:
                expected_result_path.write_text(got, encoding="utf-8")
            else:
                if not expected_result_path.exists():
                    raise FileNotFoundError(
                        f"The golden file {expected_result_path} could not "
                        f"be found. Did you set the environment variable "
                        f"{tests.common.RECORDING_VAR} and "
                        f"record the golden file before?"
                    )
                expected = expected_result_path.read_text(encoding="utf-8")

                self.assertEqual(
                    expected,
                    got,
                    f"For the golden file {expected_result_path}",
                )


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
            assert ir_errors is None
            assert schema is not None

            _ = smt.translate(
                schema=schema,
                base_namespace="https://aas-smt-from-ifc.aas-core-works.org",
                entity_is_submodel=smt.is_concrete_subtype_of_ifc_root,
            )

            # NOTE (mristin):
            # This is only a smoke test -- we test that we can successfully parse and
            # translate the schema.


if __name__ == "__main__":
    unittest.main()
