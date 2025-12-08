from datetime import date, datetime, timezone

import pytest


@pytest.fixture()
def stadsdelen(gebieden_models):
    """
    Create Stadsdeel Zuidoost.
    """
    Stadsdeel = gebieden_models["stadsdelen"]
    stadsdeel = Stadsdeel.objects.create(
        id="03630000000016.1",
        identificatie="03630000000016",
        volgnummer=1,
        registratiedatum=datetime(2006, 6, 12, 5, 40, 12, tzinfo=timezone.utc),
        begin_geldigheid=date(2006, 6, 1),
        eind_geldigheid=date(2015, 1, 1),
        naam="Zuidoost",
        opgemaakte_naam="Zuidoost",
    )

    stadsdeel_v2 = Stadsdeel.objects.create(
        id="03630000000016.2",
        identificatie="03630000000016",
        volgnummer=2,
        registratiedatum=datetime(2015, 1, 1, 5, 40, 12, tzinfo=timezone.utc),
        begin_geldigheid=date(2015, 1, 1),
        eind_geldigheid=None,
        naam="Zuidoost",
        opgemaakte_naam="Zuidoost",
    )
    return [stadsdeel, stadsdeel_v2]


@pytest.fixture()
def gebied(gebieden_models, stadsdelen, buurt):
    """
    Creates gebied that is connected to Stadsdeel Zuidoost.
    """
    Gebied = gebieden_models["ggwgebieden"]
    gebied = Gebied.objects.create(
        id="03630950000019.1",
        identificatie="03630950000019",
        volgnummer=1,
        registratiedatum=datetime(2015, 1, 1, 5, 40, 12, tzinfo=timezone.utc),
        begin_geldigheid=date(2014, 2, 20),
        naam="Bijlmer-Centrum",
    )
    Gebied.bestaat_uit_buurten.through.objects.create(
        id="11", ggwgebieden_id="03630950000019.1", bestaat_uit_buurten_id="03630000000078.1"
    )
    return gebied


@pytest.fixture()
def buurt(gebieden_models, stadsdelen, wijk):
    Buurt = gebieden_models["buurten"]
    return Buurt.objects.create(
        id="03630000000078.1",
        identificatie="03630000000078",
        volgnummer=1,
        begin_geldigheid=date(2014, 2, 20),
        code="A00a",
        naam="Kop Zeedijk",
        ligt_in_wijk=wijk,
    )


@pytest.fixture()
def wijk(gebieden_models, stadsdelen):
    Wijk = gebieden_models["wijken"]
    return Wijk.objects.create(
        id="03630012052022.1",
        identificatie="03630012052022",
        volgnummer=1,
        begin_geldigheid=date(2015, 1, 1),
        code="H36",
        naam="Sloterdijk",
        ligt_in_stadsdeel=stadsdelen[1],
    )
