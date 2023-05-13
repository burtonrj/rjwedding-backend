from typing import Optional

from odmantic import Field, Model
from pydantic import BaseModel


class RSVP(BaseModel):
    code: str
    status: int


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
