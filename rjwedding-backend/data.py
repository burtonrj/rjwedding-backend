from typing import Optional

import pandas as pd
from fastapi import UploadFile
from odmantic import Field, Model
from pydantic import BaseModel


class WeddingGuestGroup(Model):
    display_name: str
    count: int
    wedding_party_count: int
    address: Optional[str] = Field(default=None)
    postcode: Optional[str] = Field(default=None)
    email: Optional[str] = Field(default=None)
    phone: Optional[str] = Field(default=None)
    dietary_requirements: Optional[str] = Field(default=None)
    song_choice: Optional[str] = Field(default=None)
    attendance: int = Field(default=-1)
    admin: bool = Field(default=False)
    code: str = Field(unique=True)
    parking_required: bool = Field(default=False)

    def as_pandas(self) -> pd.DataFrame:
        return pd.DataFrame(self.dict(), index=[0])


class Music(BaseModel):
    display_name: str
    song_choice: str


class RSVP(BaseModel):
    code: str
    status: int


class SongChoice(BaseModel):
    code: str
    song_choice: str


class DietaryRequirements(BaseModel):
    code: str
    dietary_requirements: str


class Photo(BaseModel):
    code: str
    photos: list[UploadFile]
