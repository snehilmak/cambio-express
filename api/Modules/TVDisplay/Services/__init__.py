"""TVDisplay — Services.

* :func:`build_tv_board_context` — frame the data the public rate
  board template needs into a plain dict. Pure (no Flask or
  Starlette imports) so the Flask + Starlette renderers can both
  call it; the template + framework do the actual HTML rendering.
"""
from api.Modules.TVDisplay.Services.board import build_tv_board_context

__all__ = ["build_tv_board_context"]
