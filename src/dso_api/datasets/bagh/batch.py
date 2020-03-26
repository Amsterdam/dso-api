import copy
import logging
import os
import sqlparse

from django.db import connection, transaction
from dso_api import settings
from dso_api.batch import batch, csv, geo
from dso_api.batch.objectstore import download_file
from dso_api.datasets.models import Dataset

GOB_SHAPE_ENCODING = "utf-8"

log = logging.getLogger(__name__)


class ImportBagHTask(batch.BasicTask):
    def __init__(self, *args, **kwargs):
        self.table = f"{self.__class__.dataset}_{self.__class__.name}"
        self.temp_table = f"{self.__class__.dataset}_temp"
        self.path = kwargs.get("path")
        self.models = kwargs["models"]
        self.model = copy.deepcopy(self.models[self.__class__.name])
        self.gob_path = kwargs.get("gob_path", "bag")
        self.gob_id = {"bag": "BAG", "gebieden": "GBD"}[self.gob_path]

        self.filename = f"{self.gob_id}_{self.__class__.name}_ActueelEnHistorie.csv"
        self.source_path = f"{self.gob_path}/CSV_ActueelEnHistorie"
        self.use_gemeentes = kwargs.get("use_gemeentes", False)
        if self.use_gemeentes:
            self.gemeentes = set()

    def get_non_pk_fields(self):
        return [x.name for x in self.model._meta.get_fields() if not x.primary_key]

    def before(self):
        cursor = connection.cursor()
        cursor.execute(f"DROP TABLE IF EXISTS {self.temp_table}")
        cursor.execute(
            f"CREATE TEMPORARY TABLE {self.temp_table} AS TABLE {self.table} WITH NO DATA"
        )
        self.model._meta.db_table = self.temp_table

        if self.path:
            download_file(os.path.join(self.source_path, self.filename))

        if self.use_gemeentes:
            self.gemeentes = set(
                self.models["gemeente"]
                .objects.filter(eind_geldigheid__isnull=True)
                .order_by("code")
                .distinct("code")
                .values_list("code", flat=True)
            )

    def after(self):
        cursor = connection.cursor()
        cursor.execute(f"ALTER TABLE {self.temp_table} ADD PRIMARY KEY(id)")
        cursor.execute(f"CREATE INDEX ON {self.temp_table}(identificatie)")

        if self.do_date_checks() > 0:
            log.error(f"Data invalid. Skip table {self.table}")
            return

        # validate_geometry(models.Stadsdeel)

        # Check rows to delete. In history database there should be no rows to delete
        cursor.execute(
            f"""
            SELECT COUNT(e.*) FROM {self.table} e
            LEFT JOIN  {self.temp_table} t ON e.id = t.id
            WHERE t.id IS NULL
            """
        )
        (count,) = cursor.fetchone()
        if count > 0:
            log.error(f"Rows deleted. Data invalid. Skip table {self.table}")
            return
        with transaction.atomic():
            cursor.execute(
                f"""
                INSERT INTO  {self.table}
                SELECT t.* FROM {self.temp_table} t
                LEFT JOIN  {self.table} e ON t.id = e.id
                WHERE e.id IS NULL
                """
            )
            log.info(f"Inserted into {self.table} : {cursor.rowcount}")
            setters = map(lambda x: f"{x} = t.{x}", self.get_non_pk_fields())
            # No
            cursor.execute(
                f"""
                UPDATE {self.table} e SET {",".join(setters)}
                FROM {self.temp_table} t
                WHERE e.id = t.id AND t IS DISTINCT FROM e
                """
            )
            log.info(f"Updated {self.table} : {cursor.rowcount}")

        cursor.execute(f"DROP TABLE {self.temp_table}")
        self.model._meta.db_table = self.table
        if self.use_gemeentes:
            self.gemeentes.clear()

    def process_row_common(self, r):
        identificatie = r["identificatie"]
        volgnummer = int(r["volgnummer"])
        id = f"{identificatie}_{volgnummer:03}"
        begin_geldigheid = csv.parse_date_time(r["beginGeldigheid"])
        eind_geldigheid = csv.parse_date_time(r["eindGeldigheid"]) or None
        if not csv.is_valid_date_range(begin_geldigheid, eind_geldigheid):
            log.error(
                f"self.name.title() {id} has invalid geldigheid {begin_geldigheid}-{eind_geldigheid}; skipping"  # noqa: E501
            )
            return None

        wkt_geometrie = r["geometrie"]
        if wkt_geometrie:
            geometrie = geo.get_multipoly(wkt_geometrie)
            if not geometrie:
                log.error(f"{self.name.title()} {id} has no valid geometry; skipping")
                return None
        else:
            log.warning(f"{self.name.title} {id} has no geometry")
            geometrie = None

        values = {
            "id": id,
            "identificatie": identificatie,
            "volgnummer": volgnummer,
            "begin_geldigheid": begin_geldigheid,
            "eind_geldigheid": eind_geldigheid,
            "geometrie": geometrie,
        }
        if self.use_gemeentes:
            gemeente_id = r["ligtIn:BRK.GME.identificatie"] or None
            if gemeente_id and gemeente_id not in self.gemeentes:
                log.error(
                    f"Woonplaats {id} has invalid gemeente_id {gemeente_id}; skipping"
                )
                return None
            else:
                values["gemeente_identificatie"] = gemeente_id
        return values

    def do_date_checks(self):
        cursor = connection.cursor()
        cursor.execute(
            f"""
        SELECT identificatie, count(*)
        FROM {self.temp_table}
        WHERE eind_geldigheid IS NULL
        GROUP BY identificatie HAVING count(*) > 1
        """
        )
        multiple_endranges = cursor.fetchall()
        if len(multiple_endranges) > 0:
            log.error(f"Multiple open eind_geldigheid for: {multiple_endranges}")
            return 1

        cursor.execute(
            f"""SELECT w1.id, w2.id FROM {self.temp_table} w1
        JOIN {self.temp_table} w2 ON w1.identificatie = w2.identificatie
        WHERE w1.volgnummer <> w2.volgnummer
        AND  w1.begin_geldigheid >= w2.begin_geldigheid
        AND  (w1.begin_geldigheid < w2.eind_geldigheid OR w2.eind_geldigheid IS NULL)
        """
        )
        overlapping_ranges = cursor.fetchall()
        if len(overlapping_ranges) > 0:
            log.error(f"Overlapping date ranges for: {overlapping_ranges}")
            return 2
        return 0


