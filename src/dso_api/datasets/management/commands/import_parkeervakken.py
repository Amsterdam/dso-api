from django.db import connections
from environ import Env
from amsterdam_schema.utils import schema_def_from_file

from dso_api.lib.schematools.models import model_factory
from .import_schemas import Command as BaseCommand


class Command(BaseCommand):
    help = "Import all known Amsterdam schema files."
    requires_system_checks = False

    def add_arguments(self, parser):
        parser.add_argument(
            '--createdb',
            action='store_true',
            dest='createdb',
            default=False,
            help='Create tables in Default database',
        )
        parser.add_argument('filename', type=str)
        parser.add_argument('parkeervakken_connection', type=str)

    def handle(self, *args, **options):
        result = schema_def_from_file(options['filename'])

        dataset = self.import_schema('parkeervakken', result['parkeervakken'])
        tables = {table.id: table for table in dataset.schema.tables}
        Parkeervaak = model_factory(tables['parkeervakken'])

        parkeervakken_db_connection = connections.databases['default'].copy()
        parkeervakken_db_connection.update(Env.db_url_config(
            options['parkeervakken_connection']))
        parkeervakken_db_connection['ENGINE'] = (
            'django.contrib.gis.db.backends.postgis'
        )

        connections.databases['parkeervakken'] = parkeervakken_db_connection

        # Creating DB tables.
        if options['createdb']:
            with connections['default'].schema_editor() as schema_editor:
                schema_editor.create_model(Parkeervaak)
                print("Created models")

        # Seed test data
        # seed_test_data(connections['parkeervakken'])

        # Fill in data
        parkeervakken_cursor = connections['parkeervakken'].cursor()

        parkeervakken_cursor.execute(
            "SELECT * FROM parkeervakken"
        )
        for row in dictfetchall(parkeervakken_cursor):
            parkeervaak, created = Parkeervaak.objects.get_or_create(
                    parkeer_id=row['parkeer_id'])

            # TODO: improveme
            parkeervaak.buurtcode = row['buurtcode']
            parkeervaak.straatnaam = row['straatnaam']
            parkeervaak.soort = row['soort']
            parkeervaak.type = row['type']
            parkeervaak.aantal = row['aantal']
            parkeervaak.geom = row['geom']
            parkeervaak.e_type = row['e_type']
            parkeervaak.regimes = create_regimes(row=row)
            parkeervaak.save()


def seed_test_data(conn):
    import csv
    cursor = conn.cursor()

    with open('./Amsterdam_parkeerhaven_CENTROIDE_20161228.csv') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            if row['TVM_BEGIND']:
                row['TVM_BEGIND'] = "'{}'".format(row['TVM_BEGIND'])
            else:
                row['TVM_BEGIND'] = "null"

            if row['TVM_EINDD']:
                row['TVM_EINDD'] = "'{}'".format(row['TVM_EINDD'])
            else:
                row['TVM_EINDD'] = "null"

            for day in ['ma_vr', 'ma_za', 'ma', 'di', 'wo', 'do', 'vr', 'za', 'zo']:
                if row[day.upper()] == '?':
                    row[day.upper()] = False

            sql = "INSERT INTO parkeervakken ( " \
                " parkeer_id," \
                " buurtcode ," \
                " straatnaam," \
                " soort     ," \
                " type      ," \
                " aantal    ," \
                " kenteken  ," \
                " e_type    ," \
                " bord      ," \
                " begintijd1," \
                " eindtijd1 ," \
                " ma_vr     ," \
                " ma_za     ," \
                " zo        ," \
                " ma        ," \
                " di        ," \
                " wo        ," \
                " \"do\"        ," \
                " vr        ," \
                " za        ," \
                " eindtijd2 ," \
                " begintijd2," \
                " opmerking ," \
                " tvm_begind," \
                " tvm_eindd ," \
                " tvm_begint," \
                " tvm_eindt ," \
                " tvm_opmerk" \
                ") VALUES (" \
                " '{PARKEER_ID}'," \
                " '{BUURTCODE}'," \
                " '{STRAATNAAM}'," \
                " '{SOORT}'," \
                " '{TYPE}'," \
                " '{AANTAL}'," \
                " '{KENTEKEN}'," \
                " '{E_TYPE}'," \
                " '{BORD}'," \
                " '{BEGINTIJD1}'," \
                " '{EINDTIJD1}'," \
                " {MA_VR}," \
                " {MA_ZA}," \
                " {ZO}," \
                " {MA}," \
                " {DI}," \
                " {WO}," \
                " {DO}," \
                " {VR}," \
                " {ZA}," \
                " '{BEGINTIJD2}'," \
                " '{EINDTIJD2}'," \
                " '{OPMERKING}'," \
                " {TVM_BEGIND}," \
                " {TVM_EINDD}," \
                " '{TVM_BEGINT}'," \
                " '{TVM_EINDT}'," \
                " '{TVM_OPMERK}')".format(**row)
            cursor.execute(sql)


def create_regimes(row):
    if not any([
            row['kenteken'],
            row['bord'],
            row['e_type'],
            row['begintijd1'],
            row['eindtijd1'],
            row['begintijd2'],
            row['eindtijd2'],
            row['tvm_begind'],
            row['tvm_eindd'],
            row['tvm_begint'],
            row['tvm_eindt'],
            row['tvm_opmerk']
    ]):
        return

    days = days_from_row(row)

    base_data = dict(
        soort=row['soort'],
        eType=row['e_type'],
        bord=row['bord'],
        beginTijd=row['begintijd1'] if row['begintijd1'] else '00:00',
        eindTijd=row['eindtijd1'] if row['eindtijd1'] else '23:59',
        opmerking=row['opmerking'],
        dagen=days,
    )

    regimes = []

    if row.get('kenteken'):
        kenteken_regime = base_data.copy()
        kenteken_regime.update(dict(
            kenteken=row['kenteken'],
        ))
        regimes.append(kenteken_regime)
    elif row.get('begintijd2'):
        regimes.append(base_data)

        second_mode = base_data.copy()
        second_mode.update(dict(
            begin_tijd=row['begintijd2'],
            eind_tijd=row['eindtijd2']
        ))
        regimes.append(second_mode)
    elif any([
            row['tvm_begind'],
            row['tvm_eindd'],
            row['tvm_begint'],
            row['tvm_eindt'],
            row['tvm_opmerk']
    ]):
        # TVM
        tvm_mode = base_data.copy()
        tvm_mode.update(dict(
            beginDatum=row['tvm_begind'],
            eindDatum=row['tvm_eindd'],
            beginTijd=row['tvm_begint'],
            eindTijd=row['tvm_eindt'],
            opmerking=row['tvm_opmerk']
        ))

    return regimes


def days_from_row(row):
    week_days = ['ma', 'di', 'wo', 'do', 'vr', 'za', 'zo']

    if row['ma_vr']:
        # Monday to Friday
        days = week_days[:4]
    elif row['ma_za']:
        # Monday to Saturday
        days = week_days[:5]
    elif all([v for day, v in row.items() if day in week_days]):
        # All days apply
        days = week_days

    elif not any([v for day, v in row.items() if day in week_days]):
        # All days apply
        days = week_days
    else:
        # One day permit
        days = [key for key, v in row.items() if key in week_days and v]

    return days


def dictfetchall(cursor):
    "Return all rows from a cursor as a dict"
    columns = [col[0] for col in cursor.description]
    return [
        dict(zip(columns, row))
        for row in cursor.fetchall()
    ]
