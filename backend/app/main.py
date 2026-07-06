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
from app.services.coach_planner import build_client_plan
from app.services.commerce import prepare_checkout, prepare_instacart_checkout
from app.services.label_scanner import scan_label
from app.services.persistence import (
    DEMO_USER_ID,
    add_bag_item,
    clear_bag,
    create_or_update_client,
    get_bag,
    get_checkout,
    get_client as get_client_profile,
    get_client_plans,
    get_profile,
    get_user_plans,
    list_clients,
    load_user_memory,
    save_client_plan,
    save_copilot_message,
    save_plan_for_client,
    save_scan_history,
    save_user_plan,
    update_profile,
)
from app.services.product_intelligence import compare_products, explain_product
from app.services.workout_planner import build_workout_plan

app = FastAPI(
    title="Food Safety AI Agent",
    description="Nutrition chat, label scanning, product explainability, bag optimization, and meal-planning APIs.",
    version="0.6.0",
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
    user_id: Optional[str] = Field(default=None, max_length=100)
    load_memory: bool = False


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


class LabelScanRequest(BaseModel):
    label_text: Optional[str] = Field(default=None, max_length=12000)
    image_data_url: Optional[str] = Field(default=None, max_length=6_000_000)
    product_name: Optional[str] = Field(default=None, max_length=100)
    brand: Optional[str] = Field(default=None, max_length=100)
    user_id: str = Field(default=DEMO_USER_ID, max_length=100)


class WorkoutPlanRequest(BaseModel):
    goal: str = Field(default="general fitness", min_length=1, max_length=100)
    days_per_week: int = Field(default=3, ge=1, le=7)
    equipment: list[str] = Field(default_factory=lambda: ["bodyweight"])
    experience_level: str = Field(default="beginner", max_length=50)
    limitations: list[str] = Field(default_factory=list)
    session_minutes: int = Field(default=60, ge=20, le=120)


class CoachClientPlanRequest(BaseModel):
    client_id: Optional[str] = Field(default=None, max_length=36)
    client_name: str = Field(default="Demo Client", min_length=1, max_length=100)
    goal: str = Field(default="general fitness", min_length=1, max_length=100)
    diet: str = Field(default="balanced", max_length=100)
    allergies: list[str] = Field(default_factory=list)
    days_per_week: int = Field(default=3, ge=1, le=7)
    equipment: list[str] = Field(default_factory=lambda: ["bodyweight"])
    calorie_target: int = Field(default=2200, ge=800, le=6000)
    experience_level: str = Field(default="beginner", max_length=50)
    limitations: list[str] = Field(default_factory=list)
    session_minutes: int = Field(default=60, ge=20, le=120)


class CheckoutPrepareRequest(BaseModel):
    client_id: Optional[str] = Field(default=None, max_length=36)
    retailer: str = Field(default="preferred retailer", max_length=100)
    shopping_list: Optional[dict[str, Any]] = None
    shopping_strategy: Optional[dict[str, Any]] = None
    items: list[Any] = Field(default_factory=list)
    user_id: Optional[str] = Field(default=None, max_length=100)


class ProfileUpdateRequest(BaseModel):
    goal: str = Field(default="balanced nutrition", max_length=100)
    diet: str = Field(default="no restriction", max_length=100)
    allergies: list[str] = Field(default_factory=list)
    disliked_foods: list[str] = Field(default_factory=list)
    budget: str = Field(default="flexible", max_length=100)
    preferred_store: str = Field(default="Instacart", max_length=100)
    training_days: int = Field(default=3, ge=1, le=7)
    equipment: list[str] = Field(default_factory=list)
    calorie_target: int = Field(default=2200, ge=800, le=6000)


class BagAddRequest(BaseModel):
    product: dict[str, Any]
    quantity: int = Field(default=1, ge=1, le=99)


class PlanSaveRequest(BaseModel):
    plan: dict[str, Any]


class CoachClientCreateRequest(BaseModel):
    client_name: str = Field(default="Demo Client", min_length=1, max_length=100)
    goal: str = Field(default="general fitness", max_length=100)
    diet: str = Field(default="balanced", max_length=100)
    allergies: list[str] = Field(default_factory=list)
    days_per_week: int = Field(default=3, ge=1, le=7)
    equipment: list[str] = Field(default_factory=list)
    calorie_target: int = Field(default=2200, ge=800, le=6000)


class InstacartCheckoutRequest(BaseModel):
    user_id: str = Field(default=DEMO_USER_ID, max_length=100)
    items: list[Any] = Field(default_factory=list)
    shopping_list: Optional[dict[str, Any]] = None


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


def extract_label_image(image_data_url: str) -> dict[str, Any]:
    if len(image_data_url) > 6_000_000:
        raise ValueError("Image is too large. Use a label image under 4 MB.")
    try:
        response = get_client().responses.create(
            model=os.getenv("OPENAI_VISION_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini")),
            input=[{
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Extract this packaged-food label. Return JSON only with keys: product, confidence, warnings. "
                            "product must contain name, brand, category, nutrition, ingredients. nutrition must contain "
                            "calories, protein_g, fiber_g, sugar_g, sodium_mg as numbers. Use 0 for unreadable values."
                        ),
                    },
                    {"type": "input_image", "image_url": image_data_url},
                ],
            }],
        )
        payload = parse_json_response(response.output_text)
        if not isinstance(payload, dict):
            raise ValueError("Vision response was not a JSON object.")
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        raise ValueError(f"Label image extraction failed: {exc}") from exc


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
    user_id = request.user_id or request.context.get("user_id")
    context = dict(request.context)
    if request.load_memory or context.get("load_memory"):
        user_id = str(user_id or DEMO_USER_ID)
        memory = load_user_memory(user_id)
        context["memory"] = memory
        context.setdefault("profile", memory["profile"])
        context.setdefault("bag", memory["bag"])
        context.setdefault("recent_plans", memory["recent_plans"])
        context.setdefault("recent_scans", memory["recent_scans"])
        context.setdefault("goal", memory["profile"]["goal"])
        context.setdefault("diet", memory["profile"]["diet"])
        context.setdefault("equipment", memory["profile"]["equipment"])
        context.setdefault("days_per_week", memory["profile"]["training_days"])
        context.setdefault("calorie_target", memory["profile"]["calorie_target"])
    if user_id:
        save_copilot_message(str(user_id), "user", request.message, None, context)
    router = CopilotRouter(
        ai_runner=run_ai if os.getenv("OPENAI_API_KEY") else None,
        meal_plan_tool=generate_meal_plan_data,
        shopping_list_tool=generate_shopping_list_data,
    )
    result = router.route(request.message, context)
    result["context_used"] = context
    if user_id:
        save_copilot_message(str(user_id), "assistant", str(result.get("response") or ""), str(result.get("intent") or "general_chat"), context)
    return result


