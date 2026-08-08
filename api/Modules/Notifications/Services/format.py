"""Shared formatting helpers for notification email bodies."""


def fmt_money_2(n: float) -> str:
    """Mirror the React editor's mono money format so email line items
    look the same in the inbox as on screen. Tolerates None / bad input
    by falling back to $0.00."""
    try:
        return "${:,.2f}".format(float(n or 0))
    except (TypeError, ValueError):
        return "$0.00"
