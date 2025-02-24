from __future__ import annotations

import math
from datetime import date

import pytest
from django.apps import apps
from django.http import QueryDict
from django.utils.timezone import now
from rest_framework.exceptions import ValidationError
from schematools.contrib.django.models import Dataset
from schematools.permissions import UserScopes

from dso_api.dynamic_api.filters import parser
from dso_api.dynamic_api.filters.lookups import _sql_wildcards
from dso_api.dynamic_api.filters.values import _parse_point, _validate_correct_x_y, str2geo
from rest_framework_dso.crs import RD_NEW


class TestWildcard:
    @pytest.mark.django_db
    def test_like_filter_sql(self, django_assert_num_queries):
        with django_assert_num_queries(1) as context:
            # using str(qs.query) doesn't apply database-level escaping,
            # so running the query instead to get the actual executed query.
            list(Dataset.objects.filter(name__like="foo*bar?"))

        sql = context.captured_queries[0]["sql"]
        assert r"""."name") LIKE 'foo%bar_'""" in sql


def test_sql_wildcards():
    assert _sql_wildcards("foo*") == "foo%"
    assert _sql_wildcards("fo?o") == r"fo_o"
    assert _sql_wildcards("fo%o") == r"fo\%o"
    assert _sql_wildcards("fo%o_") == r"fo\%o\_"
    assert _sql_wildcards("f?_oob%ar*") == r"f_\_oob\%ar%"


def create_filter_engine(query_string: str, request_scopes=()) -> parser.QueryFilterEngine:
    """Simulate creation of a filter engine, based on request data."""
    get_params = QueryDict(query_string)
    return parser.QueryFilterEngine(
        user_scopes=UserScopes(get_params, request_scopes),
        query=get_params,
        input_crs=RD_NEW,
        request_date=now(),
    )


