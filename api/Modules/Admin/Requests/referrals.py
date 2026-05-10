"""Admin referrals schemas."""
from pydantic import BaseModel, ConfigDict


class ReferralRedemptionRow(BaseModel):
    """One redemption row in the History table on the referrals page."""

    model_config = ConfigDict(extra="forbid")

    redeemed_at:               str
    referee_store_id:          int
    self_credit_applied:       bool
    referee_credit_applied:    bool
    stripe_self_txn_id:        str


class ReferralCodeResponse(BaseModel):
    """Self-service referral page payload. `share_url` is the full
    /signup?ref=<code> URL on the canonical host (built server-side
    so the SPA doesn't have to know the host)."""

    model_config = ConfigDict(extra="forbid")

    code:                  str
    is_active:             bool
    reward_self_cents:     int
    reward_referee_cents:  int
    redeemed_count:        int
    credits_earned_cents:  int
    share_url:             str
    redemptions:           list[ReferralRedemptionRow]
