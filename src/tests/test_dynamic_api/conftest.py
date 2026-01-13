from datetime import UTC, date, datetime

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
        registratiedatum=datetime(2006, 6, 12, 5, 40, 12, tzinfo=UTC),
        begin_geldigheid=date(2006, 6, 1),
        eind_geldigheid=date(2015, 1, 1),
        naam="Zuidoost",
        opgemaakte_naam="Zuidoost",
    )

    stadsdeel_v2 = Stadsdeel.objects.create(
        id="03630000000016.2",
        identificatie="03630000000016",
        volgnummer=2,
        registratiedatum=datetime(2015, 1, 1, 5, 40, 12, tzinfo=UTC),
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
        registratiedatum=datetime(2015, 1, 1, 5, 40, 12, tzinfo=UTC),
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


@pytest.fixture()
def stadsdelen_ar(gebieden_ar_models):
    """
    Create Stadsdeel Zuidoost.
    """
    Stadsdeel = gebieden_ar_models["stadsdelen"]
    stadsdeel = Stadsdeel.objects.create(
        id="03630000000016.1",
        identificatie="03630000000016",
        volgnummer=1,
        begin_geldigheid=date(2006, 6, 1),
        eind_geldigheid=date(2015, 1, 1),
        naam="Zuidoost",
    )

    stadsdeel_v2 = Stadsdeel.objects.create(
        id="03630000000016.2",
        identificatie="03630000000016",
        volgnummer=2,
        begin_geldigheid=date(2015, 1, 1),
        eind_geldigheid=None,
        naam="Zuidoost",
    )
    return [stadsdeel, stadsdeel_v2]


@pytest.fixture()
def wijk_ar(gebieden_ar_models, stadsdelen_ar):
    Wijk = gebieden_ar_models["wijken"]
    return Wijk.objects.create(
        id="03630012052022.1",
        identificatie="03630012052022",
        volgnummer=1,
        begin_geldigheid=date(2015, 1, 1),
        naam="Sloterdijk",
        ligt_in_stadsdeel=stadsdelen_ar[1],
    )


@pytest.fixture()
def buurt_ar(gebieden_ar_models, stadsdelen_ar, wijk_ar):
    Buurt = gebieden_ar_models["buurten"]
    return Buurt.objects.create(
        id="03630000000078.1",
        identificatie="03630000000078",
        volgnummer=1,
        begin_geldigheid=date(2014, 2, 20),
        naam="Kop Zeedijk",
        ligt_in_wijk=wijk_ar,
        ligt_in_stadsdeel=stadsdelen_ar[1],
    )


@pytest.fixture()
def stadsdelen_subresources(gebieden_subresources_models):
    """
    Stadsdelen met subresources.
    """
    Stadsdeel = gebieden_subresources_models["stadsdelen"]
    zuidoost = Stadsdeel.objects.create(
        id="03630000000016.1",
        identificatie="03630000000016",
        volgnummer=1,
        begin_geldigheid=date(2006, 6, 1),
        eind_geldigheid=date(2015, 1, 1),
        naam="Zuidoost",
    )

    centrum = Stadsdeel.objects.create(
        id="03630000000017.1",
        identificatie="03630000000017",
        volgnummer=1,
        begin_geldigheid=date(2015, 1, 1),
        eind_geldigheid=None,
        naam="Centrum",
    )
    return {"zuidoost": zuidoost, "centrum": centrum}


@pytest.fixture()
def wijken_subresources(gebieden_subresources_models, stadsdelen_subresources):
    """
    Wijken met subresources, zelf subresource van de stadsdelen.
    """
    Wijk = gebieden_subresources_models["wijken"]
    bullewijk = Wijk.objects.create(
        id="03630012052022.1",
        identificatie="03630012052022",
        volgnummer=1,
        begin_geldigheid=date(2015, 1, 1),
        naam="Bullewijk",
        ligt_in_stadsdeel=stadsdelen_subresources["zuidoost"],
    )
    venserpolder = Wijk.objects.create(
        id="03630012052023.1",
        identificatie="03630012052023",
        volgnummer=1,
        begin_geldigheid=date(2015, 1, 1),
        naam="Venserpolder",
        ligt_in_stadsdeel=stadsdelen_subresources["zuidoost"],
    )
    haarlemmerbuurt = Wijk.objects.create(
        id="03630012052024.1",
        identificatie="03630012052024",
        volgnummer=1,
        begin_geldigheid=date(2015, 1, 1),
        naam="Haarlemmerbuurt",
        ligt_in_stadsdeel=stadsdelen_subresources["centrum"],
    )
    jordaan = Wijk.objects.create(
        id="03630012052025.1",
        identificatie="03630012052025",
        volgnummer=1,
        begin_geldigheid=date(2015, 1, 1),
        naam="Jordaan",
        ligt_in_stadsdeel=stadsdelen_subresources["centrum"],
    )

    return {
        "bullewijk": bullewijk,
        "venserpolder": venserpolder,
        "haarlemmerbuurt": haarlemmerbuurt,
        "jordaan": jordaan,
    }


@pytest.fixture()
def buurten_subresources(gebieden_subresources_models, wijken_subresources):
    """
    Buurten, subresource van wijken.
    """
    Buurt = gebieden_subresources_models["buurten"]
    marnixbuurt = Buurt.objects.create(
        id="03630000000078.1",
        identificatie="03630000000078",
        volgnummer=1,
        begin_geldigheid=date(2014, 2, 20),
        naam="Marnixbuurt",
        ligt_in_wijk=wijken_subresources["jordaan"],
    )
    zaagpoortbuurt = Buurt.objects.create(
        id="03630000000079.1",
        identificatie="03630000000079",
        volgnummer=1,
        begin_geldigheid=date(2014, 2, 20),
        naam="Zaagpoortbuurt",
        ligt_in_wijk=wijken_subresources["jordaan"],
    )
    westerdokseiland = Buurt.objects.create(
        id="03630000000080.1",
        identificatie="03630000000080",
        volgnummer=1,
        begin_geldigheid=date(2014, 2, 20),
        naam="Westerdokseiland",
        ligt_in_wijk=wijken_subresources["haarlemmerbuurt"],
    )
    westelijke_eilanden = Buurt.objects.create(
        id="03630000000081.1",
        identificatie="03630000000081",
        volgnummer=1,
        begin_geldigheid=date(2014, 2, 20),
        naam="Westelijke eilanden",
        ligt_in_wijk=wijken_subresources["haarlemmerbuurt"],
    )
    amc = Buurt.objects.create(
        id="03630000000082.1",
        identificatie="03630000000082",
        volgnummer=1,
        begin_geldigheid=date(2014, 2, 20),
        naam="AMC",
        ligt_in_wijk=wijken_subresources["bullewijk"],
    )
    hoge_dijk = Buurt.objects.create(
        id="03630000000083.1",
        identificatie="03630000000083",
        volgnummer=1,
        begin_geldigheid=date(2014, 2, 20),
        naam="Hoge Dijk",
        ligt_in_wijk=wijken_subresources["bullewijk"],
    )
    venserpolder_west = Buurt.objects.create(
        id="03630000000084.1",
        identificatie="03630000000084",
        volgnummer=1,
        begin_geldigheid=date(2014, 2, 20),
        naam="Venserpolder-West",
        ligt_in_wijk=wijken_subresources["venserpolder"],
    )
    venserpolder_oost = Buurt.objects.create(
        id="03630000000085.1",
        identificatie="03630000000085",
        volgnummer=1,
        begin_geldigheid=date(2014, 2, 20),
        naam="Venserpolder-Oost",
        ligt_in_wijk=wijken_subresources["venserpolder"],
    )

    return {
        "marnixbuurt": marnixbuurt,
        "zaagpoortbuurt": zaagpoortbuurt,
        "westerdokseiland": westerdokseiland,
        "westelijke_eilanden": westelijke_eilanden,
        "amc": amc,
        "hoge_dijk": hoge_dijk,
        "venserpolder_oost": venserpolder_oost,
        "venserpolder_west": venserpolder_west,
    }
