"""Billing module — sub-component of the Auth/Billing migration order.

Owns the Stripe Checkout + billing-portal + subscription-state
flows. Per ADR migration order, the Auth + Billing module ships
together; this directory holds the Billing-specific Services so
the Auth surface stays focused on identity.

Layer rules (ADR):
    Controller → Service → Repository → Model
"""