@app.get("/profile/{user_id}")
def profile_get(user_id: str) -> dict[str, Any]:
    return get_profile(user_id)


@app.put("/profile/{user_id}")
def profile_put(user_id: str, request: ProfileUpdateRequest) -> dict[str, Any]:
    return update_profile(user_id, request.model_dump())


@app.get("/bag/{user_id}")
def persistent_bag_get(user_id: str) -> dict[str, Any]:
    items = get_bag(user_id)
    return {"user_id": user_id, "items": items, "count": len(items)}


@app.post("/bag/{user_id}/add")
def persistent_bag_add(user_id: str, request: BagAddRequest) -> dict[str, Any]:
    item = add_bag_item(user_id, request.product, request.quantity)
    return {"user_id": user_id, "added": item, "items": get_bag(user_id)}


@app.delete("/bag/{user_id}/clear")
def persistent_bag_clear(user_id: str) -> dict[str, Any]:
    return {"user_id": user_id, "cleared": clear_bag(user_id), "items": []}


@app.get("/plans/{user_id}")
def plans_get(user_id: str) -> dict[str, Any]:
    return {"user_id": user_id, **get_user_plans(user_id)}


@app.post("/plans/{user_id}/meal")
def plans_save_meal(user_id: str, request: PlanSaveRequest) -> dict[str, Any]:
    return save_user_plan(user_id, "meal", request.plan)


