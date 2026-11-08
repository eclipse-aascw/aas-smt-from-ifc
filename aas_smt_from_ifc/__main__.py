# SPDX-FileCopyrightText: 2025 aas-smt-from-ifc AUTHORS
#
# SPDX-License-Identifier: MIT

"""Run aas-smt-from-fic as Python module."""

import aas_smt_from_ifc.main

if __name__ == "__main__":
    # The ``prog`` needs to be set in the argparse.
    # Otherwise, the program name in the help shown to the user will be ``__main__``.
    aas_smt_from_ifc.main.main(prog="aas_smt_from_ifc")
