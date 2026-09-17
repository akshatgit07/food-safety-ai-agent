from __future__ import annotations

from typing import Any


MIN_EXERCISES_PER_DAY = 3

# Every pattern must keep at least MIN_EXERCISES_PER_DAY bodyweight-only entries,
# otherwise a bodyweight-only request filters the day down to a single movement.
EXERCISE_LIBRARY = {
    "push": [
        ("Dumbbell Bench Press", "dumbbells", "3", "8-12"),
        ("Incline Push-Up", "bodyweight", "3", "8-15"),
        ("Seated Shoulder Press", "dumbbells", "3", "8-12"),
        ("Cable Triceps Pressdown", "gym", "2", "10-15"),
        ("Pike Push-Up", "bodyweight", "3", "6-12"),
        ("Bench Dip", "bodyweight", "2", "8-12"),
        ("Push-Up", "bodyweight", "3", "8-15"),
    ],
    "pull": [
        ("Lat Pulldown", "gym", "3", "8-12"),
        ("One-Arm Dumbbell Row", "dumbbells", "3", "8-12 each"),
        ("Chest-Supported Row", "gym", "3", "10-12"),
        ("Dumbbell Curl", "dumbbells", "2", "10-15"),
        ("Inverted Row", "bodyweight", "3", "8-12"),
        ("Prone Y-T-W Raise", "bodyweight", "2", "10-12"),
        ("Towel Door Row", "bodyweight", "3", "10-15"),
    ],
    "lower": [
        ("Goblet Squat", "dumbbells", "3", "8-12"),
        ("Romanian Deadlift", "dumbbells", "3", "8-12"),
        ("Leg Press", "gym", "3", "10-15"),
        ("Reverse Lunge", "bodyweight", "2", "8-10 each"),
        ("Bodyweight Squat", "bodyweight", "3", "10-15"),
        ("Glute Bridge", "bodyweight", "3", "10-15"),
        ("Split Squat", "bodyweight", "3", "8-12 each"),
    ],
    "upper": [
        ("Dumbbell Bench Press", "dumbbells", "3", "8-12"),
        ("One-Arm Dumbbell Row", "dumbbells", "3", "8-12 each"),
        ("Seated Shoulder Press", "dumbbells", "3", "8-12"),
        ("Lat Pulldown", "gym", "3", "8-12"),
        ("Push-Up", "bodyweight", "3", "8-15"),
        ("Inverted Row", "bodyweight", "3", "8-12"),
        ("Pike Push-Up", "bodyweight", "2", "6-12"),
    ],
    "full": [
        ("Goblet Squat", "dumbbells", "3", "8-12"),
        ("Dumbbell Bench Press", "dumbbells", "3", "8-12"),
        ("One-Arm Dumbbell Row", "dumbbells", "3", "8-12 each"),
        ("Dead Bug", "bodyweight", "2", "8-10 each"),
        ("Bodyweight Squat", "bodyweight", "3", "10-15"),
        ("Push-Up", "bodyweight", "3", "8-15"),
        ("Inverted Row", "bodyweight", "3", "8-12"),
    ],
    "conditioning": [
        ("Incline Treadmill Walk", "gym", "1", "15-20 min"),
        ("Farmer Carry", "dumbbells", "4", "30-45 sec"),
        ("Low-Impact Step-Up", "bodyweight", "3", "10 each"),
        ("Brisk Walk", "bodyweight", "1", "15-20 min"),
        ("Marching in Place", "bodyweight", "3", "45-60 sec"),
    ],
}

GUIDANCE_NOTE = (
    "This plan is general fitness guidance, not medical advice. It is not a diagnosis or "
    "treatment plan. Check with a qualified professional before starting if you have an "
    "injury, a medical condition, or are pregnant."
)


def _available(item: tuple[str, str, str, str], equipment: set[str]) -> bool:
    requirement = item[1]
    return requirement == "bodyweight" or requirement in equipment or "gym" in equipment


def _is_duration(reps: str) -> bool:
    return any(unit in reps.lower() for unit in ("min", "sec"))


def _top_up(candidates: list[tuple[str, str, str, str]], library_key: str) -> list[tuple[str, str, str, str]]:
    topped = list(candidates)
    pools = [library_key, "full"] if library_key != "full" else ["full"]
    for pool in pools:
        for item in EXERCISE_LIBRARY[pool]:
            if len(topped) >= MIN_EXERCISES_PER_DAY:
                return topped
            if item[1] == "bodyweight" and item not in topped:
                topped.append(item)
    return topped


def _split(days: int) -> list[tuple[str, str]]:
    splits = {
        1: [("Full Body", "full")],
        2: [("Full Body A", "full"), ("Full Body B", "full")],
        3: [("Upper Body", "upper"), ("Lower Body", "lower"), ("Full Body", "full")],
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
        if len(candidates) < MIN_EXERCISES_PER_DAY:
            # Top up from the same movement pattern's bodyweight options rather than
            # collapsing the day onto a single unrelated exercise.
            candidates = _top_up(candidates, library_key)
        for name, _, base_sets, reps in candidates[:exercise_limit]:
            sets = int(base_sets) if _is_duration(reps) else max(2, min(5, int(base_sets) + sets_adjustment))
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
        "guidance_disclaimer": GUIDANCE_NOTE,
    }
