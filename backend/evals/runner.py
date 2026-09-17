from time import perf_counter

ENDPOINTS = {"helper": "/helper/chat", "personalization": "/v2/copilot/chat"}


def make_target(client):
    def run_agent(inputs: dict) -> dict:
        if inputs["suite"] not in ENDPOINTS:
            raise ValueError("Unsupported evaluation suite")
        started = perf_counter()
        response = client.post(ENDPOINTS[inputs["suite"]], json=inputs["request"])
        return {"status": response.status_code, "body": response.json(),
                "latency_ms": round((perf_counter() - started) * 1000, 3)}
    return run_agent
