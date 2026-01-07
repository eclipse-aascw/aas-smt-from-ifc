****************
aas-smt-from-ifc
****************
Convert IFC data structures to AAS Submodel Templates.

.. image:: https://github.com/aas-core-works/aas-smt-from-ifc/actions/workflows/ci.yml/badge.svg
    :target: https://github.com/aas-core-works/aas-smt-from-ifc/actions/workflows/ci.yml
    :alt: Continuous integration

Installation
============
Check out the repository and change to its directory.

Create a virtual environment:

.. code-block::

    python -m venv venv

Activate it (on Windows):

.. code-block::

    venv/Scripts/activate

... or on Unix:

.. code-block::

    source venv/bin/activate

Install the dependencies:

.. code-block::

    pip3 install .

You can now run ``aas-smt-from-ifc`` (see the next section, "--help").

``--help``
==========

.. Help starts: aas-smt-from-ifc --help
.. code-block::

    usage: aas-smt-from-ifc [-h] [--version] --target
                            {SUBMODEL_TEMPLATES,TO_AAS_CODE} --schema_path
                            SCHEMA_PATH --base_namespace BASE_NAMESPACE
                            --output_path OUTPUT_PATH

    Convert IFC data structures to AAS Submodel Templates.

    options:
      -h, --help            show this help message and exit
      --version             show the current version and exit
      --target {SUBMODEL_TEMPLATES,TO_AAS_CODE}
                            Artefact to be generated
      --schema_path SCHEMA_PATH
                            Path to the input Express schema
      --base_namespace BASE_NAMESPACE
                            IRI to the namespace used as root, *e.g.*,
                            'https://aas-smt-from-ifc.aas-core-works.org'
      --output_path OUTPUT_PATH
                            Path where to write the generated artefact

.. Help ends: aas-smt-from-ifc --help

Experiments
===========

The experiments live in `experiments/`_ directory.

.. _experiments/: https://github.com/aas-core-works/aas-smt-from-ifc/tree/main/experiments

Assuming you are still in the virtual environment and at the root of the repository, install the experiment dependencies by:

.. code-block::

    pip3 install -r experiments/requirements.txt

Then you can run the individual experiments directly.
For example:

.. codeb-block::

    python experiments/templates/quantify_number_of_submodels.py
