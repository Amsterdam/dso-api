import logging
import sys

from django.core.management import BaseCommand

from dso_api.batch import batch
from dso_api.datasets.bagh.batch import ImportBagHJob

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Import data for dataset"
    requires_system_checks = False
    ordered = [
        "bagh",
    ]

    imports = dict(bagh=[ImportBagHJob])

    def add_arguments(self, parser):
        parser.add_argument(
            "dataset",
            nargs="*",
            default=self.ordered,
            help="Dataset to import, choose from {}".format(
                ", ".join(self.imports.keys())
            ),
        )

        parser.add_argument(
            "--create",
            action="store_true",
            dest="create",
            default=False,
            help="Only update dataset",
        )

    def handle(self, *args, **options):
        datasets = options["dataset"]

        for one_ds in datasets:
            if one_ds not in self.imports.keys():
                log.error(f"Unkown dataset: {one_ds}")
                sys.exit(1)

        sets = [ds for ds in self.ordered if ds in datasets]  # enforce order

        for one_ds in sets:
            for job_class in self.imports[one_ds]:
                batch.execute(job_class(create=options["create"]))
