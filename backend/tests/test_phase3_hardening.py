"""Regression tests for the Phase 3 review.

Each test pins a defect that was reproduced against the pre-review code.
"""

import threading
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app import db
from app.agent import CopilotRouter
from app.main import app
from app.services import usda
from app.services.coach_planner import build_client_plan
from app.services.persistence import ClientNotFound
from app.services.workout_planner import (
    EXERCISE_LIBRARY,
    MIN_EXERCISES_PER_DAY,
    build_workout_plan,
)


class WorkoutPlanConsistencyTests(unittest.TestCase):
    """A bodyweight request used to collapse every day to a single exercise, and
    the 'Upper Pull' day returned Dead Bug — a core exercise with no pulling."""

    def test_every_pattern_has_enough_bodyweight_options(self):
        for pattern, entries in EXERCISE_LIBRARY.items():
            bodyweight = [item for item in entries if item[1] == "bodyweight"]
            with self.subTest(pattern=pattern):
                self.assertGreaterEqual(
                    len(bodyweight),
                    MIN_EXERCISES_PER_DAY,
                    f"{pattern} cannot fill a bodyweight-only day",
                )

    def test_bodyweight_plans_are_not_starved(self):
        for days in range(1, 8):
            plan = build_workout_plan({"days_per_week": days, "equipment": ["bodyweight"]})
            for day in plan["weekly_split"]:
                with self.subTest(days=days, focus=day["focus"]):
                    self.assertGreaterEqual(len(day["exercises"]), MIN_EXERCISES_PER_DAY)

    def test_pull_days_contain_pulling_movements(self):
        for equipment in (["bodyweight"], ["dumbbells"], ["gym"]):
            plan = build_workout_plan({"days_per_week": 4, "equipment": equipment})
            pull_day = next(day for day in plan["weekly_split"] if "Pull" in day["focus"])
            names = " ".join(exercise["name"] for exercise in pull_day["exercises"]).lower()
            with self.subTest(equipment=equipment):
                self.assertTrue(
                    any(word in names for word in ("row", "pulldown", "curl", "y-t-w")),
                    f"pull day had no pulling movement: {names}",
                )

    def test_three_day_upper_day_trains_both_directions(self):
        plan = build_workout_plan({"days_per_week": 3, "equipment": ["gym"]})
        upper = plan["weekly_split"][0]
        names = " ".join(exercise["name"] for exercise in upper["exercises"]).lower()
        self.assertIn("press", names)
        self.assertTrue(any(word in names for word in ("row", "pulldown")))

    def test_duration_based_work_is_not_rescaled_into_sets(self):
        plan = build_workout_plan(
            {"days_per_week": 5, "equipment": ["gym"], "experience_level": "beginner"}
        )
        conditioning = plan["weekly_split"][4]
        walk = next(e for e in conditioning["exercises"] if e["name"] == "Incline Treadmill Walk")
        self.assertEqual(walk["sets"], 1, "a 15-20 min walk should not become 2 sets")

    def test_plans_are_framed_as_general_guidance(self):
        plan = build_workout_plan({"days_per_week": 3})
        self.assertIn("not medical advice", plan["guidance_disclaimer"].lower())

        client_plan = build_client_plan({"client_name": "A", "calorie_target": 2200})
        self.assertIn(
            "not medical", client_plan["nutrition_plan"]["guidance_disclaimer"].lower()
        )


class CoachClientCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_repeated_plans_reuse_one_client_profile(self):
        name = "Duplicate Guard Client"
        ids = {
            self.client.post("/coach/client-plan", json={"client_name": name})
            .json()["persistence"]["profile_id"]
            for _ in range(3)
        }
        self.assertEqual(len(ids), 1, "each call created another client row")

        roster = self.client.get("/coach/clients").json()["clients"]
        self.assertEqual(len([c for c in roster if c["client_name"] == name]), 1)

    def test_unknown_client_id_is_rejected_not_silently_replaced(self):
        response = self.client.post(
            "/coach/client-plan",
            json={"client_id": "00000000-0000-0000-0000-000000000000", "client_name": "Ghost"},
        )
        self.assertEqual(response.status_code, 404)

    def test_supplied_client_id_is_the_one_updated(self):
        created = self.client.post(
            "/coach/clients", json={"client_name": "Stable Client", "goal": "strength"}
        ).json()
        updated = self.client.post(
            "/coach/client-plan",
            json={"client_id": created["id"], "client_name": "Stable Client", "goal": "fat loss"},
        ).json()
        self.assertEqual(updated["persistence"]["profile_id"], created["id"])

    def test_client_plan_composes_workout_and_nutrition_consistently(self):
        payload = self.client.post(
            "/coach/client-plan",
            json={"client_name": "Composition Client", "days_per_week": 4, "equipment": ["gym"]},
        ).json()
        self.assertEqual(len(payload["workout_plan"]["weekly_split"]), 4)
        self.assertEqual(
            payload["nutrition_plan"]["calorie_target"],
            2200,
            "nutrition target drifted from the request",
        )


class CheckoutIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_dangling_client_id_is_refused(self):
        """checkout_sessions.client_id is a FK. SQLite used to accept a dangling id
        while Postgres raised IntegrityError and returned a 500."""
        response = self.client.post(
            "/checkout/prepare", json={"client_id": "not-a-real-client", "items": ["milk"]}
        )
        self.assertEqual(response.status_code, 404)

    def test_empty_basket_is_a_validation_error(self):
        self.assertEqual(self.client.post("/checkout/prepare", json={}).status_code, 422)

    def test_valid_checkout_round_trips(self):
        prepared = self.client.post("/checkout/prepare", json={"items": ["milk", "eggs"]}).json()
        fetched = self.client.get(f"/checkout/{prepared['checkout_id']}").json()
        self.assertEqual(fetched["item_count"], 2)


class CopilotRoutingSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_upstream_failure_is_not_reported_as_success(self):
        """An OpenAI outage used to return 200 with a canned message."""

        def failing_run_ai(instructions, user_input):
            raise HTTPException(status_code=502, detail="AI request failed: quota exceeded")

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch("app.main.run_ai", side_effect=failing_run_ai):
                response = self.client.post(
                    "/copilot/chat", json={"message": "give me a recipe with chicken"}
                )

        self.assertEqual(response.status_code, 502)
        self.assertIn("quota exceeded", response.json()["detail"])

    def test_missing_tool_context_still_falls_back_and_explains_why(self):
        with patch.dict("os.environ", {}, clear=True):
            response = self.client.post(
                "/copilot/chat", json={"message": "what should i buy this week"}
            )
        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["mode"], "routing_fallback")
        self.assertIn("shopping_list", payload["routing_error"])

    def test_successful_route_reports_no_routing_error(self):
        with patch.dict("os.environ", {}, clear=True):
            payload = self.client.post(
                "/copilot/chat",
                json={"message": "Build a 4 day workout plan", "context": {"equipment": ["gym"]}},
            ).json()
        self.assertEqual(payload["intent"], "workout_plan")
        self.assertIsNone(payload["routing_error"])

    def test_router_still_absorbs_context_errors(self):
        router = CopilotRouter(
            ai_runner=lambda instructions, prompt: (_ for _ in ()).throw(RuntimeError("offline"))
        )
        result = router.route("Tell me something useful", {"goal": "balanced nutrition"})
        self.assertEqual(result["mode"], "routing_fallback")


class ResponseContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_phase3_endpoints_declare_pydantic_response_models(self):
        """A bare `-> dict[str, Any]` annotation makes FastAPI set response_model to
        dict, so presence alone proves nothing: require a real BaseModel."""
        paths = {
            "/workout-plan",
            "/coach/client-plan",
            "/coach/clients",
            "/checkout/prepare",
            "/checkout/instacart",
            "/copilot/chat",
            "/profile/{user_id}",
            "/bag/{user_id}",
            "/plans/{user_id}",
        }
        documented = {
            route.path
            for route in app.routes
            if isinstance(getattr(route, "response_model", None), type)
            and issubclass(route.response_model, BaseModel)
        }
        self.assertEqual(paths - documented, set(), "endpoints without a Pydantic response model")

    def test_response_models_do_not_silently_drop_fields(self):
        """response_model filters undeclared keys, so an incomplete model is a
        silent API break. Spot-check the keys the frontend reads."""
        plan = self.client.post(
            "/coach/client-plan", json={"client_name": "Contract Client"}
        ).json()
        for key in ("client_name", "goal", "nutrition_plan", "workout_plan", "shopping_strategy", "coach_notes", "persistence"):
            self.assertIn(key, plan)
        self.assertIn("profile_id", plan["persistence"])
        self.assertIn("weekly_split", plan["workout_plan"])

        prepared = self.client.post("/checkout/prepare", json={"items": ["milk"]}).json()
        for key in ("checkout_id", "retailer", "status", "item_count", "items", "checkout_url", "next_action"):
            self.assertIn(key, prepared)

        bag = self.client.get("/bag/demo-user").json()
        for key in ("user_id", "items", "count"):
            self.assertIn(key, bag)

    def test_validation_errors_name_the_offending_field(self):
        """The frontend renders these; they must carry a usable loc/msg."""
        response = self.client.post(
            "/coach/client-plan", json={"client_name": "X", "calorie_target": 99999}
        )
        self.assertEqual(response.status_code, 422)
        detail = response.json()["detail"]
        self.assertIsInstance(detail, list)
        self.assertIn("calorie_target", detail[0]["loc"])
        self.assertTrue(detail[0]["msg"])


