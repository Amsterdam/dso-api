import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_removal_of_falsy_query_params(
    api_client,
    fetch_auth_token,
    parkeervakken_schema,
    parkeervakken_parkeervak_model,
):
    """ Prove that falsy query params do not lead to queries."""
    base_url = reverse("dynamic_api:parkeervakken-parkeervakken-list")

    query_param = ("buurtcode", "A05d")
    response = api_client.get(base_url + "?{}={}".format(*query_param))
    assert list(response.wsgi_request.GET.items()) == [query_param]

    query_param = ("buurtcode", "")
    response = api_client.get(base_url + "?{}={}".format(*query_param))
    assert list(response.wsgi_request.GET.items()) == []

    response = api_client.get(base_url + "?{}=".format("buurtcode"))
    assert list(response.wsgi_request.GET.items()) == []
