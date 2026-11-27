from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

MAX_MESSAGE_LENGTH = 1000


class Role(StrEnum):
    BUYER = "buyer"
    SELLER = "seller"


class Outcome(StrEnum):
    DEAL = "deal"
    NO_DEAL = "no_deal"
    INVALID_DEAL = "invalid_deal"
    PROTOCOL_ERROR = "protocol_error"
    MAX_ROUNDS = "max_rounds"


class Offer(BaseModel):
    model_config = ConfigDict(frozen=True)

    price: int = Field(gt=0)
    accept: bool = False
    walk_away: bool = False
    message: str = Field(max_length=MAX_MESSAGE_LENGTH)


class Scenario(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    item: str
    public_listing_price: int
    buyer_max: int
    seller_min: int
    max_rounds: int
    currency: str

    @property
    def zopa(self) -> int:
        return self.buyer_max - self.seller_min


class Turn(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Role
    raw: str
    offer: Offer | None
    error: str | None = None
