.PHONY: install
install:
	pip install -r requirements_dev.txt

.PHONY: sync
sync:
	pip-sync requirements.txt requirements_dev.txt

.PHONY: requirements
requirements: requirements.in
	pip-compile -v --output-file requirements.txt requirements.in

.PHONY: upgrade
upgrade:
	pur --patch=Django -r requirements.in
	pur --no-recursive -r requirements_dev.txt
	pip-compile -v --upgrade --output-file requirements.txt requirements.in

.PHONY: test
test:
	pytest --reuse-db --nomigrations -vs .

.PHONY: test
retest:
	pytest --reuse-db --nomigrations -vs --lf .


.PHONY: coverage
coverage:
	py.test --reuse-db --nomigrations --cov --cov-report=term-missing

.PHONY: flake8
flake8:
	flake8 .
