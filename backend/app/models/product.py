from pydantic import BaseModel, ConfigDict, Field, JsonValue

from app.models.offer import Offer


class Specification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    processor: str | None = None
    ram_gb: int | None = Field(default=None, gt=0)
    storage_gb: int | None = Field(default=None, gt=0)
    weight_kg: float | None = Field(default=None, gt=0)
    operating_system: str | None = None


class Product(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str
    brand: str
    model_name: str
    category: str
    image_url: str | None = None
    specifications: Specification = Field(default_factory=Specification)
    category_attributes: dict[str, JsonValue] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    rating: float | None = Field(default=None, ge=0, le=5)
    offer: Offer