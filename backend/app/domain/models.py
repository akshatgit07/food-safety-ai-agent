from datetime import date as CalendarDate
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

NonNegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
SCORE_VERSION = "guiltless-v1/g-personal-v1"


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Nutrition(DomainModel):
    # All amounts must share the declared serving basis. Micronutrient keys
    # include units (e.g. calcium_mg); targets use the same units.
    basis: str = "per serving"
    calories: NonNegative
    protein_g: NonNegative
    carbs_g: NonNegative = 0
    fat_g: NonNegative = 0
    fiber_g: NonNegative
    sugar_g: NonNegative
    sodium_mg: NonNegative
    micronutrients: dict[str, NonNegative] = Field(default_factory=dict)


class Provenance(DomainModel):
    source: str
    verified: bool = False
    reference: str | None = None
    confidence: float = Field(default=0.3, ge=0, le=1)
    retrieved_at: str | None = None


class Product(DomainModel):
    product_id: str = Field(min_length=1)
    barcode: str | None = None
    name: str = Field(min_length=1)
    brand: str = ""
    category: str = ""
    nutrition: Nutrition
    ingredients: list[str] = Field(default_factory=list)
    allergens: list[str] = Field(default_factory=list)
    allergen_info_complete: bool = False
    diet_flags: list[str] = Field(default_factory=list)
    processing_metadata: dict[str, str] = Field(default_factory=dict)
    base_score: float | None = Field(default=None, ge=0, le=100)
    score_version: str = SCORE_VERSION
    provenance: Provenance
    price: NonNegative | None = None
    currency: str = "USD"
    in_stock: bool | None = None
    stores: list[str] = Field(default_factory=list)


class UserProfile(DomainModel):
    user_id: str = "demo-user"
    primary_goal: str = "balanced nutrition"
    secondary_goals: list[str] = Field(default_factory=list)
    calorie_target: NonNegative | None = None
    protein_target: NonNegative | None = None
    carb_target: NonNegative | None = None
    fat_target: NonNegative | None = None
    micronutrient_targets: dict[str, NonNegative] = Field(default_factory=dict)
    allergies: list[str] = Field(default_factory=list)
    dietary_preferences: list[str] = Field(default_factory=list)
    ingredients_to_avoid: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(default_factory=list)
    preferred_stores: list[str] = Field(default_factory=list)
    budget_preferences: dict[str, NonNegative] = Field(default_factory=dict)


class DailyNutritionState(DomainModel):
    calories_consumed: NonNegative = 0
    protein_consumed: NonNegative = 0
    carbs_consumed: NonNegative = 0
    fat_consumed: NonNegative = 0
    micronutrients_consumed: dict[str, NonNegative] = Field(default_factory=dict)
    date: CalendarDate = Field(default_factory=CalendarDate.today)


class FactorImpact(DomainModel):
    factor: str
    impact: float
    reason: str


class GPersonalScore(DomainModel):
    base_score: float
    personal_score: float | None
    compatibility: Literal["compatible", "incompatible"]
    drivers: list[FactorImpact] = Field(default_factory=list)
    penalties: list[FactorImpact] = Field(default_factory=list)
    hard_constraint_failures: list[str] = Field(default_factory=list)
    score_version: str = SCORE_VERSION
