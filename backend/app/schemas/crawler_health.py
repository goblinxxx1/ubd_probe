from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CrawlerHealthOut(BaseModel):
    """Latest crawler health snapshot as served to the admin panel. `snapshot` is stored
    opaquely — the crawler owns its shape; only the admin UI interprets it."""
    model_config = ConfigDict(from_attributes=True)
    snapshot: dict
    reported_at: datetime
