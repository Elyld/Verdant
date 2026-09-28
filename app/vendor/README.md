# Vendored PyETo

The `pyeto/` package is PyETo by Mark Richards
(https://github.com/woodcrafty/PyETo), BSD 3-Clause (see
`pyeto-LICENSE.txt`). It was never published to PyPI ("pip install pyeto"
does not exist), so it is vendored here instead of added to
requirements.txt.

Only change from upstream: absolute imports (`from pyeto.x`) were rewritten
to relative imports (`from .x`) so the package imports as
`app.vendor.pyeto`. Re-vendor with the same rewrite if upstream changes.
