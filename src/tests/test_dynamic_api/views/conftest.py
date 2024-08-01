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
