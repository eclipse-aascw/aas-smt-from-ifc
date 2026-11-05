# SPDX-FileCopyrightText: 2025 aas-smt-from-ifc AUTHORS
#
# SPDX-License-Identifier: MIT

"""Provide features shared accross the tests."""

import os
import pathlib

RECORDING_VAR = "AAS_SMT_FROM_IFC_TEST_RECORD"
RECORDING = os.environ.get(RECORDING_VAR, "").lower() in (
    "on",
    "1",
    "true",
)

TEST_DATA_DIR = pathlib.Path(os.path.realpath(__file__)).parent.parent / "test_data"
