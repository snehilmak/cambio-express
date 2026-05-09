"""Tax Export schemas."""
from pydantic import BaseModel, ConfigDict


class TaxExportYearsResponse(BaseModel):
    """Years offered in the tax-pack year picker. `years` is sorted
    newest-first; `default_year` is the year the SPA pre-selects
    (typically last calendar year — operators usually do taxes in
    February for the year that just ended)."""

    model_config = ConfigDict(extra="forbid")

    years:        list[int]
    default_year: int
