import pytest

from app.close.workbook import DEFAULT_ITEMS, CloseStore


class TestCloseWorkbook:
    def test_create_default(self, tmp_path):
        store = CloseStore(tmp_path)
        wb = store.load_or_create("2026-04")
        assert len(wb.items) == len(DEFAULT_ITEMS)
        assert wb.done_count == 0

    def test_mark_done_and_reopen(self, tmp_path):
        store = CloseStore(tmp_path)
        store.load_or_create("2026-04")
        wb = store.set_item("2026-04", "bank-recon", True, actor="Sanjay", note="BRS b7a2")
        item = next(i for i in wb.items if i.key == "bank-recon")
        assert item.done and item.done_by == "Sanjay" and item.note == "BRS b7a2"
        wb = store.set_item("2026-04", "bank-recon", False, actor="")
        item = next(i for i in wb.items if i.key == "bank-recon")
        assert not item.done and item.done_by == ""

    def test_invalid_period_rejected(self, tmp_path):
        store = CloseStore(tmp_path)
        with pytest.raises(ValueError):
            store.load_or_create("April 2026")

    def test_unknown_key(self, tmp_path):
        store = CloseStore(tmp_path)
        store.load_or_create("2026-04")
        with pytest.raises(KeyError):
            store.set_item("2026-04", "nope", True, actor="x")

    def test_periods_listed(self, tmp_path):
        store = CloseStore(tmp_path)
        store.load_or_create("2026-03")
        store.load_or_create("2026-04")
        assert store.list_periods() == ["2026-04", "2026-03"]
