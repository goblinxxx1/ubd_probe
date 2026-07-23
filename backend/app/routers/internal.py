from datetime import datetime
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.crud import blocked_host as blocked_host_crud
from app.crud import bot_account as bot_account_crud
from app.crud import category as category_crud
from app.crud import crawl_state as crawl_state_crud
from app.crud import offer as offer_crud
from app.crud import source as source_crud
from app.crud import suggested_source as suggestion_crud
from app.deps import get_db, require_api_key
from app.models import OfferCategory
from app.models.enums import CreatedBy, OfferStatus
from app.schemas.blocked_host import BlockedHostOut, HostCandidateCreate
from app.schemas.bot_account import BotAccountOut, BotAccountStateUpdate
from app.schemas.category import CategoryCreate, CategoryOut
from app.schemas.crawl_state import CrawlStateOut, CrawlStateUpdate
from app.schemas.offer import OfferCreate, OfferOut
from app.schemas.source import SourceOut
from app.schemas.suggested_source import SuggestedSourceCreate, SuggestedSourceOut

router = APIRouter(prefix="/api/internal", tags=["internal"],
                   dependencies=[Depends(require_api_key)])


@router.get("/sources", response_model=list[SourceOut])
def list_sources(is_active: bool | None = True, db: Session = Depends(get_db)):
    return source_crud.list_sources(db, is_active=is_active)


class InternalOfferCreate(OfferCreate):
    source_id: int | None = None
    content_hash: str | None = None


@router.post("/offers", response_model=OfferOut)
def create_offer(data: InternalOfferCreate, db: Session = Depends(get_db)):
    if data.source_id is not None:
        source_crud.get_source(db, data.source_id)
    payload = OfferCreate(**data.model_dump(exclude={"source_id", "content_hash"}))
    return offer_crud.create_offer(db, payload, CreatedBy.crawler,
                                   OfferStatus.pending_review, source_id=data.source_id,
                                   content_hash=data.content_hash)


class ExpireStaleRequest(BaseModel):
    older_than_days: int = 30


class ExpireStaleResult(BaseModel):
    expired: int


@router.post("/offers/expire-stale", response_model=ExpireStaleResult)
def expire_stale(data: ExpireStaleRequest, db: Session = Depends(get_db)):
    return ExpireStaleResult(expired=offer_crud.expire_stale(db, data.older_than_days))


@router.post("/suggested-sources", response_model=SuggestedSourceOut)
def submit_suggested_source(data: SuggestedSourceCreate, db: Session = Depends(get_db)):
    return suggestion_crud.create_suggestion(db, data)


@router.post("/offer-categories", response_model=CategoryOut)
def create_offer_category(data: CategoryCreate, db: Session = Depends(get_db)):
    return category_crud.get_or_create_category(db, OfferCategory, data.name, data.slug)


@router.get("/sources/{source_id}/crawl-state", response_model=CrawlStateOut)
def get_crawl_state(source_id: int, db: Session = Depends(get_db)):
    state = crawl_state_crud.get_crawl_state(db, source_id)
    if state is None:
        return CrawlStateOut(last_seen_key=None, last_crawled_at=None)
    return state


@router.post("/sources/{source_id}/crawl-state", response_model=CrawlStateOut)
def set_crawl_state(source_id: int, data: CrawlStateUpdate, db: Session = Depends(get_db)):
    return crawl_state_crud.upsert_crawl_state(db, source_id, data.last_seen_key)


@router.get("/bot-accounts", response_model=list[BotAccountOut])
def list_bot_accounts(platform: str | None = None, db: Session = Depends(get_db)):
    return bot_account_crud.list_bot_accounts(db, platform=platform)


@router.post("/bot-accounts/{platform}/{username}/state", response_model=BotAccountOut)
def set_bot_account_state(platform: str, username: str, data: BotAccountStateUpdate,
                          db: Session = Depends(get_db)):
    return bot_account_crud.upsert_state(db, platform, username, data.state,
                                         cooldown_until=data.cooldown_until, note=data.note)


class ApprovedOfferOut(BaseModel):
    text: str
    host: str
    approved_at: datetime


def _host(url):
    return urlsplit(url or "").netloc.lower().removeprefix("www.")


@router.get("/approved-offers", response_model=list[ApprovedOfferOut])
def list_approved_offers(since: datetime | None = None, db: Session = Depends(get_db)):
    rows = offer_crud.list_published_since(db, since)
    return [
        ApprovedOfferOut(
            text=f"{o.title}\n{o.description or ''}".strip(),
            host=_host(o.site_url or o.article_url),
            approved_at=o.updated_at,
        )
        for o in rows
    ]


@router.post("/host-candidates", response_model=BlockedHostOut)
def submit_host_candidate(data: HostCandidateCreate, db: Session = Depends(get_db)):
    return blocked_host_crud.upsert_candidate(db, data)


@router.get("/blocked-hosts", response_model=list[str])
def list_blocked_hosts(db: Session = Depends(get_db)):
    return blocked_host_crud.list_approved_hosts(db)
