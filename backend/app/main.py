import json
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel, Field

app = FastAPI(
    title="Food Safety AI Agent",
    description="Nutrition chat, meal planning, and shopping-list APIs.",
    version="0.1.0",
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


class MealPlanRequest(BaseModel):
    days: int = Field(default=5, ge=1, le=7)
    goal: str = "balanced nutrition"
    diet: str = "no restriction"
    allergies: list[str] = []
    calorie_target: int | None = Field(default=None, ge=800, le=6000)
    meals_per_day: int = Field(default=3, ge=1, le=6)


class ShoppingListRequest(BaseModel):
    meal_plan: Any
    servings: int = Field(default=1, ge=1, le=20)


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
    result = run_ai(
        instructions=(
            "Create a practical meal plan. Return JSON only with keys: summary, days, "
            "and notes. Each day must contain meals; each meal must include name, ingredients, "
            "estimated_calories, and estimated_protein_g. Respect allergies and dietary limits. "
            "Estimates must be clearly identified as estimates."
        ),
        user_input=json.dumps(prompt),
    )
    return parse_json_response(result)


@app.post("/shopping-list")
def create_shopping_list(request: ShoppingListRequest) -> Any:
    result = run_ai(
        instructions=(
            "Convert the supplied meal plan into a consolidated grocery shopping list. "
            "Return JSON only with keys: servings, categories, and notes. Group items by "
            "produce, proteins, dairy_or_alternatives, pantry, frozen, and other. Merge duplicates "
            "and provide practical estimated quantities."
        ),
        user_input=json.dumps(
            {"meal_plan": request.meal_plan, "servings": request.servings}
        ),
    )
    return parse_json_response(result)
