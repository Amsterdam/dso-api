from rest_framework_dso.embedding import ObservableIterator


class TestObservableIterator:
    def test_final_outcome(self):
        """Prove that the final outcome is as desired"""
        seen1 = []
        seen2 = []

        observer = ObservableIterator("abcd", observers=[seen1.append, seen2.append])
        assert list(observer) == ["a", "b", "c", "d"]

        assert seen1 == ["a", "b", "c", "d"]
        assert seen1 == seen2
        assert bool(observer)

    def test_streaming(self):
        """Prove that results are collected during iterations"""
        seen1 = []
        seen2 = []

        observer = ObservableIterator("abcd", observers=[seen1.append, seen2.append])
        assert bool(observer)  # Prove that inspecting first doesn't break

        assert next(observer) == "a"
        assert seen1 == ["a"]
        assert seen1 == seen2
        assert bool(observer)

        assert next(observer) == "b"
        assert seen1 == ["a", "b"]
        assert seen1 == seen2
        assert bool(observer)

        # Consume the rest
        assert list(observer) == ["c", "d"]
        assert seen1 == ["a", "b", "c", "d"]
        assert seen1 == seen2
        assert bool(observer)
