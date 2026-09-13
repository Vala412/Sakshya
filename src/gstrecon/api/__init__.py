"""HTTP layer over the deterministic reconciliation engine.

Deliberately contains no matching, classification, or bridge arithmetic of
its own: every number this package serves is read off `exceptions.py` /
`report.py` output and re-shaped for transport. If a figure can be computed
here and also in the engine, it belongs in the engine -- a second
implementation is a second thing that can disagree with the working paper,
and the working paper is the audit deliverable.
"""
