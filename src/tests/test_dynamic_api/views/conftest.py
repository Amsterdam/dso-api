import pytest
from schematools.contrib.django import models
from schematools.types import ProfileSchema


@pytest.fixture
def basic_parkeervak(parkeervakken_parkeervak_model):
    return parkeervakken_parkeervak_model.objects.create(
        id=1,
        type="Langs",
        soort="NIET FISCA",
        aantal="1.0",
    )


@pytest.fixture
def profile1_mandatory():
    """A profile that enforces a particular set of filters"""
    return models.Profile.create_for_schema(
        ProfileSchema.from_dict(
            {
                "name": "parkeerwacht-filter1",
                "id": "parkeerwacht-filter1",
                "scopes": ["PROFIEL/SCOPE"],
                "datasets": {
                    "parkeervakken": {
                        "tables": {
                            "parkeervakken": {
                                "permissions": "read",
                                "mandatoryFilterSets": [
                                    ["buurtcode", "type"],
                                    ["regimes.eindtijd"],
                                ],
                            }
                        }
                    }
                },
            }
        )
    )


@pytest.fixture
def profile2_mandatory():
    """A profile that enforces a different set of filters"""
    models.Profile.create_for_schema(
        ProfileSchema.from_dict(
            {
                "name": "parkeerwacht-filter2",
                "id": "parkeerwacht-filter2",
                "scopes": ["PROFIEL2/SCOPE"],
                "datasets": {
                    "parkeervakken": {
                        "tables": {
                            "parkeervakken": {
                                "permissions": "read",
                                "mandatoryFilterSets": [
                                    ["regimes.aantal[gte]"],
                                ],
                            }
                        }
                    }
                },
            }
        )
    )


@pytest.fixture
def profile_limited_soort():
    """A profile that only exposes a field in limited way."""
    models.Profile.create_for_schema(
        ProfileSchema.from_dict(
            {
                "name": "parkeerwacht-limited1",
                "id": "parkeerwacht-limited1",
                "scopes": ["PROFIEL/SCOPE"],
                "datasets": {
                    "parkeervakken": {
                        "tables": {
                            "parkeervakken": {
                                "mandatoryFilterSets": [
                                    ["id"],
                                ],
                                "fields": {
                                    "type": "read",
                                    "soort": "letters:1",
                                },
                            }
                        }
                    }
                },
            }
        )
    )


@pytest.fixture
def profile_limited_type():
    """A profile that only exposes a field in limited way."""
    return models.Profile.create_for_schema(
        ProfileSchema.from_dict(
            {
                "name": "parkeerwacht-limited2",
                "id": "parkeerwacht-limited2",
                "scopes": ["PROFIEL2/SCOPE"],
                "datasets": {
                    "parkeervakken": {
                        "tables": {
                            "parkeervakken": {
                                "mandatoryFilterSets": [
                                    ["id", "type"],
                                ],
                                "fields": {
                                    "type": "letters:1",
                                    "soort": "read",
                                },
                            }
                        }
                    }
                },
            }
        )
    )


@pytest.fixture
def profiles_may():
    models.Profile.create_for_schema(
        ProfileSchema.from_dict(
            {
                "name": "mag_niet",
                "id": "mag_niet",
                "scopes": ["MAY/NOT"],
                "datasets": {
                    "parkeervakken": {
                        "tables": {
                            "parkeervakken": {
                                "permissions": "read",
                                "mandatoryFilterSets": [
                                    ["buurtcode", "type"],
                                ],
                            }
                        }
                    }
                },
            }
        )
    )
    models.Profile.create_for_schema(
        ProfileSchema.from_dict(
            {
                "name": "mag_wel",
                "id": "mag_wel",
                "scopes": ["MAY/ENTER"],
                "datasets": {
                    "parkeervakken": {
                        "tables": {
                            "parkeervakken": {
                                "permissions": "read",
                                "mandatoryFilterSets": [
                                    ["buurtcode", "type"],
                                    ["id"],
                                ],
                            }
                        }
                    }
                },
            }
        )
    )
    models.Profile.create_for_schema(
        ProfileSchema.from_dict(
            {
                "name": "alleen_volgnummer",
                "id": "alleen_volgnummer",
                "scopes": ["ONLY/VOLGNUMMER"],
                "datasets": {
                    "parkeervakken": {
                        "tables": {
                            "parkeervakken": {
                                "permissions": "read",
                                "mandatoryFilterSets": [
                                    ["id", "volgnummer"],
                                ],
                            }
                        }
                    }
                },
            }
        )
    )


@pytest.fixture()
def ggwgebieden_multiple_buurten_data(ggwgebieden_model, buurten_data, buurten_model):
    instance = ggwgebieden_model.objects.create(
        id="03630950000000.1",
        identificatie="03630950000000",
        volgnummer=1,
        begin_geldigheid=buurten_data.begin_geldigheid,
    )
    extra_buurt = buurten_model.objects.create(
        id="03630000000079.1",
        identificatie="03630000000079",
        volgnummer=1,
        naam="BBB v1",
        begin_geldigheid=buurten_data.begin_geldigheid,
        ligt_in_wijk_id=buurten_data.ligt_in_wijk_id,
        ligt_in_wijk_identificatie=buurten_data.ligt_in_wijk_identificatie,
        ligt_in_wijk_volgnummer=buurten_data.ligt_in_wijk_volgnummer,
    )
    ggwgebieden_model.bestaat_uit_buurten.through.objects.create(
        id=11,
        ggwgebieden_id=instance.id,
        ggwgebieden_identificatie=instance.identificatie,
        ggwgebieden_volgnummer=instance.volgnummer,
        bestaat_uit_buurten_id=buurten_data.id,
        bestaat_uit_buurten_identificatie=buurten_data.identificatie,
        bestaat_uit_buurten_volgnummer=buurten_data.volgnummer,
    )
    ggwgebieden_model.bestaat_uit_buurten.through.objects.create(
        id=22,
        ggwgebieden_id=instance.id,
        ggwgebieden_identificatie=instance.identificatie,
        ggwgebieden_volgnummer=instance.volgnummer,
        bestaat_uit_buurten_id=extra_buurt.id,
        bestaat_uit_buurten_identificatie=extra_buurt.identificatie,
        bestaat_uit_buurten_volgnummer=extra_buurt.volgnummer,
    )
    return instance


@pytest.fixture()
def stadsdeel_multiple_wijken_data(wijken_data, wijken_model):
    return wijken_model.objects.create(
        id="03630012052036.1",
        identificatie="03630012052036",
        volgnummer=1,
        begin_geldigheid=wijken_data.begin_geldigheid,
        naam="Nieuwmarkt",
        code="A02",
        ligt_in_stadsdeel_id=wijken_data.ligt_in_stadsdeel_id,
        ligt_in_stadsdeel_identificatie=wijken_data.ligt_in_stadsdeel_identificatie,
        ligt_in_stadsdeel_volgnummer=wijken_data.ligt_in_stadsdeel_volgnummer,
    )
