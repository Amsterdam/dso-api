from rest_framework_dso.paginator import DSOPaginator


class TestDSOPaginator:
    def test_get_page(self):
        paginator = DSOPaginator(range(50), per_page=10)
        page = paginator.get_page(2)
        assert str(page) == "<Page 2>"
        assert len(list(page.object_list)) == 10

    def test_get_page_non_integer(self):
        paginator = DSOPaginator(range(50), per_page=10)
        page = paginator.get_page(3.14)
        assert str(page) == "<Page 1>"
        assert len(list(page.object_list)) == 10
