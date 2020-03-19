import os
from dso_api import settings
from dso_api.batch import batch
from dso_api.datasets.models import Dataset

GOB_CSV_ENCODING = "utf-8-sig"
GOB_SHAPE_ENCODING = "utf-8"


class ImportGemeenteTask(batch.BasicTask):
    """
    Gemeente is not delivered by GOB. So we hardcode gemeente Amsterdam data
    """

    name = "Import gemeente code / naam"
    data = [
        (
            "03630000000000",
            1,
            "1900-01-01 00:00:00.00000+00",
            "1900-01-01",
            "",
            "Amsterdam",
            "J",
            "N",
        )
    ]

    def __init__(self, path, models):
        self.path = path
        self.model = models["gemeente"]

    def before(self):
        pass

    def after(self):
        pass

    def process(self):
        pass

        #     id character varying(18) COLLATE pg_catalog."default" NOT NULL,
        # identificatie character varying(14) COLLATE pg_catalog."default" NOT NULL,
        # volgnummer smallint NOT NULL,
        # registratiedatum timestamp with time zone NOT NULL,
        # begin_geldigheid date,
        # einde_geldigheid date,
        # naam character varying(40) COLLATE pg_catalog."default" NOT NULL,
        # verzorgingsgebied boolean,
        # vervallen boolean,

        gemeentes = [
            self.model(
                id=f"{r[0]}_{r[1]:03}",
                identificatie=r[0],
                volgnummer=r[1],
                registratiedatum=r[2],
                begin_geldigheid=r[3],
                einde_geldigheid=r[4] or None,
                naam=r[5],
                verzorgingsgebied=r[6] == "J",
                vervallen=r[7] == "J",
            )
            for r in self.data
        ]
        self.model.objects.bulk_create(gemeentes, batch_size=100)


class ImportBagHJob(batch.BasicJob):
    name = "Import BAGH"

    def __init__(self, **kwargs):
        data_dir = settings.DATA_DIR
        if not os.path.exists(data_dir):
            raise ValueError("GOB_DIR not found: {}".format(data_dir))

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
            # ImportWoonplaatsTask(self.gob_bag_path),
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
