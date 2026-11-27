.PHONY: help
help:
	@grep -F -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | perl -pe 's/^(\w+):(.+?)##/"  $$1:" . " " x (20 - length($$1))/e' | perl -pe 's/^## ?//'

## Makefile to perform all tasks for development.
##
## Install commands:
##

.PHONY: install
install:                               ## Perform all install steps
	uv sync
	uv run pre-commit install

.PHONY: sync
sync:                                  ## Install packages, remove unmentioned packages
	uv sync

##
## Package management:
##

.PHONY: requirements
requirements:                          ## Update the uv lockfile.
	uv lock

.PHONY: upgrade
upgrade:                               ## Tool to upgrade the backend dependencies.
	uv sync --upgrade

##
## Testing:
##

.PHONY: test
test:                                  ## Run the test-suite.
	uv run pytest --reuse-db --nomigrations -vs

.PHONY: retest
retest:                                ## Run the failed tests again.
	uv run pytest --reuse-db --nomigrations -vvs --lf

.PHONY: coverage
coverage:
	uv run pytest --reuse-db --nomigrations --cov --cov-report=term-missing

##
## Development tools:
##

format:                                ## Fix code-formatting of all files.
	uv run ruff check --fix-only .
	uv run ruff format .
#	pre-commit run -a

lint:                                  ## Report linting errors for all files
	uv run ruff check .
	uv run ruff format --check .

##
