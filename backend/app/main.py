from __future__ import annotations

import json
import os
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel, Field

from app.agent import CopilotRouter
from app.services.bag_optimizer import optimize_bag
from app.services.product_intelligence import compare_products, explain_product

app = FastAPI(
    title="Food Safety AI Agent",
    description="Nutrition chat, meal planning, shopping-list APIs, product explainability, and bag optimization.",
    version="0.4.0",
)

allowed_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=allowed_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    response: str


class ContextChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    context: dict[str, Any] = Field(default_factory=dict)


class MealPlanRequest(BaseModel):
    days: int = Field(default=5, ge=1, le=7)
    goal: str = "balanced nutrition"
    diet: str = "no restriction"
    allergies: list[str] = Field(default_factory=list)
    calorie_target: Optional[int] = Field(default=None, ge=800, le=6000)
    meals_per_day: int = Field(default=3, ge=1, le=6)


class ShoppingListRequest(BaseModel):
    meal_plan: Any
    servings: int = Field(default=1, ge=1, le=20)


class ProductExplainRequest(BaseModel):
    product: dict[str, Any]
    goal: str = "balanced nutrition"


class ProductCompareRequest(BaseModel):
    products: list[dict[str, Any]] = Field(min_length=2)
    goal: str = "balanced nutrition"


class BagOptimizeRequest(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
    goal: str = "balanced nutrition"


def get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not configured on the backend.",
        )
    return OpenAI(api_key=api_key)


def run_ai(instructions: str, user_input: str) -> str:
    try:
        response = get_client().responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            instructions=instructions,
            input=user_input,
        )
        return response.output_text
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI request failed: {exc}") from exc


def parse_json_response(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```")
        cleaned = cleaned.removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502,
            detail="The AI returned an invalid structured response.",
        ) from exc


def safe_enrich_meal_plan(meal_plan: Any) -> Any:
    if not isinstance(meal_plan, dict):
        return meal_plan

    try:
        from app.services.usda import enrich_meal_plan_with_usda

        return enrich_meal_plan_with_usda(meal_plan)
    except Exception as exc:
        meal_plan["nutrition_grounding"] = {
            "source": "model estimate",
            "status": "skipped",
            "warning": f"Nutrition enrichment failed safely: {type(exc).__name__}",
        }
        return meal_plan


def generate_meal_plan_data(prompt: dict[str, Any]) -> Any:
    result = run_ai(
        instructions=(
            "Create a practical meal plan. Return JSON only with keys: summary, days, "
            "and notes. Each day must contain meals; each meal must include name, ingredients, "
            "estimated_calories, and estimated_protein_g. Respect allergies and dietary limits. "
            "Use simple ingredient names that can be mapped to USDA foods where possible. "
            "Estimates must be clearly identified as estimates."
        ),
        user_input=json.dumps(prompt),
    )
    return safe_enrich_meal_plan(parse_json_response(result))


def generate_shopping_list_data(meal_plan: Any, servings: int) -> Any:
    result = run_ai(
        instructions=(
            "Convert the supplied meal plan into a consolidated grocery shopping list. "
            "Return JSON only with keys: servings, categories, and notes. Group items by "
            "produce, proteins, dairy_or_alternatives, pantry, frozen, and other. Merge duplicates "
            "and provide practical estimated quantities."
        ),
        user_input=json.dumps({"meal_plan": meal_plan, "servings": servings}),
    )
    return parse_json_response(result)


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok", "project": "Food Safety AI Agent"}


@app.get("/health")
def health() -> dict[str, bool]:
    return {"healthy": True}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    answer = run_ai(
        instructions=(
            "You are a practical nutrition assistant. Give concise, useful, "
            "evidence-aware guidance. Do not diagnose or replace medical care. "
            "Mention uncertainty and recommend professional guidance for medical conditions."
        ),
        user_input=request.message,
    )
    return ChatResponse(response=answer)


@app.post("/copilot/chat")
def context_chat(request: ContextChatRequest) -> dict[str, Any]:
    router = CopilotRouter(
        ai_runner=run_ai if os.getenv("OPENAI_API_KEY") else None,
        meal_plan_tool=generate_meal_plan_data,
        shopping_list_tool=generate_shopping_list_data,
    )
    result = router.route(request.message, request.context)
    result["context_used"] = request.context
    return result


@app.post("/meal-plan")
def create_meal_plan(request: MealPlanRequest) -> Any:
    prompt = {
        "days": request.days,
        "goal": request.goal,
        "diet": request.diet,
        "allergies": request.allergies,
        "calorie_target": request.calorie_target,
        "meals_per_day": request.meals_per_day,
    }
    return generate_meal_plan_data(prompt)


@app.post("/shopping-list")
def create_shopping_list(request: ShoppingListRequest) -> Any:
    return generate_shopping_list_data(request.meal_plan, request.servings)


@app.post("/product/explain")
def product_explain(request: ProductExplainRequest) -> dict[str, Any]:
    return explain_product(request.product, request.goal)


@app.post("/product/compare")
def product_compare(request: ProductCompareRequest) -> dict[str, Any]:
    return compare_products(request.products, request.goal)


@app.post("/bag/optimize")
def bag_optimize(request: BagOptimizeRequest) -> dict[str, Any]:
    return optimize_bag(request.items, request.goal)
