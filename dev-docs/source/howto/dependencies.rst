.. highlight:: console

Managing Python dependencies
============================

This project uses `uv <https://docs.astral.sh/uv/>`__ to manage dependencies in
``pyproject.toml`` and the committed ``uv.lock`` file at the repository root.
Run the following commands from the repository root.

To add a Python dependency to the project:

- Run ``uv add package-name`` (or ``uv add --dev package-name`` for development tools).
- Commit both ``pyproject.toml`` and ``uv.lock``.

After editing ``pyproject.toml`` manually, run ``make requirements`` to update the
lockfile, then ``make sync`` to install it.

To upgrade the project, run::

    make upgrade
    make install
    make test

Or in a single call: ``make upgrade install test``

``make upgrade`` updates dependencies within their declared constraints.
To upgrade a pinned dependency, update its version using
``uv add 'Django==5.2.19'`` with the desired version. Review Django upgrades
carefully, especially when changing minor or major versions.

Use ``make format`` to apply Ruff lint fixes and formatting, and ``make lint``
to check both. Black is no longer used.

Run ``uv run ty check`` for type diagnostics. The ty pre-commit hook displays
warnings without failing on type diagnostics.

To build the documentation locally, install its dependency group with
``uv sync --locked --group docs`` and run
``uv run --group docs sphinx-build dev-docs/source dev-docs/build/html``.

.. note::
    Typically, code changes are required when upgrading to newer Django versions.
    For example, some feature could be deprecated by the newer Django version.
    For this reason, third-party modules also need to be upgraded and might add more
    breaking changes that need to be addressed before the Django upgrade is complete.
