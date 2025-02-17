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

# The --generate-hashes option is disabled for the dev-file,
# because pip-tools brings in setuptools which requires --allow-unsafe.
# The --allow-unsafe option then brings in a pinned version of pip in the file.
.PHONY: requirements
requirements: requirements.in requirements_dev.in  ## Re-generate the requirements/base.txt file for pip.
	pip-compile -v --generate-hashes --output-file requirements.txt requirements.in
	pip-compile -v --output-file requirements_dev.txt requirements_dev.in
	perl -pi -e "s!$$(pwd)!.!" requirements*.txt

.PHONY: upgrade
upgrade:                               ## Tool to upgrade the backend dependencies.
	pur --patch=Django -r requirements.in
	pur --no-recursive -r requirements_dev.in
	pip-compile -v --generate-hashes --upgrade --output-file requirements.txt requirements.in
	pip-compile -v --upgrade --output-file requirements_dev.txt requirements_dev.in
	perl -pi -e "s!$$(pwd)!.!" requirements*.txt

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

format:                                ## Fix code-formatting of all files.
	black .
	ruff check --fix-only .
#	pre-commit run -a

lint:                                  ## Report linting errors for all files
	ruff check .

##
