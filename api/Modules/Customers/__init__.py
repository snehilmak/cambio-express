"""Customers module — second vertical slice in the Flask → FastAPI
strangler-fig migration.

Owns the per-store customer directory used by the transfer form's
autofill + dedupe UX, plus the `/api/customers/search` autocomplete
endpoint. Scope is the **owner umbrella** — sibling stores under the
same `Owner` share a unified customer list (see CLAUDE.md invariant
#5: "Customer upsert (owner umbrella scope)").

Layer rules from the ADR:
    Controllers → Services → Repositories → Models
"""