class UsdaGroundingTests(unittest.TestCase):
    def setUp(self):
        usda._lookup_cache.clear()

    def tearDown(self):
        usda._lookup_cache.clear()

    def test_energy_prefers_kcal_over_kilojoules(self):
        food = {
            "foodNutrients": [
                {"nutrientName": "Energy", "unitName": "kJ", "value": 690},
                {"nutrientName": "Energy", "unitName": "KCAL", "value": 165},
            ]
        }
        self.assertEqual(usda._extract_nutrient(food, "energy", unit="KCAL"), 165.0)

    def test_repeated_ingredients_are_looked_up_once(self):
        plan = {
            "days": [
                {"day": d, "meals": [{"name": "m", "ingredients": ["oats", "egg", "oats"]}]}
                for d in range(1, 6)
            ]
        }
        with patch.object(
            usda, "_lookup_food_uncached", wraps=usda._lookup_food_uncached
        ) as spy:
            usda.enrich_meal_plan_with_usda(plan)
        self.assertEqual(spy.call_count, 2, "duplicate ingredients hit the network again")

    def test_reference_values_do_not_overwrite_the_model_estimate(self):
        plan = {
            "days": [
                {
                    "day": 1,
                    "meals": [
                        {
                            "name": "Bowl",
                            "estimated_calories": 550,
                            "estimated_protein_g": 45,
                            "ingredients": ["chicken breast", "brown rice", "broccoli"],
                        }
                    ],
                }
            ]
        }
        meal = usda.enrich_meal_plan_with_usda(plan)["days"][0]["meals"][0]
        self.assertEqual(meal["estimated_calories"], 550)
        self.assertEqual(meal["estimated_protein_g"], 45)
        self.assertIn("not portion-scaled", meal["reference_nutrition"]["basis"])
        self.assertNotEqual(
            meal["nutrition_source"], "USDA", "unscaled sums must not be labelled plain USDA"
        )

    def test_grounding_block_states_its_basis(self):
        plan = {"days": [{"day": 1, "meals": [{"name": "m", "ingredients": ["oats"]}]}]}
        grounding = usda.enrich_meal_plan_with_usda(plan)["nutrition_grounding"]
        self.assertIn("estimates", grounding["basis"].lower())


class DatabaseInitTests(unittest.TestCase):
    def test_concurrent_first_requests_do_not_see_a_half_built_factory(self):
        """The old check-then-set let a thread pass the _engine guard while
        _session_factory was still None -> TypeError: 'NoneType' is not callable."""
        original_engine, original_factory = db._engine, db._session_factory
        db._engine, db._session_factory = None, None
        errors: list[BaseException] = []
        barrier = threading.Barrier(8)

        def worker():
            try:
                barrier.wait()
                with db.session_scope() as session:
                    session.execute(db.Base.metadata.sorted_tables[0].select().limit(1))
            except BaseException as exc:  # noqa: BLE001 - recorded and re-raised below
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        try:
            self.assertEqual(errors, [])
        finally:
            db._engine, db._session_factory = original_engine, original_factory

    def test_sqlite_enforces_foreign_keys_like_postgres(self):
        db.init_db()
        if not db.database_url().startswith("sqlite"):
            self.skipTest("only meaningful on the SQLite fallback")
        from sqlalchemy import text

        with db.session_scope() as session:
            self.assertEqual(session.execute(text("PRAGMA foreign_keys")).scalar(), 1)


class ClientOwnershipTests(unittest.TestCase):
    def test_clients_are_addressed_within_an_owner_scope(self):
        from app.services.persistence import create_or_update_client, get_client

        owned = create_or_update_client({"client_name": "Owner A Client"}, "owner-a")
        self.assertIsNotNone(get_client(owned["id"], "owner-a"))
        # Another owner must not be able to read or overwrite it by id.
        self.assertIsNone(get_client(owned["id"], "owner-b"))
        with self.assertRaises(ClientNotFound):
            create_or_update_client(
                {"client_id": owned["id"], "client_name": "PWNED"}, "owner-b"
            )
        self.assertEqual(get_client(owned["id"], "owner-a")["client_name"], "Owner A Client")


if __name__ == "__main__":
    unittest.main()