@app.post("/plans/{user_id}/workout")
def plans_save_workout(user_id: str, request: PlanSaveRequest) -> dict[str, Any]:
    return save_user_plan(user_id, "workout", request.plan)


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


@app.post("/workout-plan")
def create_workout_plan(request: WorkoutPlanRequest) -> dict[str, Any]:
    return build_workout_plan(request.model_dump())


@app.post("/coach/client-plan")
def create_coach_client_plan(request: CoachClientPlanRequest) -> dict[str, Any]:
    request_data = request.model_dump()
    plan = build_client_plan(request_data)
    plan["persistence"] = save_client_plan(request_data, plan)
    return plan


@app.get("/coach/clients")
def coach_clients() -> dict[str, Any]:
    clients = list_clients()
    return {"clients": clients, "count": len(clients)}


@app.post("/coach/clients")
def coach_clients_create(request: CoachClientCreateRequest) -> dict[str, Any]:
    return create_or_update_client(request.model_dump())


@app.get("/coach/clients/{client_id}")
def coach_client(client_id: str) -> dict[str, Any]:
    client = get_client_profile(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client profile not found.")
    return client


@app.get("/coach/clients/{client_id}/plans")
def coach_client_plans(client_id: str) -> dict[str, Any]:
    if get_client_profile(client_id) is None:
        raise HTTPException(status_code=404, detail="Client profile not found.")
    plans = get_client_plans(client_id)
    return {"client_id": client_id, "plans": plans, "count": len(plans)}


@app.post("/coach/clients/{client_id}/plans")
def coach_client_plans_save(client_id: str, request: PlanSaveRequest) -> dict[str, Any]:
    try:
        return save_plan_for_client(client_id, request.plan)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/checkout/prepare")
def checkout_prepare(request: CheckoutPrepareRequest) -> dict[str, Any]:
    try:
        return prepare_checkout(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/checkout/instacart")
def checkout_instacart(request: InstacartCheckoutRequest) -> dict[str, Any]:
    try:
        return prepare_instacart_checkout(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/checkout/{checkout_id}")
def checkout_session(checkout_id: str) -> dict[str, Any]:
    checkout = get_checkout(checkout_id)
    if checkout is None:
        raise HTTPException(status_code=404, detail="Checkout session not found.")
    return checkout


@app.post("/shopping-list")
def create_shopping_list(request: ShoppingListRequest) -> Any:
    return generate_shopping_list_data(request.meal_plan, request.servings)


@app.post("/product/explain")
def product_explain(request: ProductExplainRequest) -> dict[str, Any]:
    return explain_product(request.product, request.goal)


@app.post("/product/scan")
def product_scan(request: LabelScanRequest) -> dict[str, Any]:
    try:
        result = scan_label(
            label_text=request.label_text,
            image_data_url=request.image_data_url,
            product_name=request.product_name,
            brand=request.brand,
            image_extractor=extract_label_image if request.image_data_url and os.getenv("OPENAI_API_KEY") else None,
        )
        result["persistence"] = save_scan_history(request.user_id, result)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/product/compare")
def product_compare(request: ProductCompareRequest) -> dict[str, Any]:
    return compare_products(request.products, request.goal)


@app.post("/bag/optimize")
def bag_optimize(request: BagOptimizeRequest) -> dict[str, Any]:
    return optimize_bag(request.items, request.goal)
