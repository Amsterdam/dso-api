import pytest
from rest_framework.exceptions import ValidationError

from rest_framework_dso.fields import (
    ALLOW_ALL_FIELDS_TO_DISPLAY,
    DENY_SUB_FIELDS_TO_DISPLAY,
    FieldsToDisplay,
)


class TestFieldsToDisplay:
    """Prove whether the 'FieldsToDisplay' tool really works"""

    def test_allow_all(self):
        """Prove that having no fields to filter is handled correctly."""
        assert not FieldsToDisplay().reduced()
        assert not ALLOW_ALL_FIELDS_TO_DISPLAY.reduced()
        assert repr(FieldsToDisplay()) == "<FieldsToDisplay: allow all>"
        assert ALLOW_ALL_FIELDS_TO_DISPLAY.get_allow_list(set("abc")) == ({"a", "b", "c"}, set())

    def test_deny_all(self):
        """Prove that our singleton to deny all works"""
        assert DENY_SUB_FIELDS_TO_DISPLAY  # this is not empty
        assert list(DENY_SUB_FIELDS_TO_DISPLAY.includes) == []
        assert list(DENY_SUB_FIELDS_TO_DISPLAY.excludes) == []
        assert repr(DENY_SUB_FIELDS_TO_DISPLAY) == "<FieldsToDisplay: deny all>"
        assert DENY_SUB_FIELDS_TO_DISPLAY.get_allow_list(set("abc")) == (set(), set())

    def test_grouping(self):
        """Prove that sublevel fields are properly grouped."""
        root = FieldsToDisplay(["cat", "person.name", "person.id"])
        assert bool(root)
        assert set(root.includes) == {"cat"}
        assert set(root.children) == {"person"}

        sublevel = root.as_nested("person")
        assert set(sublevel.includes) == {"name", "id"}

    def test_grouping_only_subfields(self):
        """Prove that sublevel fields are properly grouped."""
        root = FieldsToDisplay(["person.name", "person.id"])
        assert bool(root)
        assert root.includes == set()
        assert set(root.children) == {"person"}
        assert repr(root) == "<FieldsToDisplay: allow all, children=['person']>"

    def test_grouping_invalid(self):
        with pytest.raises(ValidationError):
            FieldsToDisplay(["person.-name"])

    def test_grouping_exclusions(self):
        """Prove that sublevel fields are properly grouped."""
        root = FieldsToDisplay(["person", "person.name", "-person.pet.name", "address"])
        assert bool(root)
        assert set(root.includes) == {"address"}
        assert set(root.children) == {"person"}
        assert set(root.excludes) == set()  # -person.pet becomes an include of person.

        person = root.as_nested("person")
        assert set(person.includes) == {"name"}
        assert set(person.children) == {"pet"}
        person_name = person.as_nested("name")
        assert person_name is ALLOW_ALL_FIELDS_TO_DISPLAY  # further nesting is also allowed
        assert (
            repr(person) == "<FieldsToDisplay: prefix=person., include=['name'], children=['pet']>"
        )

        # Unmentioned nestings receive the same treatment as other fields
        assert person.as_nested("unknown") is DENY_SUB_FIELDS_TO_DISPLAY

        pet = person.as_nested("pet")
        assert set(pet.includes) == set()
        assert set(pet.excludes) == {"name"}
        assert repr(pet) == "<FieldsToDisplay: prefix=pet., exclude=['name'], children=[]>"

        pet_name = pet.as_nested("name")
        assert pet_name is DENY_SUB_FIELDS_TO_DISPLAY  # further nesting is also denied

        # Unmentioned nestings receive the same treatment as other fields
        assert pet.as_nested("food") is ALLOW_ALL_FIELDS_TO_DISPLAY

    def test_deny_mixing_inclusions_exclusions(self):
        """Prove that mixing inclusions and exclusions at the same level is denied."""
        with pytest.raises(ValidationError) as e:
            FieldsToDisplay(["person", "-address"])
        assert "not possible to combine inclusions and exclusions" in str(e)

        # This is fine, only reducing sub object:
        FieldsToDisplay(["person", "-person.address"])
        FieldsToDisplay(["person", "person.name", "-person.address.name"])

        # But mixing includes/excludes at the same level is not:
        with pytest.raises(ValidationError) as e:
            FieldsToDisplay(["person", "person.name", "-person.address"])
        assert "not possible to combine inclusions and exclusions" in str(e)

    def test_ordered_fields_works_with_unavailable_fields(self):
        ftd = FieldsToDisplay(["cat", "food", "owner"])
        fields = {
            "owner": "Tom",
            "cat": "Felix",
        }
        result = ftd.apply(fields, valid_names={"cat", "food", "owner"}, always_keep={"_links"})
        assert result == {"cat": "Felix", "owner": "Tom"}
