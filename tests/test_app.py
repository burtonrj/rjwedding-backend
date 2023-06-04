import io

import pandas as pd
import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_healthy(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy!"}


@pytest.mark.anyio
async def test_get_code(client: AsyncClient, db_manager):
    response = await client.get("/test1")
    assert response.status_code == 200
    data = response.json()
    data.pop("id")
    assert data == {
        "display_name": "Test Group 1",
        "party_count": 1,
        "ceremony_count": 0,
        "party_attendance": -1,
        "ceremony_attendance": -1,
        "plus_one": False,
        "address": None,
        "postcode": None,
        "email": None,
        "phone": None,
        "dietary_requirements": None,
        "song_choice": None,
        "admin": False,
        "code": "test1",
        "parking_required": False,
    }


@pytest.mark.anyio
async def test_get_code_404(client: AsyncClient, db_manager):
    response = await client.get("/test15")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_get_music(client: AsyncClient, db_manager):
    response = await client.get("test1/music")
    assert response.status_code == 200
    assert response.json() == [
        {"display_name": "Test Group 2", "song_choice": "Test Song"}
    ]


@pytest.mark.anyio
async def test_get_parking_availability(client: AsyncClient, db_manager):
    response = await client.get("test1/parking_count")
    assert response.status_code == 200
    assert response.json() == {"parking_count": 1}


@pytest.mark.anyio
async def test_get_parking_availability_404(client: AsyncClient, db_manager):
    response = await client.get("test15/parking_count")
    assert response.status_code == 404


@pytest.mark.anyio
@pytest.mark.parametrize("event_type", ["party", "ceremony"])
async def test_rsvp(client: AsyncClient, db_manager, event_type):
    response = await client.get("/test1")
    assert response.status_code == 200
    assert response.json()[f"{event_type}_attendance"] == -1
    response = await client.post(
        "/rsvp", json={"code": "test1", "status": 1, "event": event_type}
    )
    assert response.status_code == 200
    assert response.json()[f"{event_type}_attendance"] == 1
    response = await client.post(
        "/rsvp", json={"code": "test1", "status": 0, "event": event_type}
    )
    assert response.status_code == 200
    assert response.json()[f"{event_type}_attendance"] == 0


@pytest.mark.anyio
async def test_song_choice(client: AsyncClient, db_manager):
    response = await client.get("/test1")
    assert response.status_code == 200
    assert response.json()["song_choice"] is None
    response = await client.post(
        "/songchoice", json={"code": "test1", "song_choice": "Test Song 2"}
    )
    assert response.status_code == 200
    assert response.json()["song_choice"] == "Test Song 2"
    music = await client.get("test1/music")
    assert music.status_code == 200
    assert music.json() == [
        {"display_name": "Test Group 1", "song_choice": "Test Song 2"},
        {"display_name": "Test Group 2", "song_choice": "Test Song"},
    ]


@pytest.mark.anyio
async def test_dietary_requirements(client: AsyncClient, db_manager):
    response = await client.get("/test1")
    assert response.status_code == 200
    assert response.json()["dietary_requirements"] is None
    response = await client.post(
        "/dietary-requirements",
        json={"code": "test1", "requirements": "Test Dietary Requirements"},
    )
    assert response.status_code == 200
    assert response.json()["dietary_requirements"] == "Test Dietary Requirements"
    response = await client.get("/test1")
    assert response.status_code == 200
    assert response.json()["dietary_requirements"] == "Test Dietary Requirements"


@pytest.mark.anyio
async def test_get_attendance(client: AsyncClient, db_manager):
    response = await client.get("/admin/attendance")
    assert response.status_code == 200
    assert response.json() == {
        "party_count": 0 + 2 + 1 + 2,
        "ceremony_count": 0 + 2 + 0 + 2,
    }


@pytest.mark.anyio
async def test_plus_one(client: AsyncClient, db_manager):
    response = await client.post("/plus-one", json={"code": "test3", "status": 1})
    assert response.status_code == 200
    assert response.json()["plus_one"] is True


@pytest.mark.anyio
async def test_download_database(client: AsyncClient, db_manager):
    response = await client.get("/admin/download-database")
    assert response.status_code == 200
    assert (
        response.headers["Content-Disposition"] == "attachment; filename=database.csv"
    )
    data = pd.read_csv(io.StringIO(response.text))
    assert data.shape == (4, 16)


@pytest.mark.anyio
async def test_upload_database_403(client: AsyncClient, db_manager):
    response = await client.post(
        "/upload-database",
        data={"code": "test1"},
        files={
            "database_data": bytes(
                pd.DataFrame([{"a": 1}, {"a": 2}]).to_csv(index=False), encoding="utf-8"
            )
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "This action is only authorised for admins"


@pytest.mark.anyio
async def test_upload_database(client: AsyncClient, db_manager):
    new_data = pd.DataFrame(
        [
            {
                "display_name": "Test Group 3",
                "code": "test3",
                "party_count": 3,
                "ceremony_count": 0,
            },
            {
                "display_name": "Admin",
                "code": "admin",
                "party_count": 2,
                "ceremony_count": 2,
            },
        ]
    )
    response = await client.post(
        "/upload-database",
        data={"code": "admin"},
        files={"database_data": bytes(new_data.to_csv(index=False), encoding="utf-8")},
    )
    assert response.status_code == 200
    assert len(response.json()["new_ids"]) == 2
    response = await client.get("/test3")
    assert response.status_code == 200
    assert response.json()["display_name"] == "Test Group 3"
    assert response.json()["party_count"] == 3
    assert response.json()["ceremony_count"] == 0
    response = await client.get("/admin/attendance")
    assert response.status_code == 200
    assert response.json() == {
        "ceremony_count": 0,
        "party_count": 0,
    }


@pytest.mark.anyio
async def test_upload_database_invalid_columns(client: AsyncClient, db_manager):
    response = await client.post(
        "/upload-database",
        data={"code": "admin"},
        files={
            "database_data": bytes(
                pd.DataFrame([{"a": 1}, {"a": 2}]).to_csv(index=False), encoding="utf-8"
            )
        },
    )
    assert response.status_code == 400


@pytest.mark.anyio
async def test_upload_database_duplicate_names(client: AsyncClient, db_manager):
    new_data = pd.DataFrame(
        [
            {
                "display_name": "Test Group 3",
                "code": "test3",
                "party_count": 3,
                "ceremony_count": 0,
            },
            {
                "display_name": "Test Group 3",
                "code": "test3",
                "party_count": 3,
                "ceremony_count": 0,
            },
            {
                "display_name": "Admin",
                "code": "admin",
                "party_count": 2,
                "ceremony_count": 2,
            },
        ]
    )
    response = await client.post(
        "/upload-database",
        data={"code": "admin"},
        files={"database_data": bytes(new_data.to_csv(index=False), encoding="utf-8")},
    )
    assert response.status_code == 400


@pytest.mark.anyio
async def test_upload_database_duplicate_codes(client: AsyncClient, db_manager):
    new_data = pd.DataFrame(
        [
            {
                "display_name": "Test Group 2",
                "code": "test3",
                "party_count": 3,
                "ceremony_count": 0,
            },
            {
                "display_name": "Test Group 3",
                "code": "test3",
                "party_count": 3,
                "ceremony_count": 0,
            },
            {
                "display_name": "Admin",
                "code": "admin",
                "party_count": 2,
                "ceremony_count": 2,
            },
        ]
    )
    response = await client.post(
        "/upload-database",
        data={"code": "admin"},
        files={"database_data": bytes(new_data.to_csv(index=False), encoding="utf-8")},
    )
    assert response.status_code == 400


@pytest.mark.anyio
async def test_upload_database_no_admin(client: AsyncClient, db_manager):
    new_data = pd.DataFrame(
        [
            {
                "display_name": "Test Group 2",
                "code": "test3",
                "party_count": 3,
                "ceremony_count": 0,
            }
        ]
    )
    response = await client.post(
        "/upload-database",
        data={"code": "admin"},
        files={"database_data": bytes(new_data.to_csv(index=False), encoding="utf-8")},
    )
    assert response.status_code == 400


@pytest.mark.anyio
async def test_upload_database_null_values(client: AsyncClient, db_manager):
    new_data = pd.DataFrame(
        [
            {
                "display_name": "Test Group 2",
                "code": "test3",
                "party_count": 3,
                "ceremony_count": None,
            },
            {
                "display_name": "Admin",
                "code": "admin",
                "party_count": None,
                "ceremony_count": 2,
            },
        ]
    )
    response = await client.post(
        "/upload-database",
        data={"code": "admin"},
        files={"database_data": bytes(new_data.to_csv(index=False), encoding="utf-8")},
    )
    assert response.status_code == 400
