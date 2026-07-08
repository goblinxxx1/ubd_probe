from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.crud import category as category_crud
from app.crud import source as source_crud
from app.deps import get_current_admin, get_db, require_super_admin
from app.models import OfferCategory, TargetCategory
from app.models.enums import CreatedBy
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate
from app.schemas.source import SourceCreate, SourceOut, SourceUpdate

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
