.PHONY: install
install: 								## Perform all install steps.
	if ! command -v uv >/dev/null 2>&1; \
	then echo "uv not found, installing..." \
	&& curl -LsSf https://astral.sh/uv/install.sh | sh; \
	fi
	uv sync
	uv run pre-commit install

##
## Package management:
##

.PHONY: upgrade
upgrade:                               ## Upgrade the dependencies.
	uv sync --upgrade

##
## Development tools:
##

format:                                ## Fix code-formatting of all files.
	uv run ruff check --fix-only .
#	pre-commit run -a

lint:                                  ## Report linting errors for all files
	uv run ruff check .

type:								   ## Show typing errors for all files
	uv run ty check
##
