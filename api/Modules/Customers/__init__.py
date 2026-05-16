"""Customers module.

Owns the per-store customer directory used by the transfer form's
autofill + dedupe UX, plus the ``/api/v2/customers/search``
autocomplete endpoint. Scope is the **owner umbrella** — sibling
stores under the same ``Owner`` share a unified customer list
(see CLAUDE.md invariant #5: "Customer upsert (owner umbrella scope)").

Layer rules from the ADR:
    Controllers → Services → Repositories → Models
"""
