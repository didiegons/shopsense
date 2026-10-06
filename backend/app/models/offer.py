from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.source import DataSource


class Offer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price: float = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    availability: Literal["in_stock", "out_of_stock", "unknown"]
    source: DataSource