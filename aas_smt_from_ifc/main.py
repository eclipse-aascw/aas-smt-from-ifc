"""Convert IFC data structures to AAS Submodel Templates."""

import argparse
import enum
import json
import pathlib
import sys
from typing import Mapping

from aas_core3 import jsonization as aas_jsonization, xmlization as aas_xmlization
from express_schema import parse

import aas_smt_from_ifc
from aas_smt_from_ifc import ir, codegen, smt
from aas_smt_from_ifc.common import bullet_points, assert_never

assert aas_smt_from_ifc.__doc__ == __doc__


class Target(enum.Enum):
    """List available generation targets."""

    SUBMODEL_TEMPLATES = "submodel-templates"
    TO_AAS_CODE = "to-aas-code"


_TARGET_MAP: Mapping[str, Target] = {target.value: target for target in Target}


def main(prog: str) -> int:
    """
    Execute the main routine.

    :param prog: name of the program to be displayed in the help
    :return: exit code
    """
    parser = argparse.ArgumentParser(prog=prog, description=__doc__)
    parser.add_argument(
        "--version", help="show the current version and exit", action="store_true"
    )
    parser.add_argument(
        "--target",
        help="Artefact to be generated",
        choices=[target.name for target in Target],
        type=str,
        required=True,
    )
    parser.add_argument(
        "--schema_path",
        help="Path to the input Express schema",
        required=True,
    )
    parser.add_argument(
        "--base_namespace",
        help=(
            "IRI to the namespace used as root, "
            "*e.g.*, 'https://aas-smt-from-ifc.aas-core-works.org'"
        ),
        required=True,
    )
    parser.add_argument(
        "--output_path",
        help=("Path where to write the generated artefact"),
        required=True,
    )

    # NOTE (mristin):
    # The module ``argparse`` is not flexible enough to understand special options such
    # as ``--version`` so we manually hard-wire.
    if "--version" in sys.argv and "--help" not in sys.argv:
        print(aas_smt_from_ifc.__version__)
        return 0

    args = parser.parse_args()
    schema_path = pathlib.Path(args.schema_path)
    base_namespace = str(args.base_namespace)
    target = _TARGET_MAP[args.target]
    output_path = pathlib.Path(args.output_path)

    if not schema_path.exists() or not schema_path.is_file():
        print(
            f"--schema_path does not exist or is not a file: {schema_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    text = schema_path.read_text(encoding="utf-8")
    parsed_schema, parse_errors = parse.parse(text)

    if parse_errors is not None:
        print(
            f"There were one or more parsing errors:\n"
            f"{bullet_points(map(str, parse_errors))}",
            file=sys.stderr,
        )
        return 1

    assert parsed_schema is not None

    schema, ir_errors = ir.translate(parsed=parsed_schema)

    if ir_errors is not None:
        ir_errors_bullet_points = bullet_points(ir_errors)
        print(
            f"Unexpected errors when translating to "
            f"Intermediate Representation:\n{ir_errors_bullet_points}",
            file=sys.stderr,
        )
        return 1

    assert schema is not None

    if target is Target.SUBMODEL_TEMPLATES:
        environment = smt.translate(
            schema=schema,
            base_namespace=base_namespace,
            entity_is_submodel=smt.is_concrete_subtype_of_ifc_root,
        )

        if output_path.suffix.lower() == ".json":
            jsonable = aas_jsonization.to_jsonable(environment)
            output_path.write_text(json.dumps(jsonable, indent=2), encoding="utf-8")

        elif output_path.suffix.lower() == ".xml":
            text = aas_xmlization.to_str(environment)
            output_path.write_text(text, encoding="utf-8")

        else:
            print(
                f"We can not determine the format of the output "
                f"based on the file extension: {output_path.suffix}",
                file=sys.stderr,
            )
            return 1

    elif target is Target.TO_AAS_CODE:
        code = codegen.generate(
            schema=schema,
            base_namespace=base_namespace,
            entity_is_submodel=smt.is_concrete_subtype_of_ifc_root,
        )

        output_path.write_text(code, encoding="utf-8")

    else:
        # noinspection PyTypeChecker
        assert_never(target)

    return 0


def entry_point() -> int:
    """Provide an entry point for a console script."""
    return main(prog="aas-smt-from-ifc")


if __name__ == "__main__":
    sys.exit(main(prog="aas-smt-from-ifc"))
