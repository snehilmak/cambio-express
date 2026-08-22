"""api.Core.Money — the dollars↔cents conversion contract (P0-3)."""
import pytest

from api.Core.Money import to_cents, to_dollars


class TestToCents:
    def test_exact_dollars(self):
        assert to_cents(12.34) == 1234
        assert to_cents(0.01) == 1
        assert to_cents(1000000) == 100000000

    def test_half_up_rounding(self):
        # Cash-register rounding, not bankers'.
        assert to_cents(2.675) == 268
        assert to_cents(2.665) == 267  # float 2.665 reads as 2.665 via str()
        assert to_cents("2.675") == 268
        assert to_cents("2.685") == 269

    def test_float_artifacts(self):
        # 0.1 + 0.2 = 0.30000000000000004 must still land on 30.
        assert to_cents(0.1 + 0.2) == 30
        # The classic sub-cent drift from float dollar sums.
        assert to_cents(19.99 * 3) == 5997

    def test_none_and_empty(self):
        assert to_cents(None) == 0
        assert to_cents("") == 0
        assert to_cents(0) == 0

    def test_negative(self):
        assert to_cents(-5.25) == -525

    def test_rejects_garbage(self):
        with pytest.raises(ValueError):
            to_cents("not money")


class TestToDollars:
    def test_roundtrip(self):
        for cents in (0, 1, 99, 100, 1234, 999_999_999):
            assert to_cents(to_dollars(cents)) == cents

    def test_none(self):
        assert to_dollars(None) == 0.0

    def test_negative(self):
        assert to_dollars(-525) == -5.25