class CreateBagHTables(batch.BasicTask):
    def process(self):
        processed = 0
        with open("dso_api/datasets/bagh/bagh_create.sql", "r") as sql_file:
            with connection.cursor() as c:
                for sql in sqlparse.split(sql_file.read()):
                    if sql and not sql.isspace():
                        c.execute(sql)
                        processed += 1
        log.info(f"Processed {processed} statements")


class ImportGemeenteTask(ImportBagHTask):
    """
    Gemeente is not delivered by GOB. So we hardcode gemeente Amsterdam data
    """

    name = "gemeente"
    dataset = "bagh"
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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


class ImportWoonplaatsTask(ImportBagHTask):
    name = "woonplaats"
    dataset = "bagh"

    def process(self):
        source = os.path.join(self.path, self.filename)
        woonplaatsen = csv.process_csv(None, None, self.process_row, source=source)

        self.model.objects.bulk_create(woonplaatsen, batch_size=batch.BATCH_SIZE)

    def process_row(self, r):
        values = self.process_row_common(r)
        if values:
            values.update(
                {
                    "registratiedatum": csv.parse_date_time(r["registratiedatum"]),
                    "aanduiding_in_onderzoek": csv.parse_yesno_boolean(
                        r["aanduidingInOnderzoek"]
                    ),
                    "geconstateerd": csv.parse_yesno_boolean(r["geconstateerd"]),
                    "naam": r["naam"],
                    "documentdatum": csv.parse_date_time(r["documentdatum"]),
                    "documentnummer": r["documentnummer"],
                    "status": r["status"],
                }
            )
            return self.model(**values)
        else:
            return None


class ImportStadsdeelTask(ImportBagHTask):
    name = "stadsdeel"
    dataset = "bagh"

    def process(self):
        source = os.path.join(self.path, self.filename)
        stadsdelen = csv.process_csv(None, None, self.process_row, source=source)
        self.model.objects.bulk_create(stadsdelen, batch_size=batch.BATCH_SIZE)

    def process_row(self, r):
        values = self.process_row_common(r)
        if values:
            values.update(
                {
                    "code": r["code"],
                    "naam": r["naam"],
                    "registratiedatum": csv.parse_date_time(r["registratiedatum"]),
                    "documentdatum": csv.parse_date_time(r["documentdatum"]),
                    "documentnummer": r["documentnummer"],
                }
            )
            return self.model(**values)
        else:
            return None


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
        self.create = kwargs.get("create", False)

    def __del__(self):
        os.environ.pop("SHAPE_ENCODING")

    def tasks(self):
        tasks1 = []
        if self.create:
            tasks1.append(CreateBagHTables())

        tasks1.extend(
            [
                # no-dependencies.
                ImportGemeenteTask(models=self.models),
                ImportWoonplaatsTask(
                    path=self.data_dir, models=self.models, use_gemeentes=True
                ),
                ImportStadsdeelTask(
                    path=self.data_dir,
                    models=self.models,
                    gob_path="gebieden",
                    use_gemeentes=True,
                ),
                # ImportWijkTask(self.gob_gebieden_shp_path),
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
        )
        return tasks1
