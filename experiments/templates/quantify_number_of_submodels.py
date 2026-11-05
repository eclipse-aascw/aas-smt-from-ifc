# SPDX-FileCopyrightText: 2025 aas-smt-from-ifc AUTHORS
#
# SPDX-License-Identifier: MIT

"""Count how many submodel templates we have pre IFC Express schema."""

import collections
import os
import pathlib
import sys
from typing import MutableMapping, List

from express_schema import parse

from aas_smt_from_ifc import ir, smt

# NOTE (mristin):
# We do not want to expose the internal functions just for the sake of the experiments.
# pylint: disable=protected-access

# noinspection PyProtectedMember
DOMAIN_RULE_MATCH_METHODS = [
    ir._TypeDomainRuleMatcher.try_self_compare_integer_or_real,
    ir._TypeDomainRuleMatcher.try_self_in_list_of_strings,
    ir._TypeDomainRuleMatcher.try_self_interval,
]


def _assert_all_match_methods_covered() -> None:
    expected = []
    # noinspection PyProtectedMember
    for attr_name in sorted(dir(ir._TypeDomainRuleMatcher)):
        if attr_name.startswith("try_"):
            # noinspection PyProtectedMember
            expected.append(getattr(ir._TypeDomainRuleMatcher, attr_name))

    assert (
        DOMAIN_RULE_MATCH_METHODS == expected
    ), f"Expected: {expected}, got: {DOMAIN_RULE_MATCH_METHODS}"


_assert_all_match_methods_covered()


def main() -> int:
    """Execute the main routine."""
    repo_dir = pathlib.Path(os.path.realpath(__file__)).parent.parent.parent

    schema_dir = repo_dir / "test_data" / "schemas"

    stats_dir = repo_dir / "experiments" / "templates" / "stats"

    for schema_path in sorted(schema_dir.glob("*.exp")):
        print(f"Quantifying {schema_path}...")

        blocks = [
            f"""\
# {schema_path.stem} SMT Statistics"""
        ]  # type: List[str]

        text = schema_path.read_text(encoding="utf-8")
        parsed_schema, parse_errors = parse.parse(text)

        assert parse_errors is None
        assert parsed_schema is not None

        schema, translation_errors = ir.translate(parsed=parsed_schema)
        assert translation_errors is None
        assert schema is not None

        blocks.append(f"Number of declared types: {len(schema.declared_types)}")

        number_of_abstract_entities = sum(
            1 for entity in schema.entities if entity.abstract
        )
        blocks.append(
            f"Number of entities: {len(schema.entities)}, "
            f"out of which {number_of_abstract_entities} abstract"
        )

        environment = smt.translate(
            schema=schema,
            base_namespace="https://aas-smt-from-ifc.aas-core-works.org",
            entity_is_submodel=smt.is_concrete_subtype_of_ifc_root,
        )

        number_of_submodel_templates = sum(
            1
            for submodel_template in environment.over_submodels_or_empty()
            if not submodel_template.id.endswith("drop-ins")
        )

        blocks.append(f"Number of submodel templates: {number_of_submodel_templates}")

        drop_ins = next(
            submodel_template
            for submodel_template in environment.over_submodels_or_empty()
            if submodel_template.id.endswith("drop-ins")
        )
        number_of_drop_ins = sum(1 for _ in drop_ins.over_submodel_elements_or_empty())
        blocks.append(f"Number of drop-ins: {number_of_drop_ins}")

        histo_drop_in_class = collections.defaultdict(
            lambda: 0
        )  # type: MutableMapping[str, int]
        for element in drop_ins.over_submodel_elements_or_empty():
            histo_drop_in_class[element.__class__.__name__] += 1

        blocks.append(
            "\n".join(
                ["## Histogram over drop-in classes"]
                + [
                    f"{cls_name}: {histo_drop_in_class[cls_name]}"
                    for cls_name in sorted(histo_drop_in_class.keys())
                ]
            )
        )

        domain_rules_in_declared_type_matched = 0
        total_domain_rules_in_declared_types = 0
        for declared_type in schema.declared_types:
            for domain_rule in declared_type.parsed.domain_rules:
                total_domain_rules_in_declared_types += 1

                for match_method in DOMAIN_RULE_MATCH_METHODS:
                    match = match_method(domain_rule.expr)
                    if match is not None:
                        domain_rules_in_declared_type_matched += 1
                        break

        blocks.append(
            f"Total number of domain rules "
            f"in declared types: {total_domain_rules_in_declared_types}, "
            f"out of which we matched {domain_rules_in_declared_type_matched}"
        )

        total_domain_rules_in_entities = 0
        domain_rules_in_entities_matched = 0
        for entity in schema.entities:
            for domain_rule in entity.parsed.domain_rules:
                total_domain_rules_in_entities += 1

                for match_method in DOMAIN_RULE_MATCH_METHODS:
                    match = match_method(domain_rule.expr)
                    if match is not None:
                        domain_rules_in_entities_matched += 1
                        break

        blocks.append(
            f"Total number of domain rules "
            f"in entities: {total_domain_rules_in_entities}, "
            f"out of which we matched {domain_rules_in_entities_matched}"
        )

        blocks.append(
            "\n".join(
                ["## IDs of Submodel Templates"]
                + [
                    submodel.id
                    for submodel in environment.over_submodels_or_empty()
                    if not submodel.id.endswith("drop-ins")
                ]
            )
        )

        stats_path = stats_dir / f"{schema_path.stem}.report.md"
        stats_path.write_text("\n\n".join(blocks), encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
