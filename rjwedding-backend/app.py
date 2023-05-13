import io
import logging
from pathlib import Path

import boto3
import pandas as pd
from botocore.exceptions import NoCredentialsError
from data import RSVP, DietaryRequirements, Music, Photo, SongChoice, WeddingGuestGroup
from decouple import config
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from odmantic import AIOEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = AsyncIOMotorClient(config("MONGO_URI", default="mongodb://localhost:27017/"))
engine = AIOEngine(client=client, database=config("MONGO_DB_NAME", default="wedding"))

templates_dir = Path(__file__).parent / "templates"

app = FastAPI()


async def fetch_guest_group(code: str) -> WeddingGuestGroup:
    guest_group = await engine.find_one(
        WeddingGuestGroup, WeddingGuestGroup.code == code
    )
    if not guest_group:
        raise HTTPException(status_code=404, detail="Invalid user code, please login")
    return guest_group


async def is_admin(code: str) -> bool:
    guest_group = await fetch_guest_group(code)
    return guest_group.admin


@app.get("/health")
async def root():
    return {"status": "healthy!"}


@app.get("/{code}")
async def get_code(code: str, response_model=WeddingGuestGroup):
    grp = await fetch_guest_group(code)
    return grp


@app.get("/music")
async def get_music() -> list[Music]:
    music = []
    for grp in await engine.find(WeddingGuestGroup):
        if grp.song_choice:
            music.append(
                Music(display_name=grp.display_name, song_choice=grp.song_choice)
            )
    return music


@app.post("/rsvp")
async def rsvp(rsvp_data: RSVP) -> WeddingGuestGroup:
    grp = await fetch_guest_group(rsvp_data.code)
    grp.attendance = rsvp_data.status
    await engine.save(grp)
    return grp


@app.post("/songchoice")
async def songchoice(songchoice_data: SongChoice) -> WeddingGuestGroup:
    grp = await fetch_guest_group(songchoice_data.code)
    grp.song_choice = songchoice_data.song_choice
    await engine.save(grp)
    return grp


@app.post("/dietary-requirements")
async def dietary_requirements(
    dietary_requirements_data: DietaryRequirements,
) -> WeddingGuestGroup:
    grp = await fetch_guest_group(dietary_requirements_data.code)
    grp.dietary_requirements = dietary_requirements_data.dietary_requirements
    await engine.save(grp)
    return grp


@app.post("/photo")
async def photo(photo_data: Photo) -> dict:
    await fetch_guest_group(photo_data.code)
    try:
        bucket_name = config("AWS_BUCKET_NAME", default="s3://rjwedding")
        s3 = boto3.client("s3")
        for file in photo_data.photos:
            s3.upload_fileobj(file.file, bucket_name, f"{photo.filename}")
            logger.info(
                f"{photo_data.code} uploaded file {file.filename} to {bucket_name}/{file.filename}"
            )
    except NoCredentialsError:
        logger.error("AWS credentials not available")
        raise HTTPException(status_code=500, detail="AWS credentials not available")
    return {"message": "Photos uploaded!"}


@app.get("/{code}/download_database")
async def download_database(code: str) -> StreamingResponse:
    admin_grp = await fetch_guest_group(code)
    if not admin_grp.admin:
        raise HTTPException(
            status_code=403,
            detail="You are not authorised to download the database",
        )
    data = pd.concat(
        [record.as_pandas() for record in await engine.find(WeddingGuestGroup)],
        ignore_index=True,
    )
    stream = io.StringIO()
    data.to_csv(stream, index=False)
    response = StreamingResponse(iter([stream.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=database.csv"
    return response


@app.post("/upload_database")
async def upload_database(code: str, file: UploadFile) -> dict:
    admin_grp = await fetch_guest_group(code)
    if not admin_grp.admin:
        raise HTTPException(
            status_code=403,
            detail="You are not authorised to upload the database",
        )
    try:
        for grp in await engine.find(WeddingGuestGroup):
            await engine.delete(grp)
        df = pd.read_csv(file.file)
        try:
            for index, row in df.iterrows():
                grp = WeddingGuestGroup(
                    display_name=row["Name"],
                    count=row["Guest count"],
                    wedding_party=row["Wedding party"],
                    code=row["Code"],
                )
                await engine.save(grp)
        except KeyError:
            raise HTTPException(
                status_code=400,
                detail="Invalid database format",
            )
    except NoCredentialsError:
        logger.error("AWS credentials not available")
        raise HTTPException(status_code=500, detail="AWS credentials not available")
    return {"message": "Database uploaded!"}