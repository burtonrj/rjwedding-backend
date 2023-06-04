import io
import logging
from pathlib import Path

import boto3
import pandas as pd
from botocore.exceptions import NoCredentialsError
from decouple import config
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from odmantic import AIOEngine

from .data import (
    DietaryRequirementsRequest,
    MusicResponse,
    ParkingRequiredRequest,
    PlusOneRequest,
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

origins = [config("FRONTEND_URL", default="http://localhost:5173")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/{code}", response_model=WeddingGuestGroup)
async def get_code(code: str):
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


@app.get("/admin/attendance")
async def get_attendance() -> dict[str, int]:
    party_count = sum([grp.party_total for grp in await engine.find(WeddingGuestGroup)])
    ceremony_count = sum(
        [grp.ceremony_total for grp in await engine.find(WeddingGuestGroup)]
    )
    return {
        "party_count": party_count,
        "ceremony_count": ceremony_count,
    }


@app.post("/rsvp")
async def rsvp(rsvp_data: RSVPRequest) -> WeddingGuestGroup:
    grp = await fetch_guest_group(rsvp_data.code)
    if rsvp_data.event == "party":
        grp.party_attendance = rsvp_data.status
    elif rsvp_data.event == "ceremony":
        grp.ceremony_attendance = rsvp_data.status
    else:
        raise HTTPException(
            status_code=400, detail="Invalid event. Must be party or ceremony."
        )
    await engine.save(grp)
    return grp


@app.post("/plus-one")
async def plus_one(plus_one_data: PlusOneRequest) -> WeddingGuestGroup:
    grp = await fetch_guest_group(plus_one_data.code)
    grp.plus_one = plus_one_data.status
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


@app.post("/parking-required")
async def parking_required(
    dietary_requirements_data: ParkingRequiredRequest,
) -> WeddingGuestGroup:
    grp = await fetch_guest_group(dietary_requirements_data.code)
    grp.parking_required = dietary_requirements_data.required
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


@app.get("/{code}/download-database")
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
    for col in ["display_name", "party_count", "ceremony_count", "code"]:
        if col not in data.columns:
            raise HTTPException(
                status_code=400,
                detail="Invalid database format. Must contain the columns: Name, Guest count, Wedding party, and Code",
            )
    if data["display_name"].nunique() != data.shape[0]:
        raise HTTPException(
            status_code=400, detail="Invalid database. Cannot contain duplicate names."
        )
    if data["code"].nunique() != data.shape[0]:
        raise HTTPException(
            status_code=400, detail="Invalid database. Cannot contain duplicate codes."
        )
    if "Admin" not in data["display_name"].values:
        raise HTTPException(
            status_code=400, detail="Invalid database. Must contain an 'Admin'."
        )
    if data.isnull().any().sum() > 0:
        raise HTTPException(
            status_code=400, detail="Invalid database. Cannot contain null values."
        )
    data["code"] = data["code"].apply(lambda x: str(x).replace(" ", ""))
    return data


@app.post("/upload-database")
async def upload_database(
    code: str = Form(...), database_data: UploadFile = File(...)
) -> dict:
    await is_admin(code)
    try:
        df = database_validation(pd.read_csv(database_data.file))
        await engine.remove(WeddingGuestGroup)
        new_ids = []
        for index, row in df.iterrows():
            grp = WeddingGuestGroup(
                display_name=str(row["display_name"]),
                party_count=int(row["party_count"]),
                ceremony_count=int(row["ceremony_count"]),
                code=str(row["code"].replace(" ", "")),
                admin=str(row["display_name"]) == "Admin",
            )
            saved_grp = await engine.save(grp)
            new_ids.append(saved_grp.id)
    except NoCredentialsError:
        logger.error("AWS credentials not available")
        raise HTTPException(status_code=500, detail="AWS credentials not available")
    return {"message": "Database uploaded!", "new_ids": new_ids}
