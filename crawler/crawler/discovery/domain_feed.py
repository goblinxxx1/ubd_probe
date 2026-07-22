"""DDG-independent candidate emitter: re-surfaces top-rated productive domains as website
SourceCandidates each pass, exactly like BrandFeed but sourced from the DomainRegistry."""

from crawler.models import SourceCandidate


class DomainFeed:
    def __init__(self, registry, per_pass=8):
        self._registry = registry
        self._per_pass = per_pass

    def candidates(self, known_hosts):
        out = []
        for host in self._registry.top(self._per_pass, known_hosts):
            out.append(SourceCandidate(
                name=host, type="website", url_or_handle=f"https://{host}",
                discovered_from_source_id=None,
                discovery_note=f"domain-rating:{host}"))
        return out
