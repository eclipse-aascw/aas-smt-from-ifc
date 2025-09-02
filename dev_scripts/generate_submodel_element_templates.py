"""Generate the collection of submodel element templates to be referenced by IFC."""
import json
import pathlib
import os
import argparse
import sys
from typing import TextIO

from aas_core3 import (
    types as aas_types,
    jsonization as aas_jsonization,
    verification as aas_verification
)
from aas_core3.types import DataTypeDefXSD

from aas_smt_from_ifc.common import bullet_points

NAMESPACE = "https://aas-smt-from-ifc.aas-core-works.org"

def _generate_to(stream: TextIO) -> None:
    """Write the environment with submodel element templates to ``stream``."""
    submodel = aas_types.Submodel(
        id=f"{NAMESPACE}/template_submodel_elements",
        submodel_elements=[
            aas_types.Property(
                id_short="UNDEFINED",
                value_type=aas_types.DataTypeDefXSD.STRING,
                value="?",
                description=[
                    aas_types.LangStringTextType(
                        language="en",
                        text="Represent an undefined value."
                    )
                ]
            ),
            aas_types.Property(
                id_short="Logical",
                value_type=aas_types.DataTypeDefXSD.STRING,
                qualifiers=[
                    aas_types.Qualifier(
                        type="SMT/allowedValue",
                        value_type=DataTypeDefXSD.STRING,
                        value="true|false|unknown"
                    )
                ],
                description=[
                    aas_types.LangStringTextType(
                        language="en",
                        text="Represent a logical value."
                    )
                ]
            ),
        ]
    )

    environment = aas_types.Environment(
        submodels=[submodel]
    )

    errors = list(str(error) for error in aas_verification.verify(environment))
    assert len(errors) == 0, (
        f"Unexpected verification errors:\n"
        f"{bullet_points(errors)}"
    )

    jsonable = aas_jsonization.to_jsonable(environment)
    # noinspection PyTypeChecker
    json.dump(jsonable, stream)



def main() -> int:
    """Execute the main routine."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        help=(
            "Path where to write the submodel with "
            "the submodel element templates; if '-', write to STDOUT."
        ),
        default='-'
    )
    args = parser.parse_args()

    output = args.output
    assert isinstance(output, str)

    if output == '-':
        _generate_to(sys.stdout)
    else:
        path = pathlib.Path(output)
        with path.open('wt', encoding='utf-8') as fid:
            _generate_to(fid)

    return 0

if __name__ == "__main__":
    sys.exit(main())
