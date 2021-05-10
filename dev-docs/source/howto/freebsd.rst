.. highlight:: console

FreeBSD Installation Instructions
=================================

Installing the DSO API under FreeBSD should be largely similar to
installing it under Linux or MacOS. However, some extra work will be
required to build packages that rely on code written in other languages
and for which the package authors did not provide FreeBSD specific
wheels.

Maturin
-------

The ``Maturin`` package strips all symbols from the binaries that the Rust compiler produces.
For some reason this confuses the LLVM linker. The easiest solution is to install GCC9 and
use its linker during ``maturin`` build process::

    sudo pkg install gcc9
    CARGO_BUILD_RUSTFLAGS='-C linker=/usr/local/bin/gcc9' pip install maturin

Orjson
------

The ``orjson`` package requires - depending on its version - a different nightly build of the Rust compiler.
At the time of writing, the version of ``orjson`` used, version 3.4.6,
requires the rust nightly compiler from 2021-01-02. Hence before attempting to run::

    pip install orjson==3.4.6

or::

    make -C src install

one needs to install that specific nightly version of the rust compiler by::

    curl https://sh.rustup.rs -sSf \| sh -s -- --default-toolchain nightly-2021-01-02 --profile minimal -y
