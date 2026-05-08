"""TV Display — Pydantic request/response schemas.

Read-only first pass: list the per-store TV display config + its
country sections (with bank/rate counts) so the SPA can render the
admin landing. Write-side (mint/edit countries, rates, pairings)
stays on the legacy Flask routes for now."""
from pydantic import BaseModel, ConfigDict


class TVDisplayCountryStat(BaseModel):
    """One country section as it appears on the admin landing.
    `mt_companies` is the CSV column header list — stays a single
    string so the SPA can preserve column order without normalizing."""
    model_config = ConfigDict(extra="forbid")

    id: int
    country_code: str
    country_name: str
    sort_order: int
    mt_companies: str
    bank_count: int
    rate_count: int


class TVPairingSummary(BaseModel):
    """Currently-active Fire TV pairing (newest unrevoked). The
    landing page shows a "Currently paired" pill when present."""
    model_config = ConfigDict(extra="forbid")

    id: int
    device_label: str
    paired_at: str
    last_seen_at: str


class TVDisplayOverviewResponse(BaseModel):
    """Everything the SPA admin landing needs in one envelope.
    `public_url` is the absolute /tv/<token> URL the operator hands
    to a tablet/Chromecast; the SPA renders it as a copy-to-clipboard
    target. `active_pairing` is None when no Fire TV is paired."""
    model_config = ConfigDict(extra="forbid")

    display_id: int
    title: str
    subtitle: str
    orientation: str
    theme: str
    public_token: str
    public_url: str
    last_updated_at: str
    countries: list[TVDisplayCountryStat]
    active_pairing: TVPairingSummary | None


class TVDisplayBankRow(BaseModel):
    """One bank within a country, with its filled-in rate cells.
    `rates` is a sparse map keyed by mt_company; absent entries are
    rendered as "—" on the public board."""
    model_config = ConfigDict(extra="forbid")

    id: int
    bank_name: str
    sort_order: int
    rates: dict[str, float]


class TVDisplayCountryDetailResponse(BaseModel):
    """Full drill-down for one country: header config + bank matrix.
    `mt_companies` is the column-header list (already split for the
    SPA), preserving order; `banks` carries one TVDisplayBankRow per
    payout bank, each with their filled-in rate cells."""
    model_config = ConfigDict(extra="forbid")

    id: int
    country_code: str
    country_name: str
    sort_order: int
    mt_companies: list[str]
    banks: list[TVDisplayBankRow]


__all__ = [
    "TVDisplayBankRow",
    "TVDisplayCountryDetailResponse",
    "TVDisplayCountryStat",
    "TVDisplayOverviewResponse",
    "TVPairingSummary",
]