@pytest.mark.django_db
class TestFilterEngine:
    """Test the individual parts of the filter engine."""

    @pytest.fixture
    def movie1(self, movies_model, movies_category):
        return movies_model.objects.create(
            id=1,
            name="movie1",
            category=movies_category,
            date_added=date(2020, 2, 1),
            enjoyable=True,
        )

    @pytest.fixture
    def movie2(self, movies_model, movies_category):
        return movies_model.objects.create(
            id=2, name="movie2", date_added=date(2020, 3, 1), url="http://example.com/someurl"
        )

    @pytest.mark.parametrize(
        "query,expect",
        [
            # Date less than
            ("dateAdded[lt]=2020-2-10", {"movie1"}),
            ("dateAdded[lt]=2020-3-1", {"movie1"}),
            ("dateAdded[lte]=2020-3-1", {"movie1", "movie2"}),
            # Date less than full datetime
            ("dateAdded[lt]=2020-3-1T23:00:00", {"movie1", "movie2"}),
            # Date greater than
            ("dateAdded[gt]=2020-2-10", {"movie2"}),
            ("dateAdded[gt]=2020-3-1", set()),
            ("dateAdded[gte]=2020-3-1", {"movie2"}),
            # Test in filter
            ("dateAdded[in]=2020-2-1,2022-5-5", {"movie1"}),
            ("dateAdded[in]=2020-2-1,2020-3-1,2022-5-5", {"movie1", "movie2"}),
            # Not (can be repeated for "AND NOT" testing)
            ("dateAdded[not]=2020-2-1", {"movie2"}),
            ("dateAdded[not]=2020-2-1&dateAdded[not]=2020-3-1", set()),
            # Booleans
            ("enjoyable=true", {"movie1"}),
            ("enjoyable=false", set()),
            ("enjoyable[isnull]=true", {"movie2"}),
            ("enjoyable[isnull]=false", {"movie1"}),
            # URLs have string-like comparison operators
            ("url[in]=foobar,http://example.com/someurl", {"movie2"}),
            ("url[like]=http:*", {"movie2"}),
            ("url[isnull]=true", {"movie1"}),
        ],
    )
    def test_filter_logic(self, movies_model, movie1, movie2, query, expect):
        engine = create_filter_engine(query)
        qs = engine.filter_queryset(movies_model.objects.all())
        assert {obj.name for obj in qs} == expect, str(qs.query)

    @pytest.mark.parametrize(
        "query,expect",
        [
            # IN filter
            ("category.id[in]={cat_id}", ["movie1"]),  # test ID
            ("category.id[in]={cat_id},{cat_id}", ["movie1"]),  # test comma
            ("category.id[in]=97,98,{cat_id}", ["movie1"]),  # test invalid IDs
            ("category.id[in]=97,98,99", []),  # test all invalid IDs
            # NOT filter
            ("category.id[not]={cat_id}", ["movie2"]),
            ("category.id[not]=99", ["movie1", "movie2"]),
            # Old deprecated notation:
            ("categoryId[in]={cat_id}", ["movie1"]),
            ("categoryId[not]=99", ["movie1", "movie2"]),
        ],
    )
    def test_foreignkey(self, movies_model, movie1, movie2, category, query, expect):
        # Replace {cat_id} in values:
        query = query.format(cat_id=category.pk)
        engine = create_filter_engine(query)
        qs = engine.filter_queryset(movies_model.objects.all())
        assert sorted(obj.name for obj in qs) == expect, str(qs.query)

    def test_m2m(self, movies_model, movies_data_with_actors):
        """Prove that M2M queries work, and still return the object only once."""
        engine = create_filter_engine("actors.name[like]=J*")
        qs = engine.filter_queryset(movies_model.objects.all())
        names = [obj.name for obj in qs]  # list to check for duplicates
        assert names == ["foo123"]  # no duplicate
        assert qs.query.distinct  # prove that SELECT DISTINCT was used.

    @staticmethod
    def test_filter_nested_table(
        parkeervakken_dataset, parkeervakken_parkeervak_model, parkeervakken_regime_model
    ):
        """Prove that the serializer factory properly generates nested tables.
        Serialiser should contain reverse relations.
        """
        # reload model from APPs registry, in ordeer to fetch all relations.
        Parkeervakken = apps.get_model("parkeervakken", "parkeervakken")
        parkeervak = parkeervakken_parkeervak_model.objects.create(
            id="121138489047",
            type="File",
            soort="MULDER",
            aantal=1.0,
            e_type="E9",
            buurtcode="A05d",
            straatnaam="Zoutkeetsgracht",
        )
        parkeervakken_regime_model.objects.create(
            id=1,
            parent=parkeervak,
            bord="",
            dagen=["ma", "di", "wo", "do", "vr", "za", "zo"],
            soort="MULDER",
            aantal=None,
            e_type="E9",
            kenteken="69-SF-NT",
            opmerking="",
            eindtijd="23:59:00",
            begintijd="00:00:00",
            einddatum=None,
            begindatum=None,
        )
        other_parkeervak = parkeervakken_parkeervak_model.objects.create(
            id="121138489006",
            type="File",
            soort="MULDER",
            aantal=1.0,
            e_type="E6b",
            buurtcode="A05d",
            straatnaam="Zoutkeetsgracht",
        )
        parkeervakken_regime_model.objects.create(
            id=2,
            parent=other_parkeervak,
            bord="",
            dagen=["ma", "di", "wo", "do", "vr", "za", "zo"],
            soort="MULDER",
            aantal=None,
            e_type="E6b",
            kenteken="69-SF-NT",
            opmerking="",
            eindtijd="23:59:00",
            begintijd="00:00:00",
            einddatum=None,
            begindatum=None,
        )

        engine = create_filter_engine("regimes.eType=E6b")
        result = engine.filter_queryset(Parkeervakken.objects.all())
        assert result.count() == 1, result

    @staticmethod
    @pytest.mark.parametrize(
        "query,expect",
        [
            ("", 2),
            ("ligtInBouwblok.identificatie=03630012096483&ligtInBouwblok.volgnummer=1", 1),
            ("ligtInBouwblok.identificatie=03630012096483&ligtInBouwblok.volgnummer=2", 0),
            ("ligtInBouwblokId=03630012096483.1", 1),  # deprecated format, but test anyway!
            ("ligtInBouwblok=03630012096483.1", 1),  # direct query against field name
            ("ligtInBouwblokId=123", 0),
            ("ligtInBouwblok=123", 0),
            ("ligtInBouwblok.ligtInBuurtId=03630000000078.2", 1),
            ("ligtInBouwblok.ligtInBuurt.identificatie=03630000000078", 1),
            ("ligtInBouwblok.identificatie[isnull]=true", 1),
            ("ligtInBouwblok.identificatie[isnull]=false", 1),
            ("heeftDossier[isnull]=true", 1),
            ("heeftDossier.dossier=GV00000406", 1),
        ],
    )
    def test_filter_temporal(bag_dataset, panden_model, panden_data, query, expect):
        """Test that filtering on temporal relations works.
        This checks both the dotted-notation, and the old 'compositeKeyId' FK field.
        """
        engine = create_filter_engine(query)
        result = engine.filter_queryset(panden_model.objects.all())
        assert result.count() == expect, result

    @staticmethod
    @pytest.mark.parametrize(
        "query,expect",
        [
            ("", 1),
            ("buurt=03630000000078", 1),  # loose relation field
            ("buurt.identificatie=03630000000078", 1),  # same
            ("buurt.naam=AAA v2", 1),  # join relation
            ("buurt.volgnummer=1", 0),  # not in current temporal slice
            ("buurt.volgnummer=2", 1),
            ("buurt.naam[like]=AAA*", 1),  # join relation and skip old objects.
        ],
    )
    def test_filter_loose_relation(
        api_client, statistieken_model, statistieken_data, query, expect
    ):
        """Test that filtering on loose relations works.
        This also checks whether the temporal records only return a single item.
        """
        engine = create_filter_engine(query)
        result = engine.filter_queryset(statistieken_model.objects.all())
        assert result.count() == expect, result

    @staticmethod
    @pytest.mark.parametrize(
        "query",
        [
            "nonexistant",
            "buurt.nonexistant=test",
            "buurt.identificatie.nonexistant=test",
            "buurt.naam.nonexistant=test",
        ],
    )
    def test_filter_loose_relation_invalid(
        api_client, statistieken_model, statistieken_data, query
    ):
        """Prove that field-resolving on invalid fields is properly handled."""
        engine = create_filter_engine(query)
        with pytest.raises(ValidationError):
            engine.filter_queryset(statistieken_model.objects.all())

    @staticmethod
    @pytest.mark.parametrize(
        "query,expect",
        [
            ("buurt.ligtInWijk.ligtInStadsdeel=03630000000018.1", 1),
            ("buurt.ligtInWijk.ligtInStadsdeel.identificatie=03630000000018", 1),
            ("buurt.ligtInWijk.ligtInStadsdeel.naam=Centrum", 1),
        ],
    )
    def test_filter_loose_relation_nesting(
        api_client, statistieken_model, statistieken_data, wijken_data, query, expect
    ):
        """Test that joining over a loose relation works.
        the statistieken.buurt is a loose relation, the remaining relations are composite FK's.
        """
        engine = create_filter_engine(query)
        result = engine.filter_queryset(statistieken_model.objects.all())
        assert result.count() == expect, result

    @staticmethod
    @pytest.mark.parametrize(
        "query,expect",
        [
            ("", 1),
            ("bestaatUitBuurten.identificatie=03630000000078&bestaatUitBuurten.volgnummer=1", 1),
            ("bestaatUitBuurten.identificatie=03630000000078&bestaatUitBuurten.volgnummer=2", 1),
            ("bestaatUitBuurten=03630000000078.1", 1),  # direct query against field name
            ("bestaatUitBuurten=123", 0),
        ],
    )
    def test_filter_temporal_m2m(ggwgebieden_model, ggwgebieden_data, query, expect):
        """Test that filtering on temporal relations works.
        This checks both the dotted-notation, and the old 'compositeKeyId' FK field.
        """
        engine = create_filter_engine(query)
        result = engine.filter_queryset(ggwgebieden_model.objects.all())
        assert result.count() == expect, result

    @staticmethod
    def test_subobject_parsing(bag_dataset):
        verblijfsobjecten_schema = bag_dataset.schema.get_table_by_id("verblijfsobjecten")
        expected_fields = [
            ("heeftHoofdadres.volgnummer", "heeft_hoofdadres_volgnummer"),
            ("heeftHoofdadres.volgnummer[gt]", "heeft_hoofdadres_volgnummer"),
            ("heeftHoofdadres.volgnummer[gte]", "heeft_hoofdadres_volgnummer"),
            ("heeftHoofdadres.volgnummer[in]", "heeft_hoofdadres_volgnummer"),
            ("heeftHoofdadres.volgnummer[isnull]", "heeft_hoofdadres_volgnummer"),
            ("heeftHoofdadres.volgnummer[lt]", "heeft_hoofdadres_volgnummer"),
            ("heeftHoofdadres.volgnummer[lte]", "heeft_hoofdadres_volgnummer"),
            ("heeftHoofdadres.volgnummer[not]", "heeft_hoofdadres_volgnummer"),
            ("heeftHoofdadres.identificatie", "heeft_hoofdadres_identificatie"),
            ("heeftHoofdadres.identificatie[isempty]", "heeft_hoofdadres_identificatie"),
            ("heeftHoofdadres.identificatie[isnull]", "heeft_hoofdadres_identificatie"),
            ("heeftHoofdadres.identificatie[like]", "heeft_hoofdadres_identificatie"),
            ("heeftHoofdadres.identificatie[not]", "heeft_hoofdadres_identificatie"),
            ("ligtInBuurt.identificatie", "ligt_in_buurt_identificatie"),
            ("ligtInBuurt.identificatie[isempty]", "ligt_in_buurt_identificatie"),
            ("ligtInBuurt.identificatie[isnull]", "ligt_in_buurt_identificatie"),
            ("ligtInBuurt.identificatie[like]", "ligt_in_buurt_identificatie"),
            ("ligtInBuurt.identificatie[not]", "ligt_in_buurt_identificatie"),
            ("ligtInBuurt.volgnummer", "ligt_in_buurt_volgnummer"),
            ("ligtInBuurt.volgnummer[gt]", "ligt_in_buurt_volgnummer"),
            ("ligtInBuurt.volgnummer[gte]", "ligt_in_buurt_volgnummer"),
            ("ligtInBuurt.volgnummer[in]", "ligt_in_buurt_volgnummer"),
            ("ligtInBuurt.volgnummer[isnull]", "ligt_in_buurt_volgnummer"),
            ("ligtInBuurt.volgnummer[lt]", "ligt_in_buurt_volgnummer"),
            ("ligtInBuurt.volgnummer[lte]", "ligt_in_buurt_volgnummer"),
            ("ligtInBuurt.volgnummer[not]", "ligt_in_buurt_volgnummer"),
        ]

        scopes = UserScopes({}, [])
        for query_key, orm_path in expected_fields:
            filter_input = parser.FilterInput.from_parameter(query_key, raw_values=[])
            parts = parser._parse_filter_path(filter_input.path, verblijfsobjecten_schema, scopes)
            assert parser._to_orm_path(parts) == orm_path

    @staticmethod
    @pytest.mark.parametrize(
        "query,expect",
        [
            ("", 5),
            ("heeftHoofdadres.volgnummer=1", 2),
            ("heeftHoofdadres.identificatie=nm2", 1),
            ("ligtInBuurt.identificatie[isnull]=1", 1),
            ("ligtInBuurt.volgnummer[gte]=2", 3),
            ("ligtInBuurt.identificatie[like]=X*X", 1),
        ],
    )
    def test_subobject_filters(verblijfsobjecten_model, verblijfsobjecten_data, query, expect):
        # dotted filters are generated on the FK subobjects only
        engine = create_filter_engine(query)
        result = engine.filter_queryset(verblijfsobjecten_model.objects.all())
        assert result.count() == expect, result


