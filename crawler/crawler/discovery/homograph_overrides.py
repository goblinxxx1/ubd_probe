"""Manual veto tuning for the gazetteer generator.

- FORCE_MARKER: canonical names whose EVERY surface form must be marker-only
  (matched only after м./с./смт/місто), regardless of the automatic word check.
- FORCE_PERMISSIVE: (canonical, form) pairs kept permissive despite the automatic
  homograph veto — e.g. whitelisting an oblast-centre nominative.
Both start conservative; tune after eyeballing the generated output.
"""

FORCE_MARKER: set[str] = set()
FORCE_PERMISSIVE: set[tuple[str, str]] = set()
