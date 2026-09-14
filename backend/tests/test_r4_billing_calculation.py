from decimal import Decimal

from app.services.billing import round_half_up_to_unit, split_largest_remainder


def test_r4_money_oracles_are_integer_vnd_and_round_once_half_up():
    assert round_half_up_to_unit(Decimal("80.25") * Decimal("12000"), 1) == 963000
    assert round_half_up_to_unit(Decimal("82.58") * Decimal("12000"), 1000) == 991000


def test_r4_largest_remainder_oracle_preserves_every_vnd_deterministically():
    assert split_largest_remainder(1_000_000, [
        ("account-a", Decimal("0.3333333333333333333333333333")),
        ("account-b", Decimal("0.3333333333333333333333333333")),
        ("account-c", Decimal("0.3333333333333333333333333334")),
    ]) == [333333, 333333, 333334]
    assert split_largest_remainder(1_000_000, [
        ("account-a", Decimal(1) / Decimal(3)),
        ("account-b", Decimal(1) / Decimal(3)),
        ("account-c", Decimal(1) / Decimal(3)),
    ]) == [333334, 333333, 333333]