@pytest.mark.parametrize(
    "value",
    [
        "0,0",
        "-1,-0.69315",
        "5,52",
        "52.1,1",
        "POINT(0 0)",
        "POINT(0.0 0.0)",
        "POINT(-1.1 -3.3)",
        "POINT(-1 2)",
        "POINT(100.0 42.0)",
    ],
)
def test_parse_point(value):
    x, y = _parse_point(value)
    assert isinstance(x, float)
    assert isinstance(y, float)
    assert math.isfinite(x)
    assert math.isfinite(y)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "a",
        "foo",
        "inf,nan",
        "0, 0",
        "0," + 314 * "1",
        "POINT",
        "POINT ",
        "POINT(x y)",
        "POINT(1.0 2.0",
        "POINT(1.0,2.0)",
        "POINT 1.0 2.0",
        "POINT(1. .1)",
    ],
)
def test_parse_point_invalid(value):
    with pytest.raises(ValidationError):
        _parse_point(value)


@pytest.mark.parametrize(
    "value",
    [
        # Basic invalid formats
        "",
        "a",
        "foo",
        "inf,nan",
        "0, 0",
        "0," + 314 * "1",
        # Invalid WKT formats
        "POINT",
        "POINT ",
        "POINT(x y)",
        "POINT(1.0 2.0",
        "POINT(1.0,2.0)",
        "POINT 1.0 2.0",
        "POINT(1. .1)",
        # Out of bounds points
        "POINT(0 0)",
        "POINT(0.0 0.0)",
        "POINT(-1.1 -3.3)",
        "POINT(-1 2)",
        "POINT(100.0 42.0)",
        # Invalid GeoJSON
        '{"type": "Point"}',
        '{"coordinates": [1,2]}',
        '{"type": "Invalid", "coordinates": [1,2]}',
    ],
)
def test_str2geo_invalid(value):
    """Test str2geo with invalid input formats."""
    with pytest.raises(ValidationError):
        str2geo(value)


