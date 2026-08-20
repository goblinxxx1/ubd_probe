from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.crud import admin_user as admin_user_crud
from app.crud import blocked_host as blocked_host_crud
from app.crud import query_term as query_term_crud
from app.crud import category as category_crud
from app.crud import offer as offer_crud
from app.crud import source as source_crud
from app.crud import suggested_source as suggestion_crud
from app.core.errors import validation_error
from app.deps import get_current_admin, get_db, require_super_admin
from app.models import OfferCategory, TargetCategory
from app.models.enums import (BlockedHostStatus, CreatedBy, OfferStatus, OfferType,
                               QueryTermStatus, SuggestionStatus)
from app.schemas.admin_user import AdminUserCreate, AdminUserOut
from app.schemas.blocked_host import BlockedHostCreate, BlockedHostOut
from app.schemas.query_term import QueryTermOut
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate
from app.schemas.common import Page
from app.schemas.offer import OfferAdminOut, OfferCreate, OfferOut, OfferUpdate
from app.schemas.source import SourceCreate, SourceOut, SourceUpdate
from app.schemas.suggested_source import SuggestedSourceOut
from app.services import promotion

router = APIRouter(prefix="/api/admin", tags=["admin"])

_CATEGORY_MODELS = {"target-categories": TargetCategory, "offer-categories": OfferCategory}


def _make_category_routes(path: str, model):
    @router.post(f"/{path}", response_model=CategoryOut, name=f"create_{path}")
    def create(data: CategoryCreate, db: Session = Depends(get_db),
               _=Depends(require_super_admin), model=model):
        return category_crud.create_category(db, model, data)

    @router.patch(f"/{path}/{{category_id}}", response_model=CategoryOut, name=f"update_{path}")
    def update(category_id: int, data: CategoryUpdate, db: Session = Depends(get_db),
               _=Depends(require_super_admin), model=model):
        return category_crud.update_category(db, model, category_id, data)

    @router.delete(f"/{path}/{{category_id}}", status_code=204, name=f"delete_{path}")
    def delete(category_id: int, db: Session = Depends(get_db),
               _=Depends(require_super_admin), model=model):
        category_crud.delete_category(db, model, category_id)


for _path, _model in _CATEGORY_MODELS.items():
    _make_category_routes(_path, _model)


@router.post("/sources", response_model=SourceOut)
def create_source(data: SourceCreate, db: Session = Depends(get_db),
                  _=Depends(get_current_admin)):
    return source_crud.create_source(db, data, CreatedBy.admin)


@router.get("/sources", response_model=list[SourceOut])
def list_sources(db: Session = Depends(get_db), _=Depends(get_current_admin)):
    return source_crud.list_sources(db)


@router.patch("/sources/{source_id}", response_model=SourceOut)
def update_source(source_id: int, data: SourceUpdate, db: Session = Depends(get_db),
                  _=Depends(get_current_admin)):
    return source_crud.update_source(db, source_id, data)


@router.delete("/sources/{source_id}", status_code=204)
def delete_source(source_id: int, db: Session = Depends(get_db),
                  _=Depends(get_current_admin)):
    source_crud.delete_source(db, source_id)


@router.post("/offers", response_model=OfferOut)
def create_offer(data: OfferCreate, db: Session = Depends(get_db),
                 _=Depends(get_current_admin)):
    return offer_crud.create_offer(db, data, CreatedBy.admin, OfferStatus.published)


@router.get("/offers", response_model=Page[OfferAdminOut])
def list_offers(status: OfferStatus | None = None, type: OfferType | None = None,
                q: str | None = None,
                page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                db: Session = Depends(get_db), _=Depends(get_current_admin)):
    items, total = offer_crud.list_offers(db, status=status, types=[type] if type else None,
                                          search=q, page=page, size=size)
    if status == OfferStatus.pending_review:
        from app.services.confidence import enrich_pending
        enrich_pending(db, items)   # moderation-queue assist (advisory only)
    return Page(items=items, total=total, page=page, size=size)


class BulkRejectIn(BaseModel):
    ids: list[int] = Field(min_length=1)


class BulkRejectFail(BaseModel):
    id: int
    error: str


class BulkRejectOut(BaseModel):
    rejected: list[int] = []
    failed: list[BulkRejectFail] = []


@router.post("/offers/bulk-reject", response_model=BulkRejectOut)
def bulk_reject_offers(data: BulkRejectIn, db: Session = Depends(get_db),
                       admin=Depends(get_current_admin)):
    """Bulk soft-reject (reversible, #12). No bulk publish — that stays single + confirmed."""
    rejected, failed = [], []
    for oid in data.ids:
        try:
            offer_crud.set_status(db, oid, OfferStatus.rejected, admin.id)
            rejected.append(oid)
        except Exception as exc:  # noqa: BLE001 — isolate per id, report the rest
            failed.append(BulkRejectFail(id=oid, error=str(getattr(exc, "detail", exc))))
    return BulkRejectOut(rejected=rejected, failed=failed)


