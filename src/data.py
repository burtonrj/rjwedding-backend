from typing import Optional

import pandas as pd
from fastapi import UploadFile
from odmantic import Field, Model
from pydantic import BaseModel
from pydantic import Field as PydanticField


class WeddingGuestGroup(Model):
    display_name: str
    party_count: int
    ceremony_count: int
    plus_one: bool = Field(default=False)
    party_attendance: int = Field(default=-1)
    ceremony_attendance: int = Field(default=-1)
    address: Optional[str] = Field(default=None)
    postcode: Optional[str] = Field(default=None)
    email: Optional[str] = Field(default=None)
    phone: Optional[str] = Field(default=None)
    dietary_requirements: Optional[str] = Field(default=None)
    song_choice: Optional[str] = Field(default=None)

    admin: bool = Field(default=False)
    code: str = Field(unique=True)
    parking_required: bool = Field(default=False)

    def as_pandas(self) -> pd.DataFrame:
        return pd.DataFrame(self.dict(), index=[0])

    @property
    def party_total(self) -> int:
        count = self.party_count if self.party_attendance == 1 else 0
        if "&" in self.display_name or self.party_count == 1:
            if not self.plus_one:
                return count - 1
        return count

    @property
    def ceremony_total(self) -> int:
        count = self.ceremony_count if self.ceremony_attendance == 1 else 0
        if "&" in self.display_name or self.ceremony_count == 1:
            return count
        if self.plus_one:
            return count + 1
        return count


class MusicResponse(BaseModel):
    display_name: str
    song_choice: str


class RequestBase(BaseModel):
    code: str


class RSVPRequest(RequestBase):
    status: int
    event: str = PydanticField(regex="^(party|ceremony)$")


class PlusOneRequest(RequestBase):
    status: bool


class SongChoiceRequest(RequestBase):
    song_choice: str


class DietaryRequirementsRequest(RequestBase):
    requirements: str


class ParkingRequiredRequest(RequestBase):
    required: bool


class PhotoRequest(RequestBase):
    photos: list[UploadFile]


class DatabaseRequest(RequestBase):
    file: UploadFile
