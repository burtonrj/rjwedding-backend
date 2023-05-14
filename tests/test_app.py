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
        "count": 1,
        "wedding_party_count": 0,
        "address": None,
        "postcode": None,
        "email": None,
        "phone": None,
        "dietary_requirements": None,
        "song_choice": None,
        "attendance": -1,
        "admin": False,
        "code": "test1",
        "parking_required": False,
    }


@pytest.mark.anyio
async def test_get_code_404(client: AsyncClient, db_manager):
    response = await client.get("/test3")
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
    response = await client.get("test3/parking_count")
    assert response.status_code == 404


@pytest.mark.anyio
async def test_rsvp(client: AsyncClient, db_manager):
    response = await client.get("/test1")
    assert response.status_code == 200
    assert response.json()["attendance"] == -1
    response = await client.post("/rsvp", json={"code": "test1", "status": 1})
    assert response.status_code == 200
    assert response.json()["attendance"] == 1
    response = await client.post("/rsvp", json={"code": "test1", "status": 0})
    assert response.status_code == 200
    assert response.json()["attendance"] == 0


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
        "attending_group_count": 2,
        "attending_total_count": 4,
        "attending_wedding_count": 4,
    }


@pytest.mark.anyio
async def test_get_attendance_not_admin(client: AsyncClient, db_manager):
    response = await client.get("/test1/attendance")
    assert response.status_code == 403


@pytest.mark.anyio
async def test_download_database(client: AsyncClient, db_manager):
    response = await client.get("/admin/download_database")
    assert response.status_code == 200
    assert (
        response.headers["Content-Disposition"] == "attachment; filename=database.csv"
    )
    data = pd.read_csv(io.StringIO(response.text))
    assert data.shape == (3, 14)


@pytest.mark.anyio
async def test_upload_database_403(client: AsyncClient, db_manager):
    response = await client.post(
        "/upload_database",
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
                "Name": "Test Group 3",
                "Code": "test3",
                "Guest count": 3,
                "Wedding party": 0,
                "Attendance": -1,
            },
            {
                "Name": "admin",
                "Code": "admin",
                "Guest count": 2,
                "Wedding party": 2,
                "Attendance": 1,
            },
        ]
    )
    response = await client.post(
        "/upload_database",
        data={"code": "admin"},
        files={"database_data": bytes(new_data.to_csv(index=False), encoding="utf-8")},
    )
    assert response.status_code == 200
    assert len(response.json()["new_ids"]) == 2
    response = await client.get("/test3")
    assert response.status_code == 200
    assert response.json()["display_name"] == "Test Group 3"
    assert response.json()["count"] == 3
    assert response.json()["wedding_party_count"] == 0
    response = await client.get("/admin/attendance")
    assert response.status_code == 200
    assert response.json() == {
        "attending_group_count": 1,
        "attending_total_count": 2,
        "attending_wedding_count": 2,
    }


@pytest.mark.anyio
async def test_upload_database_invalid_columns(client: AsyncClient, db_manager):
    response = await client.post(
        "/upload_database",
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
                "Name": "admin",
                "Code": "test3",
                "Guest count": 3,
                "Wedding party": 0,
                "Attendance": -1,
            },
            {
                "Name": "admin",
                "Code": "admin",
                "Guest count": 2,
                "Wedding party": 2,
                "Attendance": 1,
            },
        ]
    )
    response = await client.post(
        "/upload_database",
        data={"code": "admin"},
        files={"database_data": bytes(new_data.to_csv(index=False), encoding="utf-8")},
    )
    assert response.status_code == 400


@pytest.mark.anyio
async def test_upload_database_duplicate_codes(client: AsyncClient, db_manager):
    new_data = pd.DataFrame(
        [
            {
                "Name": "test3",
                "Code": "admin",
                "Guest count": 3,
                "Wedding party": 0,
                "Attendance": -1,
            },
            {
                "Name": "admin",
                "Code": "admin",
                "Guest count": 2,
                "Wedding party": 2,
                "Attendance": 1,
            },
        ]
    )
    response = await client.post(
        "/upload_database",
        data={"code": "admin"},
        files={"database_data": bytes(new_data.to_csv(index=False), encoding="utf-8")},
    )
    assert response.status_code == 400


@pytest.mark.anyio
async def test_upload_database_no_admin(client: AsyncClient, db_manager):
    new_data = pd.DataFrame(
        [
            {
                "Name": "test3",
                "Code": "admin",
                "Guest count": 3,
                "Wedding party": 0,
                "Attendance": -1,
            }
        ]
    )
    response = await client.post(
        "/upload_database",
        data={"code": "admin"},
        files={"database_data": bytes(new_data.to_csv(index=False), encoding="utf-8")},
    )
    assert response.status_code == 400


@pytest.mark.anyio
async def test_upload_database_null_values(client: AsyncClient, db_manager):
    new_data = pd.DataFrame(
        [
            {
                "Name": "test3",
                "Code": "admin",
                "Guest count": 3,
                "Wedding party": 0,
                "Attendance": None,
            },
            {
                "Name": "admin",
                "Code": "admin",
                "Guest count": None,
                "Wedding party": 2,
                "Attendance": 1,
            },
        ]
    )
    response = await client.post(
        "/upload_database",
        data={"code": "admin"},
        files={"database_data": bytes(new_data.to_csv(index=False), encoding="utf-8")},
    )
    assert response.status_code == 400
