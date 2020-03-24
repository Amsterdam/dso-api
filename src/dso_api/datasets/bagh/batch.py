import logging
import os

from django.db.models import Count

from dso_api import settings
from dso_api.batch import batch, csv, geo
from dso_api.batch.objectstore import download_file
from dso_api.datasets.models import Dataset

GOB_CSV_ENCODING = "utf-8-sig"
GOB_SHAPE_ENCODING = "utf-8"

log = logging.getLogger(__name__)


class ImportGemeenteTask(batch.BasicTask):
    """
    Gemeente is not delivered by GOB. So we hardcode gemeente Amsterdam data
    """

    name = "Import gemeente code / naam"
    data = [
        (
            "03630000000000",
            1,
            "0363",
            "1900-01-01 00:00:00.00000+00",
            "1900-01-01",
            "",
            "Amsterdam",
            "J",
        )
    ]

    def __init__(self, path, models):
        self.path = path
        self.model = models["gemeente"]

    def before(self):
        self.model.objects.all().delete()

    def after(self):
        pass

    def process(self):

        gemeentes = [
            self.model(
                id=f"{r[0]}_{r[1]:03}",
                identificatie=r[0],
                volgnummer=r[1],
                code=r[2],
                registratiedatum=r[3],
                begin_geldigheid=r[4],
                eind_geldigheid=r[5] or None,
                naam=r[6],
                verzorgingsgebied=r[7] == "J",
            )
            for r in self.data
        ]
        self.model.objects.bulk_create(gemeentes, batch_size=100)


class ImportWoonplaatsTask(batch.BasicTask):
    name = "Import woonplaats"

    def __init__(self, path, models):
        self.path = path
        self.models = models
        self.model = models["woonplaats"]
        self.filename = "BAG_woonplaats_ActueelEnHistorie.csv"
        self.source_path = "bag/CSV_ActueelEnHistorie"
        self.gemeentes = set()

    def before(self):
        self.model.objects.all().delete()
        download_file(os.path.join(self.source_path, self.filename))
        self.gemeentes = set(
            self.models["gemeente"]
            .objects.filter(eind_geldigheid__isnull=True)
            .order_by("code")
            .distinct("code")
            .values_list("code", flat=True)
        )

    def after(self):
        multiple_endranges = (
            self.model.objects.values("identificatie")
            .filter(eind_geldigheid__isnull=True)
            .annotate(cnt=Count("identificatie"))
            .filter(cnt__gt=1)
        )

        if len(multiple_endranges) > 0:
            log.error(f"Multiple undefined eind_geldigheid for: {multiple_endranges}")

        # TODO : Check overlapping time periods for each identificatie

        self.gemeentes.clear()

    def process(self):
        source = os.path.join(self.path, self.filename)
        woonplaatsen = csv.process_csv(
            None, None, self.process_row, source=source, encoding=GOB_CSV_ENCODING
        )

        self.model.objects.bulk_create(woonplaatsen, batch_size=batch.BATCH_SIZE)

    def process_row(self, r):
        identificatie = r["identificatie"]
        volgnummer = int(r["volgnummer"])
        id = f"{identificatie}_{volgnummer:03}"
        wkt_geometrie = r["geometrie"]
        if wkt_geometrie:
            geometrie = geo.get_multipoly(wkt_geometrie)
            if not geometrie:
                log.error(f"Woonplaats {id} has no valid geometry; skipping")
                return None
        else:
            log.warning(f"OpenbareRuimte {id} has no geometry")
            geometrie = None

        gemeente_id = r["ligtIn:BRK.GME.identificatie"] or None
        if gemeente_id and gemeente_id not in self.gemeentes:
            log.error(
                f"Woonplaats {id} has invalid gemeente_id {gemeente_id}; skipping"
            )
            return None
        begin_geldigheid = csv.iso_datum_tijd(r["beginGeldigheid"])
        eind_geldigheid = csv.iso_datum_tijd(r["eindGeldigheid"]) or None
        if not csv.datum_geldig(begin_geldigheid, eind_geldigheid):
            log.error(
                f"Woonplaats {id} has invalid geldigheid {begin_geldigheid}-{eind_geldigheid}; skipping"  # noqa: E501
            )
            return None

        values = {
            "id": id,
            "identificatie": r["identificatie"],
            "volgnummer": r["volgnummer"],
            "registratiedatum": csv.iso_datum_tijd(r["registratiedatum"]),
            "begin_geldigheid": csv.iso_datum_tijd(r["beginGeldigheid"]),
            "eind_geldigheid": csv.iso_datum_tijd(r["eindGeldigheid"]),
            "aanduiding_in_onderzoek": csv.get_janee_boolean(
                r["aanduidingInOnderzoek"]
            ),
            "geconstateerd": csv.get_janee_boolean(r["geconstateerd"]),
            "naam": r["naam"],
            "document_datum": csv.iso_datum(r["documentdatum"]),
            "document_nummer": r["documentnummer"],
            "status": r["status"],
            "geometrie": geometrie,
            "gemeente_identificatie": gemeente_id,
        }
        return self.model(**values)


class ImportBagHJob(batch.BasicJob):
    name = "Import BAGH"

    def __init__(self, **kwargs):
        data_dir = settings.DATA_DIR
        if not os.path.exists(data_dir):
            raise ValueError("DATA_DIR not found: {}".format(data_dir))

        self.data_dir = data_dir
        # For utf-8 files SHAPE_ENCODING needs to be set.
        # noqa: E501 See : https://gis.stackexchange.com/questions/195862/preserving-special-chars-using-osgeo-ogr-driver-to-shapefile-in-python
        os.environ["SHAPE_ENCODING"] = "utf-8"

        dataset = Dataset.objects.get(name="bagh")
        self.models = {
            model._meta.model_name: model for model in dataset.create_models()
        }

    def __del__(self):
        # TODO : shapefiles for BRK are not yet in utf-8.
        #        If every shapefile is utf-8 SHAPE_ENCODING variable can be set globally
        os.environ.pop("SHAPE_ENCODING")

    def tasks(self):
        return [
            # no-dependencies.
            ImportGemeenteTask(self.data_dir, self.models),
            ImportWoonplaatsTask(self.data_dir, self.models),
            # ImportStadsdeelTask(self.gob_gebieden_path),
            # ImportWijkTask(self.gob_gebieden_shp_path),
            #
            # # stadsdelen.
            # ImportGebiedsgerichtwerkenTask(self.gob_gebieden_shp_path),
            # ImportGebiedsgerichtwerkenPraktijkgebiedenTask(self.gob_gebieden_shp_path),
            # ImportGrootstedelijkgebiedTask(self.gob_gebieden_shp_path),
            # ImportUnescoTask(self.gob_gebieden_shp_path),
            # ImportBuurtTask(self.gob_gebieden_path),
            # ImportBouwblokTask(self.gob_gebieden_path),
            # #
            # ImportOpenbareRuimteTask(self.gob_bag_path),
            # #
            # ImportLigplaatsTask(self.gob_bag_path),
            # ImportStandplaatsenTask(self.gob_bag_path),
            # ImportPandTask(self.gob_bag_path),
            # # large. 500.000
            # ImportVerblijfsobjectTask(self.gob_bag_path),
            # #
            # # large. 500.000
            # ImportNummeraanduidingTask(self.gob_bag_path),
            # #
            # # some sql copying fields
            # DenormalizeDataTask(),
            # #
            # # more denormalizing sql
            # UpdateGebiedenAttributenTask(),
            # UpdateGrootstedelijkAttri
        ]
