import logging

import click

from integration_tests.testrunner import run_tests

logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.INFO)


@click.command()
@click.option("-l", "--load-test", type=bool, default=False, help="Perform a load test")
def cli(load_test: bool):
    run_tests()
