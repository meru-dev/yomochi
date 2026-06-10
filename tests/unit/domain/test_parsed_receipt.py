from decimal import Decimal

from app.domain.value_objects.parsed_receipt import ParsedReceiptDraft


def test_notes_formatted_from_line_items():
    draft = ParsedReceiptDraft(
        merchant="AEON",
        amount=Decimal("1498"),
        currency="JPY",
        date_str="2026-05-29",
        suggested_category_code="groceries",
        line_items=(
            {"name": "Rice 5kg", "price": "1200"},
            {"name": "Eggs 10pk", "price": "298"},
        ),
    )
    assert draft.notes is not None
    assert "Rice 5kg" in draft.notes
    assert "1200" in draft.notes
    assert "Eggs 10pk" in draft.notes
    assert "298" in draft.notes


def test_notes_none_when_no_line_items():
    draft = ParsedReceiptDraft(
        merchant="AEON",
        amount=Decimal("1498"),
        currency="JPY",
        date_str="2026-05-29",
        suggested_category_code=None,
    )
    assert draft.notes is None
