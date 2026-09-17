from __future__ import annotations

from typing import Any

from app.services.workout_planner import build_workout_plan

NUTRITION_GUIDANCE_NOTE = (
    "General nutrition guidance only - not medical or dietetic advice, and not a treatment "
    "plan. Calorie and protein figures are starting estimates to adjust from. Refer clients "
    "with medical conditions, disordered-eating history, pregnancy, or who are under 18 to a "
    "registered dietitian or physician."
)


def build_client_plan(request: dict[str, Any]) -> dict[str, Any]:
    client_name = str(request.get("client_name") or "Client")
    goal = str(request.get("goal") or "general fitness")
    diet = str(request.get("diet") or "balanced")
    allergies = [str(item) for item in request.get("allergies") or []]
    calories = max(800, min(6000, int(request.get("calorie_target") or 2200)))
    protein_target = max(80, round(calories * 0.065))

    workout_plan = build_workout_plan({
        "goal": goal,
        "days_per_week": request.get("days_per_week", 3),
        "equipment": request.get("equipment", ["bodyweight"]),
        "experience_level": request.get("experience_level", "beginner"),
        "limitations": request.get("limitations", []),
        "session_minutes": request.get("session_minutes", 60),
    })
    allergy_note = f"Exclude: {', '.join(allergies)}." if allergies else "No allergies supplied."
    return {
        "client_name": client_name,
        "goal": goal,
        "nutrition_plan": {
            "summary": f"A practical {diet} structure targeting about {calories} kcal and {protein_target} g protein daily.",
            "calorie_target": calories,
            "protein_target_g": protein_target,
            "meal_structure": ["Protein-centered breakfast", "Balanced lunch", "Training-aware snack", "Vegetable-forward dinner"],
            "diet": diet,
            "allergy_guidance": allergy_note,
            "guidance_disclaimer": NUTRITION_GUIDANCE_NOTE,
        },
        "workout_plan": workout_plan,
        "shopping_strategy": {
            "summary": "Build the weekly shop around repeatable proteins, produce, high-fiber carbohydrates, and simple training snacks.",
            "priority_categories": ["lean proteins", "produce", "high-fiber carbohydrates", "dairy or alternatives", "healthy fats"],
            "weekly_prep": ["Choose two batch proteins", "Prep two vegetables", "Portion two grab-and-go snacks"],
            "starter_items": [
                {"name": "lean protein", "quantity": "4 servings", "category": "proteins"},
                {"name": "mixed vegetables", "quantity": "7 servings", "category": "produce"},
                {"name": "high-fiber carbohydrate", "quantity": "4 servings", "category": "pantry"},
                {"name": "high-protein snack", "quantity": "5 servings", "category": "snacks"},
            ],
            "checkout_action": "Review substitutions, then prepare the approved list for checkout.",
        },
        "coach_notes": [
            "Confirm preferences, schedule, and recovery before assigning the plan.",
            "Review adherence and energy after the first week before changing calories or volume.",
            "Treat pain, medical conditions, and eating-disorder concerns as referral points—not coaching problems.",
        ],
    }
