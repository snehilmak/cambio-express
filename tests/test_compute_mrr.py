"""Unit tests for _compute_mrr() — the pure MRR helper (CLAUDE.md #7 audit context).

Prices as of the 2026-04-29 bump:
  Basic  $35/mo  or  $350/yr  (amortised: $29/mo, rounded)
  Pro    $45/mo  or  $420/yr  (amortised: $35/mo, rounded)

The function returns a 5-tuple:
  (basic_monthly_mrr, basic_yearly_mrr, pro_monthly_mrr, pro_yearly_mrr, total)
"""
import pytest
from app import _compute_mrr


def test_all_zeros_returns_zero_total():
    bm, by_, pm, py_, total = _compute_mrr(0, 0, 0, 0)
    assert (bm, by_, pm, py_, total) == (0, 0, 0, 0, 0)


def test_basic_monthly_only():
    bm, by_, pm, py_, total = _compute_mrr(basic_monthly=3, basic_yearly=0,
                                            pro_monthly=0, pro_yearly=0)
    assert bm == 3 * 35
    assert by_ == 0
    assert pm == 0
    assert py_ == 0
    assert total == 105


def test_basic_yearly_amortised_to_monthly():
    # 1 yearly sub: round(350 / 12) == 29
    _, by_, _, _, total = _compute_mrr(0, 1, 0, 0)
    assert by_ == round(350 / 12)
    assert total == by_


def test_pro_monthly_only():
    bm, by_, pm, py_, total = _compute_mrr(0, 0, 2, 0)
    assert pm == 2 * 45
    assert total == 90


def test_pro_yearly_amortised_to_monthly():
    # 1 yearly sub: round(420 / 12) == 35
    _, _, _, py_, total = _compute_mrr(0, 0, 0, 1)
    assert py_ == round(420 / 12)
    assert total == py_


def test_mixed_subscribers_total_is_sum_of_components():
    bm, by_, pm, py_, total = _compute_mrr(
        basic_monthly=2, basic_yearly=3,
        pro_monthly=1, pro_yearly=4,
    )
    assert total == bm + by_ + pm + py_


@pytest.mark.parametrize("bm,by_,pm,py_", [
    (1, 0, 0, 0),
    (0, 1, 0, 0),
    (0, 0, 1, 0),
    (0, 0, 0, 1),
    (10, 10, 10, 10),
])
def test_total_always_equals_component_sum(bm, by_, pm, py_):
    r_bm, r_by, r_pm, r_py, total = _compute_mrr(bm, by_, pm, py_)
    assert total == r_bm + r_by + r_pm + r_py


def test_large_subscriber_counts_scale_linearly():
    bm, _, pm, _, total = _compute_mrr(100, 0, 50, 0)
    assert bm == 100 * 35
    assert pm == 50 * 45
    assert total == bm + pm
