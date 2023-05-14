import io
import logging
from pathlib import Path

import boto3
import pandas as pd
from botocore.exceptions import NoCredentialsError
from decouple import config
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from odmantic import AIOEngine

from .data import (
    DietaryRequirementsRequest,
    MusicResponse,
    RSVPRequest,
    SongChoiceRequest,
    WeddingGuestGroup,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = AsyncIOMotorClient(config("MONGO_URI", default="mongodb://localhost:27017/"))
engine = AIOEngine(client=client, database=config("MONGO_DB_NAME", default="test"))

templates_dir = Path(__file__).parent / "templates"

app = FastAPI()


async def fetch_guest_group(code: str) -> WeddingGuestGroup:
    guest_group = await engine.find_one(
        WeddingGuestGroup, WeddingGuestGroup.code == code
    )
    if not guest_group:
        raise HTTPException(status_code=404, detail="Invalid user code, please login")
    return guest_group


async def is_admin(code: str):
    guest_group = await fetch_guest_group(code)
    if not guest_group.admin:
        raise HTTPException(
            status_code=403,
            detail="This action is only authorised for admins",
        )


@app.get("/health")
async def root():
    return {"status": "healthy!"}


@app.get("/{code}")
async def get_code(code: str, response_model=WeddingGuestGroup):
    grp = await fetch_guest_group(code)
    return grp


@app.get("/{code}/music")
async def get_music(code: str) -> list[MusicResponse]:
    await fetch_guest_group(code)
    music = []
    for grp in await engine.find(WeddingGuestGroup):
        if grp.song_choice:
            music.append(
                MusicResponse(
                    display_name=grp.display_name, song_choice=grp.song_choice
                )
            )
    return music


@app.get("/{code}/parking_count")
async def get_parking_count(code: str) -> dict[str, int]:
    await fetch_guest_group(code)
    parking_count = sum(
        [grp.parking_required for grp in await engine.find(WeddingGuestGroup)]
    )
    return {"parking_count": parking_count}


@app.get("/{code}/attendance")
async def get_attendance(code: str) -> dict[str, int]:
    await is_admin(code)
    grp_attending = [
        grp for grp in await engine.find(WeddingGuestGroup) if grp.attendance == 1
    ]
    return {
        "attending_group_count": len(grp_attending),
        "attending_total_count": sum([grp.count for grp in grp_attending]),
        "attending_wedding_count": sum(
            [grp.wedding_party_count for grp in grp_attending]
        ),
    }


@app.post("/rsvp")
async def rsvp(rsvp_data: RSVPRequest) -> WeddingGuestGroup:
    grp = await fetch_guest_group(rsvp_data.code)
    grp.attendance = rsvp_data.status
    await engine.save(grp)
    return grp


@app.post("/songchoice")
async def songchoice(songchoice_data: SongChoiceRequest) -> WeddingGuestGroup:
    grp = await fetch_guest_group(songchoice_data.code)
    grp.song_choice = songchoice_data.song_choice
    await engine.save(grp)
    return grp


@app.post("/dietary-requirements")
async def dietary_requirements(
    dietary_requirements_data: DietaryRequirementsRequest,
) -> WeddingGuestGroup:
    grp = await fetch_guest_group(dietary_requirements_data.code)
    grp.dietary_requirements = dietary_requirements_data.requirements
    await engine.save(grp)
    return grp


@app.post("/photo")
async def photo(code: str = Form(...), photos: list[UploadFile] = File(...)) -> dict:
    await fetch_guest_group(code)
    try:
        bucket_name = config("AWS_BUCKET_NAME", default="s3://rjwedding")
        s3 = boto3.client("s3")
        for file in photos:
            s3.upload_fileobj(file.file, bucket_name, f"{file.filename}")
            logger.info(
                f"{code} uploaded file {file.filename} to {bucket_name}/{file.filename}"
            )
    except NoCredentialsError:
        logger.error("AWS credentials not available")
        raise HTTPException(status_code=500, detail="AWS credentials not available")
    return {"message": "Photos uploaded!"}


@app.get("/{code}/download_database")
async def download_database(code: str) -> StreamingResponse:
    await is_admin(code)
    data = pd.concat(
        [record.as_pandas() for record in await engine.find(WeddingGuestGroup)],
        ignore_index=True,
    )
    stream = io.StringIO()
    data.to_csv(stream, index=False)
    response = StreamingResponse(iter([stream.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=database.csv"
    return response


def database_validation(data: pd.DataFrame) -> pd.DataFrame:
    for col in ["Name", "Guest count", "Wedding party", "Code", "Attendance"]:
        if col not in data.columns:
            raise HTTPException(
                status_code=400,
                detail="Invalid database format. Must contain the columns: Name, Guest count, Wedding party, and Code",
            )
    if data["Name"].nunique() != data.shape[0]:
        raise HTTPException(
            status_code=400, detail="Invalid database. Cannot contain duplicate names."
        )
    if data["Code"].nunique() != data.shape[0]:
        raise HTTPException(
            status_code=400, detail="Invalid database. Cannot contain duplicate codes."
        )
    if "admin" not in data["Name"].values:
        raise HTTPException(
            status_code=400, detail="Invalid database. Must contain an admin."
        )
    if data.isnull().any().sum() > 0:
        raise HTTPException(
            status_code=400, detail="Invalid database. Cannot contain null values."
        )
    data["Code"] = data["Code"].apply(lambda x: str(x).replace(" ", ""))
    return data


@app.post("/upload_database")
async def upload_database(
    code: str = Form(...), database_data: UploadFile = File(...)
) -> dict:
    await is_admin(code)
    try:
        await engine.remove(WeddingGuestGroup)
        df = database_validation(pd.read_csv(database_data.file))
        new_ids = []
        for index, row in df.iterrows():
            grp = WeddingGuestGroup(
                display_name=str(row["Name"]),
                count=int(row["Guest count"]),
                wedding_party_count=int(row["Wedding party"]),
                code=str(row["Code"].replace(" ", "")),
                admin=str(row["Name"]) == "admin",
                attendance=int(row["Attendance"]),
            )
            saved_grp = await engine.save(grp)
            new_ids.append(saved_grp.id)
    except NoCredentialsError:
        logger.error("AWS credentials not available")
        raise HTTPException(status_code=500, detail="AWS credentials not available")
    return {"message": "Database uploaded!", "new_ids": new_ids}
