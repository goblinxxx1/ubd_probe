import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.db import Base, get_db
import app.models  # noqa: F401 — ensures all models are registered on Base
from app.main import app

_engine = create_engine(settings.test_database_url, pool_pre_ping=True)


@pytest.fixture
def db_session():
    # Clean slate (in case a previous crashed run left tables behind), then fresh schema.
    Base.metadata.drop_all(bind=_engine)
    Base.metadata.create_all(bind=_engine)
    TestingSessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
