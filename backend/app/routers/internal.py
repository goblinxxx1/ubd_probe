from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.crud import bot_account as bot_account_crud
from app.crud import crawl_state as crawl_state_crud
from app.crud import offer as offer_crud
from app.crud import source as source_crud
from app.crud import suggested_source as suggestion_crud
from app.deps import get_db, require_api_key
from app.models.enums import CreatedBy, OfferStatus
from app.schemas.bot_account import BotAccountOut, BotAccountStateUpdate
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


@router.post("/suggested-sources", response_model=SuggestedSourceOut)
def submit_suggested_source(data: SuggestedSourceCreate, db: Session = Depends(get_db)):
    return suggestion_crud.create_suggestion(db, data)


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
