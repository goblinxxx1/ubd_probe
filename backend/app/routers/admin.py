from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.crud import category as category_crud
from app.deps import get_db, require_super_admin
from app.models import OfferCategory, TargetCategory
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate

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
