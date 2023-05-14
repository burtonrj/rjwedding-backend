import asyncio
import logging

import docker
import pytest
from decouple import config
from httpx import AsyncClient
from odmantic import SyncEngine
from pymongo import MongoClient

from src.app import app
from src.data import WeddingGuestGroup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
def event_loop():
    return asyncio.get_event_loop()


@pytest.fixture(scope="session")
async def client():
    async with AsyncClient(app=app, base_url="http://test") as client:
        logger.info("Async client is ready")
        yield client


def mongodb_testdb_container_check() -> bool:
    for container in docker.from_env().containers.list():
        if container.name == "rjwedding-mongodb":
            return True
    return False


def clear_db(sync_engine: SyncEngine):
    sync_engine.remove(WeddingGuestGroup)
    assert len(list(sync_engine.find(WeddingGuestGroup))) == 0


@pytest.fixture
def db_manager():
    if not mongodb_testdb_container_check():
        raise ValueError("No mongodb test container found")
    client = MongoClient(config("MONGO_URI", default="mongodb://localhost:27017/"))
    sync_engine = SyncEngine(client=client, database="test")
    clear_db(sync_engine)
    # Add 2 test WeddingGuestGroup documents
    test_grp1 = WeddingGuestGroup(
        display_name="Test Group 1", count=1, wedding_party_count=0, code="test1"
    )
    test_grp2 = WeddingGuestGroup(
        display_name="Test Group 2",
        count=2,
        wedding_party_count=2,
        code="test2",
        parking_required=True,
        attendance=1,
        song_choice="Test Song",
    )
    admin = WeddingGuestGroup(
        display_name="Admin Group",
        count=2,
        wedding_party_count=2,
        code="admin",
        attendance=1,
        admin=True,
    )
    sync_engine.save(test_grp1)
    sync_engine.save(test_grp2)
    sync_engine.save(admin)
    yield
    clear_db(sync_engine)
