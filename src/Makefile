.PHONY: help
help:
	@grep -F -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | perl -pe 's/^(\w+):(.+?)##/"  $$1:" . " " x (20 - length($$1))/e' | perl -pe 's/^## ?//'

## Makefile to perform all tasks for development.
##
## Install commands:
##

.PHONY: install
install:                               ## Perform all install steps
	pip --require-virtualenv install -r requirements_dev.txt
	pre-commit install

.PHONY: sync
sync:                                  ## Install packages, remove unmentioned packages
	pip-sync requirements.txt requirements_dev.txt

##
## Package management:
##

.PHONY: requirements
requirements: requirements.in requirements_dev.in  ## Re-generate the requirements/base.txt file for pip.
	pip-compile -v --generate-hashes --resolver=legacy --output-file requirements.txt requirements.in
	pip-compile -v --generate-hashes --resolver=legacy --output-file requirements_dev.txt requirements_dev.in

.PHONY: upgrade
upgrade:                               ## Tool to upgrade the backend dependencies.
	pur --patch=Django -r requirements.in
	pur --no-recursive -r requirements_dev.in
	pip-compile -v --generate-hashes --upgrade --output-file requirements.txt requirements.in
	pip-compile -v --generate-hashes --upgrade --output-file requirements_dev.txt requirements_dev.in

##
## Testing:
##

.PHONY: test
test:                                  ## Run the test-suite.
	pytest --reuse-db --nomigrations -vs .

.PHONY: test
retest:                                ## Run the failed tests again.
	pytest --reuse-db --nomigrations -vvs --lf .

.PHONY: coverage
coverage:
	py.test --reuse-db --nomigrations --cov --cov-report=term-missing

##
## Development tools:
##

.PHONY: flake8
flake8:                                ## Report linting errors
	flake8 .

##
