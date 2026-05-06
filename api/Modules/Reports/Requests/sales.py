"""Schemas for the Sales-* family of reports.

Same row shape (label + count + sums) across the four reports here:

  Sales by Company           — group by Transfer.company
  Sales by Service Type      — group by Transfer.service_type
  By Destination Country     — group by Transfer.country
  Top Recipients             — group by Transfer.recipient_name
                               (no recipient table; we group on
                               the string directly)
"""
from pydantic import BaseModel, ConfigDict

from .common import AggregatedRowBase, AggregatedTotals


class CompanyRow(AggregatedRowBase):
    company: str


class ServiceTypeRow(AggregatedRowBase):
    service_type: str


class CountryRow(AggregatedRowBase):
    country: str


class RecipientRow(AggregatedRowBase):
    recipient: str


class SalesByCompanyResponse(BaseModel):
    rows: list[CompanyRow]
    totals: AggregatedTotals
    model_config = ConfigDict(extra="forbid")


class SalesByServiceResponse(BaseModel):
    rows: list[ServiceTypeRow]
    totals: AggregatedTotals
    model_config = ConfigDict(extra="forbid")


class ByDestinationCountryResponse(BaseModel):
    rows: list[CountryRow]
    totals: AggregatedTotals
    model_config = ConfigDict(extra="forbid")


class TopRecipientsResponse(BaseModel):
    rows: list[RecipientRow]
    totals: AggregatedTotals
    model_config = ConfigDict(extra="forbid")
