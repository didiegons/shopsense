from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from app.models.product import Product


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_budget: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    min_ram_gb: int | None = Field(default=None, gt=0)
    operating_system: str | None = Field(default=None, min_length=1)
    max_weight_kg: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    category_filters: dict[str, JsonValue] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )

    @field_validator("operating_system")
    @classmethod
    def normalize_operating_system(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("operating_system cannot be blank")
        return normalized


class SearchResponse(BaseModel):
    results: list[Product]
    total: int
    applied_filters: SearchRequest