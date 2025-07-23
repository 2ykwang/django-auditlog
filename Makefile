.PHONY: install-base-requirements install-test-requirements install-docs-requirements install-requirements test lint docs

install-base-requirements: ## install package requirements
	pip install .

install-test-requirements: ## install requirements for testing
	pip install .[tests]

install-docs-requirements: ## install requirements for docs
	pip install --editable .[docs]

install-requirements: install-base-requirements install-test-requirements install-docs-requirements

test:
	tox

lint:
	pre-commit run --all-files

docs:
	$(MAKE) -C docs html
