import pytest
from django.urls import reverse

from tests.utils import read_response_json


@pytest.mark.django_db
class TestEmbedTemporalTables:
    """NOTE: the 'data' fixtures are"""

    def test_detail_expand_true_for_fk_relation(
        self, api_client, buurten_data, wijken_data, filled_router
    ):
        """Prove that ligtInWijk shows up when expanded"""

        url = reverse("dynamic_api:gebieden-buurten-detail", args=["03630000000078.2"])
        response = api_client.get(url, data={"_expand": "true"})
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert data["_embedded"]["ligtInWijk"]["identificatie"] == "03630012052035"
        assert data["_embedded"]["ligtInWijk"]["_links"]["buurt"] == {
            "count": 1,
            "href": "http://testserver/v1/gebieden/buurten?ligtInWijkId=03630012052035.1",
        }
        assert data == {
            "_links": {
                "ligtInWijk": {
                    "href": "http://testserver/v1/gebieden/wijken/03630012052035.1",
                    "identificatie": "03630012052035",
                    "title": "03630012052035.1",
                    "volgnummer": 1,
                },
                "onderdeelVanGGWGebieden": [],
                "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/buurten/v1",
                "self": {
                    "href": "http://testserver/v1/gebieden/buurten/03630000000078.2",
                    "identificatie": "03630000000078",
                    "title": "03630000000078.2",
                    "volgnummer": 2,
                },
            },
            "beginGeldigheid": "2021-06-11",
            "code": None,
            "eindGeldigheid": None,
            "geometrie": None,
            "identificatie": "03630000000078",
            "volgnummer": 2,
            "ligtInWijkId": "03630012052035",
            "naam": "AAA v2",
            "_embedded": {
                "onderdeelVanGGWGebieden": [],  # reverse M2M relation, but no data in fixtures
                "ligtInWijk": {
                    "_links": {
                        "schema": (
                            "https://schemas.data.amsterdam.nl/datasets/gebieden/wijken/v1"
                        ),
                        "self": {
                            "href": ("http://testserver/v1/gebieden/wijken/03630012052035.1"),
                            "identificatie": "03630012052035",
                            "title": "03630012052035.1",
                            "volgnummer": 1,
                        },
                        "buurt": {
                            # See that the link is properly added
                            "count": 1,
                            "href": (
                                "http://testserver/v1/gebieden/buurten"
                                "?ligtInWijkId=03630012052035.1"
                            ),
                        },
                        "ligtInStadsdeel": {
                            "href": ("http://testserver/v1/gebieden/stadsdelen/03630000000018.1"),
                            "identificatie": "03630000000018",
                            "title": "03630000000018.1",
                            "volgnummer": 1,
                        },
                    },
                    "identificatie": "03630012052035",
                    "volgnummer": 1,
                    "code": "A01",
                    "naam": "Burgwallen-Nieuwe Zijde",
                    "beginGeldigheid": "2021-02-28",
                    "eindGeldigheid": None,
                    "ligtInStadsdeelId": "03630000000018",
                    "_embedded": {
                        # second level embedded
                        "ligtInStadsdeel": {
                            "_links": {
                                "schema": (
                                    "https://schemas.data.amsterdam.nl"
                                    "/datasets/gebieden/stadsdelen/v1"
                                ),
                                "self": {
                                    "href": (
                                        "http://testserver/v1/gebieden/stadsdelen/03630000000018.1"
                                    ),
                                    "identificatie": "03630000000018",
                                    "title": "03630000000018.1",
                                    "volgnummer": 1,
                                },
                                # wijken is excluded (repeated relation)
                            },
                            "beginGeldigheid": "2021-02-28",
                            "code": "A",
                            "documentdatum": None,
                            "documentnummer": None,
                            "eindGeldigheid": None,
                            "geometrie": None,
                            "identificatie": "03630000000018",
                            "volgnummer": 1,
                            "ligtInGemeenteIdentificatie": None,
                            "naam": "Centrum",
                            "registratiedatum": None,
                        }
                    },
                },
            },
        }

    def test_detail_expand_true_reverse_fk_relation(self, api_client, wijken_data, filled_router):
        """Prove that the reverse stadsdelen.wijken can be expanded"""

        url = reverse("dynamic_api:gebieden-stadsdelen-detail", args=["03630000000018.1"])
        response = api_client.get(url, data={"_expand": "true"})
        data = read_response_json(response)
        assert response.status_code == 200, data

        assert data == {
            "_links": {
                "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/stadsdelen/v1",
                "self": {
                    "href": "http://testserver/v1/gebieden/stadsdelen/03630000000018.1",  # noqa: E501
                    "identificatie": "03630000000018",
                    "title": "03630000000018.1",
                    "volgnummer": 1,
                },
                "wijken": [
                    {
                        "href": "http://testserver/v1/gebieden/wijken/03630012052035.1",  # noqa: E501
                        "identificatie": "03630012052035",
                        "title": "03630012052035.1",
                        "volgnummer": 1,
                    }
                ],
            },
            "identificatie": "03630000000018",
            "volgnummer": 1,
            "code": "A",
            "naam": "Centrum",
            "geometrie": None,
            "documentdatum": None,
            "documentnummer": None,
            "registratiedatum": None,
            "beginGeldigheid": "2021-02-28",
            "eindGeldigheid": None,
            "ligtInGemeenteIdentificatie": None,
            "_embedded": {
                "wijken": [
                    # reverse relation
                    {
                        "_links": {
                            "buurt": {
                                "count": 0,
                                "href": "http://testserver/v1/gebieden/buurten?ligtInWijkId=03630012052035.1",  # noqa: E501
                            },
                            "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/wijken/v1",  # noqa: E501
                            "self": {
                                "href": "http://testserver/v1/gebieden/wijken/03630012052035.1",  # noqa: E501
                                "identificatie": "03630012052035",
                                "title": "03630012052035.1",
                                "volgnummer": 1,
                            },
                            # ligtInStadsdeel is removed (as it's a backward->forward match)
                        },
                        "identificatie": "03630012052035",
                        "volgnummer": 1,
                        "code": "A01",
                        "naam": "Burgwallen-Nieuwe Zijde",
                        "beginGeldigheid": "2021-02-28",
                        "eindGeldigheid": None,
                        "ligtInStadsdeelId": "03630000000018",
                    }
                ]
            },
        }

    def test_nested_expand_list(
        self, api_client, panden_data, buurten_data, wijken_data, filled_router
    ):
        """Prove that nesting of nesting also works."""
        url = reverse("dynamic_api:bag-panden-list")
        response = api_client.get(
            url,
            data={
                "_expand": "true",
                "_expandScope": "ligtInBouwblok.ligtInBuurt.ligtInWijk.ligtInStadsdeel",
                "naam": "Voorbeeldpand",
            },
        )
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert data == {
            "_embedded": {
                "panden": [
                    {
                        "_links": {
                            "schema": ("https://schemas.data.amsterdam.nl/datasets/bag/panden/v1"),
                            "self": {
                                "href": (
                                    "http://testserver/v1/bag/panden/0363100012061164"
                                    "?volgnummer=3"
                                ),
                                "identificatie": "0363100012061164",
                                "title": "0363100012061164.3",
                                "volgnummer": 3,
                            },
                            "heeftDossier": {
                                "href": "http://testserver/v1/bag/dossiers/GV00000406",
                                "title": "GV00000406",
                                "dossier": "GV00000406",
                            },
                            "ligtInBouwblok": {
                                "href": (
                                    "http://testserver/v1/gebieden/bouwblokken/03630012096483?volgnummer=1"
                                ),
                                "identificatie": "03630012096483",
                                "title": "03630012096483.1",
                                "volgnummer": 1,
                            },
                        },
                        "identificatie": "0363100012061164",
                        "volgnummer": 3,
                        "ligtInBouwblokId": "03630012096483",
                        "naam": "Voorbeeldpand",
                        "statusCode": 7,
                        "statusOmschrijving": "Sloopvergunning verleend",
                        "bagProces": {"code": 1},
                        "beginGeldigheid": "2021-02-28T10:00:00",
                        "eindGeldigheid": None,
                        "heeftDossierId": "GV00000406",
                    }
                ],
                "ligtInBouwblok": [
                    {
                        "_links": {
                            "schema": (
                                "https://schemas.data.amsterdam.nl/datasets/gebieden/bouwblokken/v1"
                            ),
                            "self": {
                                "href": (
                                    "http://testserver/v1/gebieden/bouwblokken/03630012096483?volgnummer=1"
                                ),
                                "identificatie": "03630012096483",
                                "title": "03630012096483.1",
                                "volgnummer": 1,
                            },
                            "ligtInBuurt": {
                                "href": (
                                    "http://testserver/v1/gebieden/buurten/03630000000078?volgnummer=2"
                                ),
                                "identificatie": "03630000000078",
                                "title": "03630000000078.2",
                                "volgnummer": 2,
                            },
                        },
                        "beginGeldigheid": "2021-02-28",
                        "code": None,
                        "eindGeldigheid": None,
                        "geometrie": None,
                        "identificatie": "03630012096483",
                        "volgnummer": 1,
                        "ligtInBuurtId": "03630000000078",
                        "registratiedatum": None,
                        "_embedded": {
                            "ligtInBuurt": {
                                "_links": {
                                    "schema": (
                                        "https://schemas.data.amsterdam.nl/datasets/gebieden/buurten/v1"
                                    ),
                                    "self": {
                                        "href": (
                                            "http://testserver/v1/gebieden/buurten/03630000000078?volgnummer=2"
                                        ),
                                        "identificatie": "03630000000078",
                                        "title": "03630000000078.2",
                                        "volgnummer": 2,
                                    },
                                    "ligtInWijk": {
                                        "href": (
                                            "http://testserver/v1/gebieden/wijken/03630012052035?volgnummer=1"
                                        ),
                                        "identificatie": "03630012052035",
                                        "title": "03630012052035.1",
                                        "volgnummer": 1,
                                    },
                                    "onderdeelVanGGWGebieden": [],
                                },
                                "identificatie": "03630000000078",
                                "volgnummer": 2,
                                "naam": "AAA v2",
                                "code": None,
                                "geometrie": None,
                                "beginGeldigheid": "2021-06-11",
                                "eindGeldigheid": None,
                                "ligtInWijkId": "03630012052035",
                                "_embedded": {
                                    "ligtInWijk": {
                                        "_embedded": {
                                            "ligtInStadsdeel": {
                                                "_links": {
                                                    "schema": (
                                                        "https://schemas.data.amsterdam.nl/datasets/gebieden/stadsdelen/v1"
                                                    ),
                                                    "self": {
                                                        "href": (
                                                            "http://testserver/v1/gebieden/stadsdelen/03630000000018?volgnummer=1"
                                                        ),
                                                        "identificatie": "03630000000018",
                                                        "title": "03630000000018.1",
                                                        "volgnummer": 1,
                                                    },
                                                    # wijken is excluded (repeated relation)
                                                },
                                                "beginGeldigheid": "2021-02-28",
                                                "code": "A",
                                                "documentdatum": None,
                                                "documentnummer": None,
                                                "eindGeldigheid": None,
                                                "geometrie": None,
                                                "identificatie": "03630000000018",
                                                "volgnummer": 1,
                                                "ligtInGemeenteIdentificatie": None,
                                                "naam": "Centrum",
                                                "registratiedatum": None,
                                            }
                                        },
                                        "_links": {
                                            "schema": (
                                                "https://schemas.data.amsterdam.nl/datasets/gebieden/wijken/v1"
                                            ),
                                            "self": {
                                                "href": (
                                                    "http://testserver/v1/gebieden/wijken/03630012052035?volgnummer=1"
                                                ),
                                                "identificatie": "03630012052035",
                                                "title": "03630012052035.1",
                                                "volgnummer": 1,
                                            },
                                            "buurt": {
                                                "count": 1,
                                                "href": (
                                                    "http://testserver/v1/gebieden/buurten?ligtInWijkId=03630012052035.1"
                                                ),
                                            },
                                            "ligtInStadsdeel": {
                                                "href": (
                                                    "http://testserver/v1/gebieden/stadsdelen/03630000000018?volgnummer=1"
                                                ),
                                                "identificatie": "03630000000018",
                                                "title": "03630000000018.1",
                                                "volgnummer": 1,
                                            },
                                        },
                                        "beginGeldigheid": "2021-02-28",
                                        "code": "A01",
                                        "eindGeldigheid": None,
                                        "identificatie": "03630012052035",
                                        "volgnummer": 1,
                                        "ligtInStadsdeelId": "03630000000018",
                                        "naam": "Burgwallen-Nieuwe Zijde",
                                    }
                                },
                            }
                        },
                    }
                ],
            },
            "_links": {
                "self": {
                    "href": (
                        "http://testserver/v1/bag/panden?_expand=true"
                        "&_expandScope=ligtInBouwblok.ligtInBuurt.ligtInWijk.ligtInStadsdeel"
                        "&naam=Voorbeeldpand"
                    )
                }
            },
            "page": {"number": 1, "size": 20},
        }

    def test_nested_expand_array(self, api_client, movies_data_with_actors, filled_router):
        """Prove that _expandScope works with an array-typed relation."""
        response = api_client.get("/v1/movies/movie/?_expandScope=actors")
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert data["_embedded"]["actors"][0]["name"] == "John Doe"

    def test_detail_no_expand_for_temporal_fk_relation(
        self, api_client, buurten_data, wijken_data, filled_router
    ):
        """Prove that temporal identifier fields have been removed from the body
        and only appear in the respective HAL envelopes"""

        url = reverse("dynamic_api:gebieden-buurten-detail", args=["03630000000078.2"])
        response = api_client.get(url)
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert data == {
            "_links": {
                "ligtInWijk": {
                    "href": "http://testserver/v1/gebieden/wijken/03630012052035.1",
                    "identificatie": "03630012052035",
                    "title": "03630012052035.1",
                    "volgnummer": 1,
                },
                "onderdeelVanGGWGebieden": [],
                "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/buurten/v1",
                "self": {
                    "href": "http://testserver/v1/gebieden/buurten/03630000000078.2",
                    "identificatie": "03630000000078",
                    "title": "03630000000078.2",
                    "volgnummer": 2,
                },
            },
            "beginGeldigheid": "2021-06-11",
            "code": None,
            "eindGeldigheid": None,
            "geometrie": None,
            "identificatie": "03630000000078",
            "volgnummer": 2,
            "ligtInWijkId": "03630012052035",
            "naam": "AAA v2",
        }

    def test_list_expand_true_for_fk_relation(
        self, api_client, buurten_data, wijken_data, filled_router
    ):
        """Prove that buurt shows up when listview is expanded and uses the
        latest volgnummer
        """

        url = reverse("dynamic_api:gebieden-buurten-list")
        url = f"{url}?_format=json&_expand=true"
        response = api_client.get(url)
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert data["_embedded"]["ligtInWijk"][0]["identificatie"] == "03630012052035"
        assert data["_embedded"]["ligtInWijk"][0]["volgnummer"] == 1
        assert data["_embedded"]["ligtInWijk"][0]["_links"]["buurt"] == {
            "count": 1,
            "href": (
                "http://testserver/v1/gebieden/buurten?_format=json&ligtInWijkId=03630012052035.1"
            ),
        }
        assert len(data["_embedded"]["buurten"]) == 1  # no historical records
        assert data == {
            "_embedded": {
                "buurten": [
                    # Main response
                    {
                        "_links": {
                            "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/buurten/v1",  # noqa: E501
                            "self": {
                                "href": "http://testserver/v1/gebieden/buurten/03630000000078?_format=json&volgnummer=2",  # noqa: E501
                                "identificatie": "03630000000078",
                                "title": "03630000000078.2",
                                "volgnummer": 2,
                            },
                            "ligtInWijk": {
                                "href": "http://testserver/v1/gebieden/wijken/03630012052035?_format=json&volgnummer=1",  # noqa: E501
                                "identificatie": "03630012052035",
                                "title": "03630012052035.1",
                                "volgnummer": 1,
                            },
                            "onderdeelVanGGWGebieden": [],
                        },
                        "identificatie": "03630000000078",
                        "volgnummer": 2,
                        "code": None,
                        "naam": "AAA v2",
                        "beginGeldigheid": "2021-06-11",
                        "eindGeldigheid": None,
                        "geometrie": None,
                        "ligtInWijkId": "03630012052035",
                    },
                ],
                "ligtInWijk": [
                    # Embedded object in next section
                    {
                        "_links": {
                            "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/wijken/v1",  # noqa: E501
                            "self": {
                                "href": "http://testserver/v1/gebieden/wijken/03630012052035?_format=json&volgnummer=1",  # noqa: E501
                                "identificatie": "03630012052035",
                                "title": "03630012052035.1",
                                "volgnummer": 1,
                            },
                            "buurt": {
                                "count": 1,
                                "href": "http://testserver/v1/gebieden/buurten?_format=json&ligtInWijkId=03630012052035.1",  # noqa: E501
                            },
                            "ligtInStadsdeel": {
                                "href": "http://testserver/v1/gebieden/stadsdelen/03630000000018?_format=json&volgnummer=1",  # noqa: E501
                                "identificatie": "03630000000018",
                                "title": "03630000000018.1",
                                "volgnummer": 1,
                            },
                        },
                        "beginGeldigheid": "2021-02-28",
                        "code": "A01",
                        "eindGeldigheid": None,
                        "identificatie": "03630012052035",
                        "volgnummer": 1,
                        "ligtInStadsdeelId": "03630000000018",
                        "naam": "Burgwallen-Nieuwe Zijde",
                        "_embedded": {
                            # Nested embedding (1 level)
                            "ligtInStadsdeel": {
                                "_links": {
                                    "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/stadsdelen/v1",  # noqa: E501
                                    "self": {
                                        "href": "http://testserver/v1/gebieden/stadsdelen/03630000000018?_format=json&volgnummer=1",  # noqa: E501
                                        "identificatie": "03630000000018",
                                        "title": "03630000000018.1",
                                        "volgnummer": 1,
                                    },
                                    # wijken is excluded here (forward/reverse relation loop)
                                },
                                "beginGeldigheid": "2021-02-28",
                                "code": "A",
                                "documentdatum": None,
                                "documentnummer": None,
                                "eindGeldigheid": None,
                                "geometrie": None,
                                "identificatie": "03630000000018",
                                "volgnummer": 1,
                                "ligtInGemeenteIdentificatie": None,
                                "naam": "Centrum",
                                "registratiedatum": None,
                            }
                        },
                    }
                ],
                "onderdeelVanGGWGebieden": [],
            },
            "_links": {
                "self": {"href": "http://testserver/v1/gebieden/buurten?_format=json&_expand=true"}
            },
            "page": {"number": 1, "size": 20},
        }

    def test_expand_warning_reverse_summary(
        self, api_client, buurten_data, wijken_data, filled_router
    ):
        """Prove that expanding on an additionalRelations with format=summary is not possible,
        AND that it shows a custom error message to improve developer experience.
        """
        url = reverse("dynamic_api:gebieden-wijken-list")
        response = api_client.get(url, {"_format": "json", "_expandScope": "buurt"})
        data = read_response_json(response)
        assert response.status_code == 400, data
        assert data == {
            "detail": (
                "The field 'buurt' is not available for embedding"
                " as it's a summary of a huge listing."
            ),
            "status": 400,
            "title": "Malformed request.",
            "type": "urn:apiexception:parse_error",
        }

    def test_detail_expand_true_for_m2m_relation(
        self, api_client, buurten_data, ggwgebieden_data, filled_router
    ):
        """Prove that bestaatUitBuurten shows up when expanded"""
        url = reverse("dynamic_api:gebieden-ggwgebieden-detail", args=["03630950000000.1"])
        response = api_client.get(url, data={"_expand": "true"})
        data = read_response_json(response)

        assert response.status_code == 200, data

        assert data["_links"] == {
            "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/ggwgebieden/v1",
            "self": {
                "href": "http://testserver/v1/gebieden/ggwgebieden/03630950000000.1",
                "identificatie": "03630950000000",
                "title": "03630950000000.1",
                "volgnummer": 1,
            },
            "bestaatUitBuurten": [
                # Only the current active object, not the historical one!
                # This happens in the DynamicListSerializer.get_attribute() logic.
                {
                    "href": "http://testserver/v1/gebieden/buurten/03630000000078.2",
                    "identificatie": "03630000000078",
                    "title": "03630000000078.2",
                    "volgnummer": 2,
                }
            ],
        }
        assert data["_embedded"] == {
            "bestaatUitBuurten": [
                {
                    # In a detail view, the main object is not found in _embedded.
                    # It should also include the active object only.
                    "_links": {
                        "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/buurten/v1",  # noqa: E501
                        "self": {
                            "href": "http://testserver/v1/gebieden/buurten/03630000000078.2",  # noqa: E501
                            "identificatie": "03630000000078",
                            "title": "03630000000078.2",
                            "volgnummer": 2,
                        },
                        "ligtInWijk": None,
                    },
                    "beginGeldigheid": "2021-06-11",
                    "code": None,
                    "eindGeldigheid": None,
                    "geometrie": None,
                    "identificatie": "03630000000078",
                    "volgnummer": 2,
                    "ligtInWijkId": "03630012052035",
                    "naam": "AAA v2",
                    "_embedded": {
                        "ligtInWijk": None,
                    },
                }
            ]
        }

    def test_list_expand_true_for_m2m_relation(
        self, api_client, buurten_data, ggwgebieden_data, filled_router
    ):
        """Prove that buurt shows up when listview is expanded and uses the
        latest volgnummer
        """

        url = reverse("dynamic_api:gebieden-ggwgebieden-list")
        response = api_client.get(url, data={"_expand": "true"})
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert data["_embedded"] == {
            "ggwgebieden": [
                {
                    "_links": {
                        "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/ggwgebieden/v1",  # noqa: E501
                        "self": {
                            "href": "http://testserver/v1/gebieden/ggwgebieden/03630950000000?volgnummer=1",  # noqa: E501
                            "title": "03630950000000.1",
                            "volgnummer": 1,
                            "identificatie": "03630950000000",
                        },
                        "bestaatUitBuurten": [
                            # M2M relation, a list of objects.
                            {
                                "href": "http://testserver/v1/gebieden/buurten/03630000000078?volgnummer=2",  # noqa: E501
                                "title": "03630000000078.2",
                                "identificatie": "03630000000078",
                                "volgnummer": 2,
                            }
                        ],
                    },
                    "identificatie": "03630950000000",
                    "volgnummer": 1,
                    "registratiedatum": None,
                    "naam": None,
                    "beginGeldigheid": "2021-02-28",
                    "eindGeldigheid": None,
                    "geometrie": None,
                }
            ],
            "bestaatUitBuurten": [
                # The embedded object, via an M2M relation
                {
                    "_links": {
                        "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/buurten/v1",  # noqa: E501
                        "self": {
                            "href": "http://testserver/v1/gebieden/buurten/03630000000078?volgnummer=2",  # noqa: E501
                            "title": "03630000000078.2",
                            "volgnummer": 2,
                            "identificatie": "03630000000078",
                        },
                        "ligtInWijk": None,
                    },
                    "identificatie": "03630000000078",
                    "volgnummer": 2,
                    "naam": "AAA v2",
                    "code": None,
                    "beginGeldigheid": "2021-06-11",
                    "eindGeldigheid": None,
                    "ligtInWijkId": "03630012052035",
                    "geometrie": None,
                    "_embedded": {
                        "ligtInWijk": None,
                    },
                }
            ],
        }

    def test_list_expand_true_for_reverse_m2m_relation(
        self,
        api_client,
        ggwgebieden_data,
        filled_router,
    ):
        """Prove that nesting of nesting also works."""
        url = reverse("dynamic_api:gebieden-buurten-list")
        response = api_client.get(
            url,
            data={
                "_expand": "true",
                "_expandScope": "onderdeelVanGGWGebieden",
            },
        )
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert data["_embedded"] == {
            "buurten": [
                {
                    "_links": {
                        "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/buurten/v1",  # noqa: E501
                        "self": {
                            "href": "http://testserver/v1/gebieden/buurten/03630000000078?volgnummer=2",  # noqa: E501
                            "identificatie": "03630000000078",
                            "title": "03630000000078.2",
                            "volgnummer": 2,
                        },
                        "ligtInWijk": None,
                        "onderdeelVanGGWGebieden": [
                            {
                                "href": "http://testserver/v1/gebieden/ggwgebieden/03630950000000?volgnummer=1",  # noqa: E501
                                "identificatie": "03630950000000",
                                "title": "03630950000000.1",
                                "volgnummer": 1,
                            }
                        ],
                    },
                    "beginGeldigheid": "2021-06-11",
                    "code": None,
                    "eindGeldigheid": None,
                    "geometrie": None,
                    "identificatie": "03630000000078",
                    "volgnummer": 2,
                    "ligtInWijkId": "03630012052035",
                    "naam": "AAA v2",
                }
            ],
            "onderdeelVanGGWGebieden": [
                {
                    "_links": {
                        "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/ggwgebieden/v1",  # noqa: E501
                        "self": {
                            "href": "http://testserver/v1/gebieden/ggwgebieden/03630950000000?volgnummer=1",  # noqa: E501
                            "identificatie": "03630950000000",
                            "title": "03630950000000.1",
                            "volgnummer": 1,
                        },
                        "bestaatUitBuurten": [
                            {
                                "href": "http://testserver/v1/gebieden/buurten/03630000000078?volgnummer=2",  # noqa: E501
                                "identificatie": "03630000000078",
                                "title": "03630000000078.2",
                                "volgnummer": 2,
                            },
                        ],
                    },
                    "beginGeldigheid": "2021-02-28",
                    "eindGeldigheid": None,
                    "geometrie": None,
                    "identificatie": "03630950000000",
                    "volgnummer": 1,
                    "naam": None,
                    "registratiedatum": None,
                }
            ],
        }

    def test_through_extra_fields_for_m2m_relation(
        self, api_client, buurten_data, ggpgebieden_data, filled_router
    ):
        """Prove that extra through fields are showing up
        latest volgnummer
        """

        url = reverse("dynamic_api:gebieden-ggpgebieden-list")
        response = api_client.get(url)
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert dict(data["_embedded"]["ggpgebieden"][0]) == {
            "_links": {
                "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/ggpgebieden/v1",  # noqa: E501
                "self": {
                    "href": "http://testserver/v1/gebieden/ggpgebieden/03630950000000?volgnummer=1",  # noqa: E501
                    "title": "03630950000000.1",
                    "volgnummer": 1,
                    "identificatie": "03630950000000",
                },
                "bestaatUitBuurten": [
                    {
                        "href": "http://testserver/v1/gebieden/buurten/03630000000078?volgnummer=2",  # noqa: E501
                        "title": "03630000000078.2",
                        "volgnummer": 2,
                        "identificatie": "03630000000078",
                        "beginGeldigheid": "2021-03-04",  # from relation!
                        "eindGeldigheid": None,  # from relation!
                    },
                ],
            },
            "geometrie": None,
            "identificatie": "03630950000000",
            "volgnummer": 1,
            "eindGeldigheid": None,
            "beginGeldigheid": "2021-02-28",
            "naam": None,
            "registratiedatum": None,
        }

    def test_detail_no_expand_for_loose_relation(
        self, api_client, statistieken_data, buurten_data, filled_router
    ):
        """Without _expand=true there is no _embedded field.
        The buurt link must appear in the _links field inside an HAL envelope.
        The "buurtId" field in is how the field is known in the statistieken dataset, and must
        appear in the body of the response.
        The buurt link is not resolved to the latest volgnummer, but "identificatie" is specified,
        which is the identifier used by the gebieden dataset.
        """

        url = reverse("dynamic_api:meldingen-statistieken-detail", args=[1])
        response = api_client.get(url)
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert data == {
            "_links": {
                "buurt": {
                    "href": "http://testserver/v1/gebieden/buurten/03630000000078",
                    "title": "03630000000078",
                    "identificatie": "03630000000078",
                },
                "schema": "https://schemas.data.amsterdam.nl/datasets/meldingen/statistieken/v1",  # noqa: E501
                "self": {
                    "href": "http://testserver/v1/meldingen/statistieken/1",
                    "title": "1",
                    "id": 1,
                },
            },
            "id": 1,
            "buurtId": "03630000000078",
        }

    def test_detail_expand_true_for_loose_relation(
        self, api_client, statistieken_data, buurten_data, filled_router
    ):
        """Prove that buurt shows up when expanded and uses the
        latest volgnummer
        """

        url = reverse("dynamic_api:meldingen-statistieken-detail", args=[1])
        response = api_client.get(url, data={"_expand": "true"})
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert data == {
            "_links": {
                "schema": "https://schemas.data.amsterdam.nl/datasets/meldingen/statistieken/v1",  # noqa: E501
                "self": {
                    "href": "http://testserver/v1/meldingen/statistieken/1",
                    "title": "1",
                    "id": 1,
                },
                "buurt": {
                    "href": "http://testserver/v1/gebieden/buurten/03630000000078",
                    "identificatie": "03630000000078",
                    "title": "03630000000078",
                },
            },
            "id": 1,
            "buurtId": "03630000000078",
            "_embedded": {
                "buurt": {
                    "_links": {
                        "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/buurten/v1",  # noqa: E501
                        "self": {
                            "href": "http://testserver/v1/gebieden/buurten/03630000000078?volgnummer=2",  # noqa: E501
                            "title": "03630000000078.2",
                            "volgnummer": 2,
                            "identificatie": "03630000000078",
                        },
                        "ligtInWijk": None,
                        "onderdeelVanGGWGebieden": [],
                    },
                    "code": None,
                    "naam": "AAA v2",
                    "geometrie": None,
                    "eindGeldigheid": None,
                    "beginGeldigheid": "2021-06-11",
                    "identificatie": "03630000000078",
                    "volgnummer": 2,
                    "ligtInWijkId": "03630012052035",
                    "_embedded": {
                        "ligtInWijk": None,
                        "onderdeelVanGGWGebieden": [],  # reverse m2m, but no fixture data given
                    },
                }
            },
        }

    def test_list_expand_true_for_loose_relation(
        self, api_client, statistieken_data, buurten_data, filled_router
    ):
        """Prove that buurt shows up when listview is expanded and uses the
        latest volgnummer
        """
        url = reverse("dynamic_api:meldingen-statistieken-list")
        response = api_client.get(url, data={"_expand": "true"})
        data = read_response_json(response)

        assert response.status_code == 200, data

        # Main object:
        assert data["_embedded"]["statistieken"][0]["_links"]["buurt"] == {
            "href": "http://testserver/v1/gebieden/buurten/03630000000078",
            "title": "03630000000078",
            "identificatie": "03630000000078",
        }
        assert "_embedded" not in data["_embedded"]["statistieken"][0]

        # Embedded object from loose relation:
        assert data["_embedded"]["buurt"][0]["identificatie"] == "03630000000078"
        assert data["_embedded"]["buurt"][0]["volgnummer"] == 2
        assert data["_embedded"]["buurt"][0]["_links"]["self"] == {
            "href": "http://testserver/v1/gebieden/buurten/03630000000078?volgnummer=2",
            "identificatie": "03630000000078",
            "title": "03630000000078.2",
            "volgnummer": 2,
        }

    def test_list_expand_true_non_tempooral_loose_many_to_many_to_temporal(
        self, api_client, buurten_data, woningbouwplannen_data, filled_router
    ):
        """_embedded must contain for each FK or MN relation a key (with camelCased fieldname)
        containing a list of all record-sets that are being referred to
        for loose relations, each set must be resolved to its latest 'volgnummer'
        _embedded must also contain a key (with table name)
          containing a (filtered) list of items.
        the FK or NM relation keys in those items are urls without volgnummer

        Check the loose coupling of woningbouwplan with buurten
        The "identificatie" fieldname is taken from the related buurten model.
        Note that "volgnummer" is not specified within the woningbouwplan data (which
        makes it "loose"), and therefore not mentioned here"""

        url = reverse("dynamic_api:woningbouwplannen-woningbouwplan-list")
        response = api_client.get(url, data={"_expand": "true"})
        data = read_response_json(response)
        assert response.status_code == 200, data

        #  _embedded must contain for each FK or MN relation a key (with camelCased fieldname)
        #  containing a list of all records that are being referred to
        #  for loose relations, these must be resolved to the latest 'volgnummer'
        #  _embedded must also contain a key (with table name)
        #    containing a (filtered) list of items.
        # the FK or NM relation keys in those items are urls without volgnummer

        #  Check that the embedded buurten contains the correct "identificatie",
        #  and is now also resolved to the latest "volgnummer", which is specified.
        assert data["_embedded"]["buurten"][0]["_links"]["self"] == {
            "href": "http://testserver/v1/gebieden/buurten/03630000000078?volgnummer=2",
            "title": "03630000000078.2",
            "identificatie": "03630000000078",
            "volgnummer": 2,
        }
        assert data["_embedded"]["buurten"][0]["identificatie"] == "03630000000078"
        assert data["_embedded"]["buurten"][0]["volgnummer"] == 2

    def test_links_loose_many_to_many_to_temporal(
        self, api_client, buurten_data, woningbouwplannen_data, filled_router
    ):
        """Prove that _links contains:
        - the loose identifier of the related entity
        - a URL that loosely points to the related entity
        - a title field
        """

        url = reverse("dynamic_api:woningbouwplannen-woningbouwplan-list")
        response = api_client.get(url)
        data = read_response_json(response)
        assert response.status_code == 200, data

        assert data["_embedded"]["woningbouwplan"][0]["_links"]["buurten"] == [
            {
                "href": "http://testserver/v1/gebieden/buurten/03630000000078",
                "title": "03630000000078",
                "identificatie": "03630000000078",
            }
        ]

    def test_links_many_to_many_to_temporal(
        self, api_client, buurten_data, woningbouwplannen_data, filled_router
    ):
        """Prove that _links contains:
        - the identifier of the related entity
        - the temporal identifier of the related entity
        - a URL that points to the exact related entity
        - a title field
        """

        url = reverse("dynamic_api:woningbouwplannen-woningbouwplan-list")
        response = api_client.get(url)
        data = read_response_json(response)
        assert response.status_code == 200, data

        assert data["_embedded"]["woningbouwplan"][0]["_links"]["buurtenregular"] == [
            {
                "href": "http://testserver/v1/gebieden/buurten/03630000000078?volgnummer=2",
                "title": "03630000000078.2",
                "identificatie": "03630000000078",
                "volgnummer": 2,
            }
        ]

    def test_links_many_to_many_to_non_temporal(
        self, api_client, woningbouwplannen_data, filled_router
    ):
        """Prove that _links contains:
        - the identifier of the related entity
        - a URL that points to the exact related entity
        - a title field
        """

        url = reverse("dynamic_api:woningbouwplannen-woningbouwplan-list")
        response = api_client.get(url)
        data = read_response_json(response)
        assert response.status_code == 200, data

        assert data["_embedded"]["woningbouwplan"][0]["_links"]["nontemporeleNm"] == [
            {
                "href": "http://testserver/v1/woningbouwplannen/nontemporeel/1234",
                "title": "4displayonly",
                "sleutel": "1234",
            }
        ]

    def test_detail_expand_true_non_temporal_many_to_many_to_temporal(
        self,
        api_client,
        woningbouwplan_model,
        woningbouwplannen_data,
        filled_router,
    ):
        url = reverse("dynamic_api:woningbouwplannen-woningbouwplan-detail", args=[1])
        response = api_client.get(url, data={"_expand": "true"})
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert "buurten" not in data  # because it must be in  "_embedded"
        buurten = data["_embedded"]["buurten"]
        assert buurten[0]["identificatie"] == "03630000000078"
        assert buurten[0]["volgnummer"] == 2
        assert buurten[0]["_links"]["self"]["href"] == (
            "http://testserver/v1/gebieden/buurten/03630000000078?volgnummer=2"
        )

    def test_list_count_true(self, api_client, afval_container, filled_router):
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url, data={"_count": "true"})
        data = read_response_json(response)

        assert response.status_code == 200, data
        assert data["page"]["totalElements"] == 1
        assert data["page"]["totalPages"] == 1
        assert response["X-Pagination-Count"] == "1"
        assert response["X-Total-Count"] == "1"

    @pytest.mark.parametrize("data", [{}, {"_count": "false"}, {"_count": "0"}, {"_count": "1"}])
    def test_list_count_falsy(self, api_client, afval_container, filled_router, data):
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url, data=data)
        data = read_response_json(response)

        assert response.status_code == 200, data
        assert "X-Total-Count" not in response
        assert "X-Pagination-Count" not in response
        assert "totalElements" not in data["page"]
        assert "totalPages" not in data["page"]
