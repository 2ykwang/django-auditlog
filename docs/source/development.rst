Development setup
=================

This document describes how to configure a local development environment for
``django-auditlog``. The commands below assume a Unix-like shell.

Prepare a virtual environment
-----------------------------

.. code-block:: bash

   python -m venv venv
   source venv/bin/activate
   pip install -U pip
   pip install -e .[tests,docs]
   # or use the provided Makefile
   make install-requirements

Install pre-commit hooks
------------------------

.. code-block:: bash

   pre-commit install

Running the test suite
----------------------

The project uses ``tox`` to run tests across multiple environments.
Execute the following command to run all tests:

.. code-block:: bash

   tox

Building the documentation
--------------------------

To build the HTML documentation locally:

.. code-block:: bash

   make docs
