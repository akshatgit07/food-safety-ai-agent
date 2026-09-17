# Screen-aware Guiltless helper

`POST /helper/chat` is a read-only helper facade over the existing v2 product
graph and a small, versioned app guide. It makes no new LLM requests for guidance.
It does not authenticate users, execute UI code, or mutate bags,
food logs, checkout, or preferences. Existing endpoints are unchanged.

```json
{
  "message": "Explain this score",
  "screen": "product_detail",
  "product_id": "demo-bar",
  "bag_product_ids": ["demo-bar", "demo-yogurt"],
  "goal": "high protein",
  "allergies": ["milk"],
  "score_source": "agent_catalog",
  "user_id": "demo-user"
}
```

Screens: `groceries`, `product_detail`, `comparison`, `bag`, `scan`,
`food_logging`, `tracker`. Responses include intent, response, steps, actions,
tool_result, limitations, errors, context_used, and guide_version.

Product/alternative/bag requests delegate to the existing grounded LangGraph.
Unknown identifiers never produce fabricated nutrition. Entered allergies and,
when `user_id` is supplied, saved profile allergies are passed into hard-constraint
checks. The saved goal is used when the request retains the default goal.
`score_source: mobile_app` deliberately blocks explaining the mobile score from
the agent's different algorithm. Nutrition scores are not safety probabilities.

App guidance is based on the supplied September 9 recording. The actual mobile
route names, saved-food behavior, scoring formula and app versions still need
review by the mobile developer. It is not a complete help knowledge base; unknown
questions return the current screen guide rather than improvised instructions.

## Preview

Choose **Ask Guiltless** next to the product/goal/bag context in the existing
decision workspace. The accessible native dialog opens as a bottom sheet. Select
a screen, ask a question, or use a prompt. Change context to discard stale results.
Navigation is restricted to four known local destinations. Actions requiring
confirmation only display a review notice; no confirmation/commerce API exists.

Start the backend and frontend with the existing setup, setting
`NEXT_PUBLIC_API_URL` to the backend origin. No new API keys are required. Test:

```bash
curl -X POST http://localhost:8000/helper/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"How do I use this screen?","screen":"scan"}'
```

Before embedding in the mobile app: implement authentication and user-scoped
authorization, map real product identifiers, review guide content, connect the
authoritative score factors, and map allowed actions to native navigation.
The demo endpoint must not be treated as a production account/mutation service.

## Behavior-aware suggestions

The UI records a small allowlist of declared behavior events through
`POST /app/events/{user_id}`. Events contain an event type, known screen, optional
product ID, and at most 4 KB of metadata. Screenshots, raw click streams, message
content, and arbitrary event types are rejected by design.

`POST /helper/proactive/{user_id}` accepts the current screen/product/bag context
and may return one timely suggestion. Current rules cover product score
explanations, interrupted comparisons, multi-item bag optimization, and scan
guidance. A dismissed suggestion is suppressed for 24 hours. The response explains
why it appeared, and the frontend treats event recording as optional so an
analytics failure never blocks the host workflow.

```bash
curl -X POST http://localhost:8000/app/events/demo-user \
  -H 'Content-Type: application/json' \
  -d '{"event_type":"screen_viewed","screen":"product_detail","product_id":"demo-bar"}'

curl -X POST http://localhost:8000/helper/proactive/demo-user \
  -H 'Content-Type: application/json' \
  -d '{"screen":"product_detail","product_id":"demo-bar","product_name":"Frosted Snack Bar","product_score":30}'
```

This is rule-based assistance, not covert behavioral profiling. Production use
still needs authenticated user IDs, retention/deletion controls, consent settings,
and native navigation mappings.