@router.get("/offers/{offer_id}", response_model=OfferOut)
def get_offer(offer_id: int, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    return offer_crud.get_offer(db, offer_id)


@router.patch("/offers/{offer_id}", response_model=OfferOut)
def update_offer(offer_id: int, data: OfferUpdate, db: Session = Depends(get_db),
                 _=Depends(get_current_admin)):
    return offer_crud.update_offer(db, offer_id, data)


@router.post("/offers/{offer_id}/publish", response_model=OfferOut)
def publish_offer(offer_id: int, db: Session = Depends(get_db),
                  admin=Depends(get_current_admin)):
    offer = offer_crud.set_status(db, offer_id, OfferStatus.published, admin.id)
    promotion.maybe_promote_on_publish(db, offer)
    return offer


@router.post("/offers/{offer_id}/reject", response_model=OfferOut)
def reject_offer(offer_id: int, db: Session = Depends(get_db),
                 admin=Depends(get_current_admin)):
    return offer_crud.set_status(db, offer_id, OfferStatus.rejected, admin.id)


@router.post("/offers/{offer_id}/restore", response_model=OfferOut)
def restore_offer(offer_id: int, db: Session = Depends(get_db),
                  admin=Depends(get_current_admin)):
    offer = offer_crud.get_offer(db, offer_id)
    if offer.status != OfferStatus.rejected:
        raise validation_error("Відновити можна лише відхилений оффер")
    return offer_crud.set_status(db, offer_id, OfferStatus.pending_review, admin.id)


@router.post("/offers/{offer_id}/block-host", response_model=BlockedHostOut)
def block_offer_host(offer_id: int, db: Session = Depends(get_db),
                     admin=Depends(get_current_admin)):
    offer = offer_crud.get_offer(db, offer_id)
    host_src = offer.site_url or next(
        (link.site_url for link in offer.links if link.site_url), None)
    # add_manual сам bare-host'ить URL і кидає validation_error на порожньому -> 422.
    return blocked_host_crud.add_manual(db, host_src or "", admin.id)


@router.delete("/offers/{offer_id}", status_code=204)
def delete_offer(offer_id: int, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    offer_crud.delete_offer(db, offer_id)


@router.get("/suggested-sources", response_model=list[SuggestedSourceOut])
def list_suggestions(status: SuggestionStatus | None = None, db: Session = Depends(get_db),
                     _=Depends(get_current_admin)):
    return suggestion_crud.list_suggestions(db, status)


@router.post("/suggested-sources/{suggestion_id}/approve", response_model=SourceOut)
def approve_suggestion(suggestion_id: int, db: Session = Depends(get_db),
                       admin=Depends(get_current_admin)):
    return suggestion_crud.approve(db, suggestion_id, admin.id)


@router.post("/suggested-sources/{suggestion_id}/reject", response_model=SuggestedSourceOut)
def reject_suggestion(suggestion_id: int, db: Session = Depends(get_db),
                      admin=Depends(get_current_admin)):
    return suggestion_crud.reject(db, suggestion_id, admin.id)


@router.get("/host-candidates", response_model=list[BlockedHostOut])
def list_host_candidates(status: BlockedHostStatus | None = None,
                         db: Session = Depends(get_db), _=Depends(get_current_admin)):
    return blocked_host_crud.list_hosts(db, status)


@router.post("/host-candidates", response_model=BlockedHostOut)
def add_blocked_host(data: BlockedHostCreate, db: Session = Depends(get_db),
                     admin=Depends(get_current_admin)):
    return blocked_host_crud.add_manual(db, data.host, admin.id)


@router.post("/host-candidates/{host_id}/approve", response_model=BlockedHostOut)
def approve_host_candidate(host_id: int, db: Session = Depends(get_db),
                           admin=Depends(get_current_admin)):
    return blocked_host_crud.approve(db, host_id, admin.id)


@router.post("/host-candidates/{host_id}/reject", response_model=BlockedHostOut)
def reject_host_candidate(host_id: int, db: Session = Depends(get_db),
                          admin=Depends(get_current_admin)):
    return blocked_host_crud.reject(db, host_id, admin.id)


@router.get("/query-terms", response_model=list[QueryTermOut])
def list_query_terms(status: QueryTermStatus | None = None,
                     db: Session = Depends(get_db), _=Depends(get_current_admin)):
    return query_term_crud.list_terms(db, status)


@router.post("/query-terms/{term_id}/approve", response_model=QueryTermOut)
def approve_query_term(term_id: int, db: Session = Depends(get_db),
                       admin=Depends(get_current_admin)):
    return query_term_crud.approve(db, term_id, admin.id)


@router.post("/query-terms/{term_id}/reject", response_model=QueryTermOut)
def reject_query_term(term_id: int, db: Session = Depends(get_db),
                      admin=Depends(get_current_admin)):
    return query_term_crud.reject(db, term_id, admin.id)


@router.post("/query-terms/{term_id}/unreject", response_model=QueryTermOut)
def unreject_query_term(term_id: int, db: Session = Depends(get_db),
                        admin=Depends(get_current_admin)):
    return query_term_crud.to_pending(db, term_id)


@router.post("/users", response_model=AdminUserOut)
def create_admin_user(data: AdminUserCreate, db: Session = Depends(get_db),
                      _=Depends(require_super_admin)):
    return admin_user_crud.create_admin(db, data)


@router.get("/users", response_model=list[AdminUserOut])
def list_admin_users(db: Session = Depends(get_db), _=Depends(require_super_admin)):
    return admin_user_crud.list_admins(db)


@router.delete("/users/{admin_id}", status_code=204)
def delete_admin_user(admin_id: int, db: Session = Depends(get_db),
                      _=Depends(require_super_admin)):
    admin_user_crud.delete_admin(db, admin_id)
