"""Iterate over IFC entities and see if we can easily transform them to simple IR."""

import argparse
import os
import pathlib
import sys
from typing import List, Optional

from express_schema import parse

from aas_smt_from_ifc.common import bullet_points, NonEmptySequence


def _check(schema: parse.Schema) -> Optional[NonEmptySequence[str]]:
    """
    Check that attributes of all the entities are named attributes.

    Return a list of messages if that is not the case.
    """
    messages: List[str] = []
    for entity_declaration in schema.entity_declarations:
        for attribute_definition in entity_declaration.explicit_clauses:
            for attribute in attribute_definition.attributes:
                if not isinstance(attribute, parse.NameRef):
                    messages.append(
                        f"Expected only NameRef's in attribute definitions, "
                        f"but got: {parse.dump(attribute)} "
                        f"in entity {entity_declaration.identifier}"
                    )

    if len(messages) > 0:
        return NonEmptySequence(messages)

    return None


def main() -> int:
    """Execute the main routine."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.parse_args()

    this_dir = pathlib.Path(os.path.realpath(__file__)).parent
    repo_root = this_dir.parent

    fail = False
    for path in sorted((repo_root/"test_data"/"schemas").glob("*.exp")):
        text = path.read_text(encoding='utf-8')

        print(f"Parsing {path} ...")
        schema, parse_errors = parse.parse(text)
        if parse_errors is not None:
            print(
                f"Failed parsing {path} due to one or more errors:\n"
                f"{bullet_points([str(error) for error in parse_errors])}",
                file=sys.stderr
            )
            fail = True
            continue

        print(f"Checking {path} ...")
        errors = _check(schema)
        if errors is not None:
            print(
                f"One or more checks on {path} failed:\n"
                f"{bullet_points(errors)}"
            )
            fail = True

    if fail:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
