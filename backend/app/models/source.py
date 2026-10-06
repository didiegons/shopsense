from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, HttpUrl


class DataSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str
    source_url: HttpUrl
    source_checked_date: date
    data_status: Literal["demo", "live"]