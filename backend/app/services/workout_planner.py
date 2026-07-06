from __future__ import annotations

from typing import Any


EXERCISE_LIBRARY = {
    "push": [
        ("Dumbbell Bench Press", "dumbbells", "3", "8-12"),
        ("Incline Push-Up", "bodyweight", "3", "8-15"),
        ("Seated Shoulder Press", "dumbbells", "3", "8-12"),
        ("Cable Triceps Pressdown", "gym", "2", "10-15"),
    ],
    "pull": [
        ("Lat Pulldown", "gym", "3", "8-12"),
        ("One-Arm Dumbbell Row", "dumbbells", "3", "8-12 each"),
        ("Chest-Supported Row", "gym", "3", "10-12"),
        ("Dumbbell Curl", "dumbbells", "2", "10-15"),
    ],
    "lower": [
        ("Goblet Squat", "dumbbells", "3", "8-12"),
        ("Romanian Deadlift", "dumbbells", "3", "8-12"),
        ("Leg Press", "gym", "3", "10-15"),
        ("Reverse Lunge", "bodyweight", "2", "8-10 each"),
    ],
    "full": [
        ("Goblet Squat", "dumbbells", "3", "8-12"),
        ("Dumbbell Bench Press", "dumbbells", "3", "8-12"),
        ("One-Arm Dumbbell Row", "dumbbells", "3", "8-12 each"),
        ("Dead Bug", "bodyweight", "2", "8-10 each"),
    ],
    "conditioning": [
        ("Incline Treadmill Walk", "gym", "1", "15-20 min"),
        ("Farmer Carry", "dumbbells", "4", "30-45 sec"),
        ("Low-Impact Step-Up", "bodyweight", "3", "10 each"),
    ],
}


def _available(item: tuple[str, str, str, str], equipment: set[str]) -> bool:
    requirement = item[1]
    return requirement == "bodyweight" or requirement in equipment or "gym" in equipment


def _split(days: int) -> list[tuple[str, str]]:
    splits = {
        1: [("Full Body", "full")],
        2: [("Full Body A", "full"), ("Full Body B", "full")],
        3: [("Upper Body", "push"), ("Lower Body", "lower"), ("Full Body", "full")],
        4: [("Upper Push", "push"), ("Lower Body", "lower"), ("Upper Pull", "pull"), ("Full Body", "full")],
        5: [("Push", "push"), ("Lower Body", "lower"), ("Pull", "pull"), ("Full Body", "full"), ("Conditioning", "conditioning")],
        6: [("Push A", "push"), ("Pull A", "pull"), ("Lower A", "lower"), ("Push B", "push"), ("Pull B", "pull"), ("Lower B", "lower")],
        7: [("Full Body", "full"), ("Conditioning", "conditioning"), ("Upper Push", "push"), ("Lower Body", "lower"), ("Upper Pull", "pull"), ("Full Body Light", "full"), ("Recovery", "conditioning")],
    }
    return splits[days]


def build_workout_plan(request: dict[str, Any]) -> dict[str, Any]:
    goal = str(request.get("goal") or "general fitness")
    days = max(1, min(7, int(request.get("days_per_week") or 3)))
    experience = str(request.get("experience_level") or "beginner").lower()
    session_minutes = max(20, min(120, int(request.get("session_minutes") or 60)))
    equipment_list = [str(item).lower() for item in request.get("equipment") or ["bodyweight"]]
    equipment = set(equipment_list) | {"bodyweight"}
    limitations = [str(item) for item in request.get("limitations") or []]
    exercise_limit = 3 if session_minutes < 40 else 4 if session_minutes < 75 else 5
    sets_adjustment = -1 if experience == "beginner" else 1 if experience == "advanced" else 0

    weekly_split = []
    for index, (focus, library_key) in enumerate(_split(days), start=1):
        exercises = []
        candidates = [item for item in EXERCISE_LIBRARY[library_key] if _available(item, equipment)]
        if not candidates:
            candidates = [item for item in EXERCISE_LIBRARY["full"] if item[1] == "bodyweight"]
        for name, _, base_sets, reps in candidates[:exercise_limit]:
            sets = max(2, min(5, int(base_sets) + sets_adjustment))
            exercises.append({
                "name": name,
                "sets": sets,
                "reps": reps,
                "notes": "Finish with 2-3 good reps in reserve; prioritize controlled technique.",
            })
        weekly_split.append({"day": index, "focus": focus, "exercises": exercises})

    limitation_note = (
        "Modify or replace movements that aggravate: " + ", ".join(limitations) + "."
        if limitations
        else "Stop any movement that causes sharp or worsening pain."
    )
    return {
        "summary": f"A {days}-day {experience} plan for {goal}, designed for roughly {session_minutes}-minute sessions.",
        "weekly_split": weekly_split,
        "progression_notes": "When every set reaches the top of the rep range with solid form, add the smallest available load or one repetition next session.",
        "safety_notes": f"Warm up for 5-10 minutes and use conservative starting loads. {limitation_note} Seek qualified guidance for injuries or medical restrictions.",
    }
