from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import BotAccount
from app.models.enums import BotAccountState


def list_bot_accounts(db: Session, platform: str | None = None) -> list[BotAccount]:
    q = db.query(BotAccount)
    if platform is not None:
        q = q.filter(BotAccount.platform == platform)
    return q.order_by(BotAccount.platform, BotAccount.username).all()


def upsert_state(db: Session, platform: str, username: str, state: BotAccountState,
                 cooldown_until: datetime | None = None, note: str | None = None) -> BotAccount:
    obj = (db.query(BotAccount)
           .filter(BotAccount.platform == platform, BotAccount.username == username)
           .first())
    if obj is None:
        obj = BotAccount(platform=platform, username=username)
        db.add(obj)
    obj.state = state
    obj.cooldown_until = cooldown_until
    obj.note = note
    obj.last_used_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(obj)
    return obj
