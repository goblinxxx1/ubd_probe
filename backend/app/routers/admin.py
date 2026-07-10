from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.crud import admin_user as admin_user_crud
from app.crud import category as category_crud
from app.crud import offer as offer_crud
from app.crud import source as source_crud
from app.crud import suggested_source as suggestion_crud
from app.deps import get_current_admin, get_db, require_super_admin
from app.models import OfferCategory, TargetCategory
from app.models.enums import CreatedBy, OfferStatus, OfferType, SuggestionStatus
from app.schemas.admin_user import AdminUserCreate, AdminUserOut
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate
from app.schemas.common import Page
from app.schemas.offer import OfferCreate, OfferOut, OfferUpdate
from app.schemas.source import SourceCreate, SourceOut, SourceUpdate
from app.schemas.suggested_source import SuggestedSourceOut

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


@router.get("/offers", response_model=Page[OfferOut])
def list_offers(status: OfferStatus | None = None, type: OfferType | None = None,
                q: str | None = None,
                page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                db: Session = Depends(get_db), _=Depends(get_current_admin)):
    items, total = offer_crud.list_offers(db, status=status, type=type, search=q, page=page, size=size)
    return Page(items=items, total=total, page=page, size=size)


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
    return offer_crud.set_status(db, offer_id, OfferStatus.published, admin.id)


@router.post("/offers/{offer_id}/reject", response_model=OfferOut)
def reject_offer(offer_id: int, db: Session = Depends(get_db),
                 admin=Depends(get_current_admin)):
    return offer_crud.set_status(db, offer_id, OfferStatus.rejected, admin.id)


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
