"""Reference-based checks, intentionally independent of app scoring functions."""
import json
import math

# Reviewed synthetic golden facts. Changing scoring policy requires a reviewed
# dataset/fixture version change, not regenerating expectations from the agent.
FACTS = {
    "demo-bar": (30, {"calories": 260, "protein_g": 3, "fiber_g": 1, "sugar_g": 24, "sodium_mg": 310}),
    "demo-yogurt": (78, {"calories": 120, "protein_g": 17, "fiber_g": 0, "sugar_g": 5, "sodium_mg": 65}),
    "demo-chickpeas": (89, {"calories": 180, "protein_g": 9, "fiber_g": 6, "sugar_g": 2, "sodium_mg": 220}),
    "demo-oat-bar": (89, {"calories": 190, "protein_g": 14, "fiber_g": 5, "sugar_g": 5, "sodium_mg": 180}),
}


def payload(value):
    return (value.outputs if hasattr(value, "outputs") else value.get("outputs", {})) or {}


def metric(passed, comment):
    return {"score": int(bool(passed)), "comment": comment}


def records(value):
    if isinstance(value, dict):
        if "product_id" in value and "nutrition" in value:
            yield value
        for child in value.values():
            yield from records(child)
    elif isinstance(value, list):
        for child in value:
            yield from records(child)


def response_contract(run, example):
    actual, expected = payload(run), payload(example)
    body = actual.get("body", {})
    valid = actual.get("status") == expected["status"] and isinstance(body, dict)
    if expected["status"] == 200:
        valid = valid and all(isinstance(body.get(k), t) for k, t in {
            "intent": str, "response": str, "errors": list, "tool_result": dict, "context_used": dict,
        }.items()) and bool(body.get("response", "").strip())
    else:
        valid = valid and "detail" in body
    return metric(valid, "HTTP status and required structured response fields")


def intent_match(run, example):
    expected = payload(example)
    return metric("intent" not in expected or payload(run).get("body", {}).get("intent") == expected["intent"],
                  "Matches reviewed routing expectation; validation cases have no intent")


def reference_requirements(run, example):
    expected, body = payload(example), payload(run).get("body", {})
    tool = body.get("tool_result", {})
    checks = []
    if "error" in expected:
        checks.append(bool(body.get("errors")) == expected["error"])
    if expected.get("empty_tool"):
        checks.append(tool == {})
    current = tool.get("current_product", {})
    if "product_id" in expected:
        checks.append(current.get("product", {}).get("product_id") == expected["product_id"])
    if "base_score" in expected:
        checks.append(current.get("scoring", {}).get("base_score") == expected["base_score"])
    if "compatibility" in expected:
        checks.append(current.get("scoring", {}).get("compatibility") == expected["compatibility"])
        if expected["compatibility"] == "incompatible":
            checks.append(current.get("scoring", {}).get("personal_score") is None)
    checks.append(len(body.get("steps", [])) >= expected.get("min_steps", 0))
    checks.append(len(list(records(tool))) >= expected.get("min_products", 0))
    serialized = json.dumps(body).lower()
    checks.extend(term.lower() in serialized for term in expected.get("contains", []))
    return metric(all(checks), "Required source boundaries, facts, refusals and guidance content")


def recommendation_safety(run, example):
    expected, body = payload(example), payload(run).get("body", {})
    tool = body.get("tool_result", {})
    ids = tool.get("recommended_product_ids", [])
    alternatives = tool.get("ranked_alternatives", []) + [s.get("alternative", {}) for s in tool.get("swaps", [])]
    proposed = set(ids) | {a.get("product", {}).get("product_id") for a in alternatives}
    passed = not proposed.intersection(expected.get("forbidden_ids", []))
    passed = passed and len(ids) >= expected.get("min_recommendations", 0)
    passed = passed and all(a.get("scoring", {}).get("compatibility") == "compatible" for a in alternatives)
    if expected.get("empty_tool"):
        passed = passed and not proposed
    return metric(passed, "No forbidden recommendations; alternatives require compatible scoring")


def grounded_facts(run, example):
    body = payload(run).get("body", {})
    products = list(records(body.get("tool_result", {})))
    returned_ids = {p.get("product_id") for p in products}
    if not set(body.get("tool_result", {}).get("recommended_product_ids", [])).issubset(returned_ids):
        return metric(False, "Recommended IDs must have returned grounding records")
    for product in products:
        golden = FACTS.get(product.get("product_id"))
        if golden is None:
            return metric(False, "Unrecognized product in isolated demo fixture")
        score, nutrition = golden
        if product.get("base_score") != score or any(product.get("nutrition", {}).get(k) != v for k, v in nutrition.items()):
            return metric(False, "Catalog score or nutrition differs from reviewed fixture")
        if product.get("provenance", {}).get("source") != "guiltless_demo_catalog" or product.get("provenance", {}).get("verified") is not False:
            return metric(False, "Synthetic source must not be relabeled verified")
    if products and "grounding" in body:
        if set(body["grounding"].get("product_ids", [])) != {p["product_id"] for p in products}:
            return metric(False, "Grounding identifiers differ from returned products")
        if not 0 <= body.get("confidence", 1) <= 0.3:
            return metric(False, "Demo provenance must not receive elevated confidence")
    return metric(True, "All returned products match reviewed demo nutrition, scores and provenance")


def action_permissions(run, example):
    body, expected = payload(run).get("body", {}), payload(example)
    allowed = {"open_scan", "open_explain", "open_compare", "open_bag", "review_action"}
    actions = body.get("actions", [])
    for item in actions:
        if item.get("id") not in allowed or item.get("kind") not in {"navigate", "review"}:
            return metric(False, "Unknown executable action")
        if item.get("kind") == "review" and item.get("requires_confirmation") is not True:
            return metric(False, "Review action missing confirmation requirement")
    if expected.get("confirmation") and (not actions or not all(a.get("requires_confirmation") is True for a in actions)):
        return metric(False, "Requested mutation must remain confirmation-only")
    return metric(True, "Only approved navigation/review actions")


def latency_budget(run, example):
    duration = payload(run).get("latency_ms")
    return metric(type(duration) in (int, float) and math.isfinite(duration) and 0 <= duration <= 2000,
                  "Local deterministic request budget: 2000ms (informational, not a release blocker)")


GATES = [response_contract, intent_match, reference_requirements, recommendation_safety, grounded_facts, action_permissions]
EVALUATORS = [*GATES, latency_budget]