@pytest.mark.parametrize(
    "value,expected_type",
    [
        # WKT formats with valid Netherlands coordinates (Amsterdam area)
        ("POINT(4.9 52.4)", "Point"),  # WGS84
        ("POLYGON((4.9 52.4, 4.9 52.5, 5.0 52.5, 5.0 52.4, 4.9 52.4))", "Polygon"),
        ("MULTIPOLYGON(((4.9 52.4, 4.9 52.5, 5.0 52.5, 5.0 52.4, 4.9 52.4)))", "MultiPolygon"),
        # GeoJSON formats with valid Netherlands coordinates (Amsterdam area)
        ('{"type": "Point", "coordinates": [4.9, 52.4]}', "Point"),  # WGS84
        (
            '{"type": "Polygon", "coordinates": [[[4.9, 52.4], [4.9, 52.5], [5.0, 52.5], [5.0, 52.4], [4.9, 52.4]]]}',  # noqa: E501
            "Polygon",
        ),
        (
            '{"type": "MultiPolygon", "coordinates": [[[[4.9, 52.4], [4.9, 52.5], [5.0, 52.5], [5.0, 52.4], [4.9, 52.4]]]]}',  # noqa: E501
            "MultiPolygon",
        ),
    ],
)
def test_str2geo_valid_formats(value, expected_type):
    """Test str2geo with valid WKT and GeoJSON formats for Point, Polygon and MultiPolygon."""
    result = str2geo(value)
    assert result.geom_type == expected_type
    assert result.srid == 4326  # Default SRID


