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
	mkdir -p source/datasets source/wfs-datasets
	python3 source/datasets.py

# Ensure the folder exists
source/datasets:
	mkdir -p source/datasets source/wfs-datasets
	python3 source/datasets.py

clean:
	rm -rf build/
	rm -rf source/datasets source/wfs-datasets

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile source/datasets
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
