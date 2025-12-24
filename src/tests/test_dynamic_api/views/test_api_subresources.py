import pytest
from django.urls import reverse

from tests.utils import read_response_json


@pytest.mark.django_db
class TestSubResources:
    def test_nested_routes_list(self, api_client, stadsdelen_subresources, wijken_subresources):
        centrum = stadsdelen_subresources["centrum"]
        url = reverse(
            "dynamic_api:gebieden_subresources-stadsdelen-wijken-list",
            args=[centrum.id],
        )

        response = api_client.get(url)
        assert response.status_code == 200
        result = read_response_json(response)
        result_wijken = [wijk["naam"] for wijk in result["_embedded"]["wijken"]]
        for wijk in wijken_subresources.values():
            assert wijk.naam in result_wijken or wijk.ligt_in_stadsdeel != centrum

    def test_nested_routes_detail(self, api_client, stadsdelen_subresources, wijken_subresources):
        centrum = stadsdelen_subresources["centrum"]
        haarlemmerbuurt = wijken_subresources["haarlemmerbuurt"]
        url = reverse(
            "dynamic_api:gebieden_subresources-stadsdelen-wijken-detail",
            args=[centrum.id, haarlemmerbuurt.id],
        )

        response = api_client.get(url)
        assert response.status_code == 200
        result = read_response_json(response)
        assert haarlemmerbuurt.naam == result["naam"]

    def test_nested_routes_multiple_levels_list(
        self, api_client, stadsdelen_subresources, wijken_subresources, buurten_subresources
    ):
        centrum = stadsdelen_subresources["centrum"]
        haarlemmerbuurt = wijken_subresources["haarlemmerbuurt"]
        url = reverse(
            "dynamic_api:gebieden_subresources-stadsdelen-wijken-buurten-list",
            args=[centrum.id, haarlemmerbuurt.id],
        )

        response = api_client.get(url)
        assert response.status_code == 200
        result = read_response_json(response)
        result_buurten = [buurt["naam"] for buurt in result["_embedded"]["buurten"]]
        for buurt in buurten_subresources.values():
            assert buurt.naam in result_buurten or buurt.ligt_in_wijk != haarlemmerbuurt

    def test_nested_routes_multiple_levels_detail(
        self, api_client, stadsdelen_subresources, wijken_subresources, buurten_subresources
    ):
        centrum = stadsdelen_subresources["centrum"]
        haarlemmerbuurt = wijken_subresources["haarlemmerbuurt"]
        westerdokseiland = buurten_subresources["westerdokseiland"]
        url = reverse(
            "dynamic_api:gebieden_subresources-stadsdelen-wijken-buurten-detail",
            args=[centrum.id, haarlemmerbuurt.id, westerdokseiland.id],
        )

        response = api_client.get(url)
        assert response.status_code == 200
        result = read_response_json(response)
        assert westerdokseiland.naam == result["naam"]

    def test_nested_resource_detail_not_available_under_wrong_parent(
        self, api_client, stadsdelen_subresources, wijken_subresources
    ):
        centrum = stadsdelen_subresources["centrum"]
        venserpolder = wijken_subresources["venserpolder"]
        url = reverse(
            "dynamic_api:gebieden_subresources-stadsdelen-wijken-detail",
            args=[centrum.id, venserpolder.id],
        )

        response = api_client.get(url)
        assert response.status_code == 404

    def test_nested_resource_multilevel_list_not_available_under_wrong_parent(
        self, api_client, stadsdelen_subresources, wijken_subresources
    ):
        centrum = stadsdelen_subresources["centrum"]
        venserpolder = wijken_subresources["venserpolder"]
        url = reverse(
            "dynamic_api:gebieden_subresources-stadsdelen-wijken-buurten-list",
            args=[centrum.id, venserpolder.id],
        )

        response = api_client.get(url)
        assert response.status_code == 200
        result = read_response_json(response)
        assert result["_embedded"]["buurten"] == []
