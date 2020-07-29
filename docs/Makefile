# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = source
BUILDDIR      = build

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile

datasets:
	rm -rf source/datasets
	mkdir -p source/datasets
	python3 source/datasets.py

datasets-docker:
	rm -rf /docs/source/datasets
	mkdir -p /docs/source/datasets
	python3 /docs/source/datasets.py
	@$(SPHINXBUILD) -M html "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(0)
	mkdir -p /usr/share/nginx/html/v1/docs/
	cp -rf /docs/build/html/* /usr/share/nginx/html/v1/docs/

# Ensure the folder exists
source/datasets:
	mkdir -p source/datasets
	python3 source/datasets.py

clean:
	rm -rf build/
	rm -rf source/datasets

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile source/datasets
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