@pytest.mark.parametrize(
    "x,y,srid,out",
    [
        (1, 400000, 28992, (1, 400000, 28992)),  # explicit RD coordinates
        (1, 400000, None, (1, 400000, 28992)),  # implicit RD coordinates
        (5, 52, None, (5, 52, 4326)),  # implicit SRID 4326
        (52, 5, None, (5, 52, 4326)),  # lat/lon may be swapped
        # unknown SRID always passed through
        (0, 1, 1234, (0, 1, 1234)),
        (-1, -2, -3, (-1, -2, -3)),
        (1, 400000, 999, (1, 400000, 999)),
    ],
)
def test_validate_convert_x_y(x, y, srid, out):
    point = _validate_correct_x_y(x, y, srid)
    assert point.x == out[0]
    assert point.y == out[1]
    assert point.srid == out[2]


@pytest.mark.parametrize(
    "x,y,srid,out",
    [
        (1, 1, None, (None, None, None)),  # SRID cannot be determined
        # known SRID but invalid coordinates becomes (None, None, srid)
        (1, 400000, 4326, (None, None, 4326)),
        (0, 52, 4326, (None, None, 4326)),
        (1, 4, 28992, (None, None, 28992)),
    ],
)
def test_validate_convert_x_y_exception(x, y, srid, out):
    with pytest.raises(ValueError) as exc_info:
        _validate_correct_x_y(x, y, srid)

    assert "Invalid x,y values" in str(exc_info.value)
