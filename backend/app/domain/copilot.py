from typing import Any

from pydantic import Field, model_validator

from app.domain.models import DailyNutritionState, DomainModel, UserProfile


class CopilotV2Request(DomainModel):
    message: str = Field(min_length=1, max_length=4000)
    user_id: str = Field(default="demo-user", min_length=1, max_length=100)
    load_memory: bool = False
    user_profile: UserProfile | None = None
    daily_nutrition_state: DailyNutritionState | None = None
    product_id: str | None = None
    barcode: str | None = None
    bag_product_ids: list[str] | None = Field(default=None, max_length=50)
    planning_context: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def exact_identifier(self):
        if self.product_id is not None and self.barcode is not None:
            raise ValueError("Supply product_id or barcode, not both")
        if not self.message.strip():
            raise ValueError("Message cannot be blank")
        return self


class Grounding(DomainModel):
    product_ids: list[str]
    score_version: str
    data_sources: list[str]
    method: str


class CopilotV2Response(DomainModel):
    intent: str
    response: str
    grounding: Grounding
    confidence: float = Field(ge=0, le=1)
    suggested_actions: list[str]
    tool_result: dict[str, Any]
    errors: list[str] = Field(default_factory=list)
    context_used: dict[str, Any]
