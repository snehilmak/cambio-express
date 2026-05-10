"""TV Display — Pydantic request/response schemas.

Covers the SPA admin landing: read overview + per-country drill-down,
plus the write actions the landing page exposes (settings save, token
rotation, Fire TV claim/revoke, country create/delete). The country
editor's bank/rate matrix POST stays on legacy Flask until the next
migration slice."""
from pydantic import BaseModel, ConfigDict, Field


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


class TVDisplaySettingsUpdateRequest(BaseModel):
    """Settings the admin landing page can save in one form: title,
    optional subtitle, orientation (auto/landscape/portrait), board
    theme (light/dark). Mirrors the legacy form contract — same
    server-side defaults + bounded length truncation."""
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="", max_length=120)
    subtitle: str = Field(default="", max_length=120)
    orientation: str = Field(default="auto")
    theme: str = Field(default="light")


class TVDisplayRegenerateTokenResponse(BaseModel):
    """Result of rotating the public_token. The SPA refreshes its
    overview state from this, since the URL the operator has to hand
    out changed."""
    model_config = ConfigDict(extra="forbid")

    public_token: str
    public_url: str


class TVDisplayClaimRequest(BaseModel):
    """The 6-char code the operator typed in from a Fire TV showing
    the pairing screen. Server normalises (strips non-alnum, uppercases)
    before lookup; client may send it raw."""
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=20)


class TVDisplayCountryCreateRequest(BaseModel):
    """Add a new country section. Country picker on the landing page
    submits the ISO-2 plus the human-readable name; mt_companies is
    optional (can be filled in later from the country editor)."""
    model_config = ConfigDict(extra="forbid")

    country_name: str = Field(min_length=1, max_length=80)
    country_code: str = Field(default="", max_length=4)
    mt_companies: str = Field(default="", max_length=500)


class TVDisplayCountryCreateResponse(BaseModel):
    """The new country row — caller redirects into the editor for
    that country_id to fill in banks + rates."""
    model_config = ConfigDict(extra="forbid")

    id: int
    country_name: str
    country_code: str


__all__ = [
    "TVDisplayBankRow",
    "TVDisplayClaimRequest",
    "TVDisplayCountryCreateRequest",
    "TVDisplayCountryCreateResponse",
    "TVDisplayCountryDetailResponse",
    "TVDisplayCountryStat",
    "TVDisplayOverviewResponse",
    "TVDisplayRegenerateTokenResponse",
    "TVDisplaySettingsUpdateRequest",
    "TVPairingSummary",
]
