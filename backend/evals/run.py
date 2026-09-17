"""Run: python -m evals.run [--publish --env-file ../.env.local]."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from evals.checks import EVALUATORS, GATES
from evals.runner import make_target

DATA = Path(__file__).parent / "data"


def load_cases(path):
    cases = json.loads(path.read_text())
    ids = [case["inputs"]["case_id"] for case in cases]
    if not cases or len(ids) != len(set(ids)):
        raise ValueError("Dataset must be nonempty with unique case IDs")
    return cases


@contextmanager
def isolated_target():
    # This entry point always overrides DATABASE_URL before importing the app.
    # Never run an evaluation against the local user's or Render's database.
    with tempfile.TemporaryDirectory(prefix="guiltless-eval-") as directory:
        os.environ["DATABASE_URL"] = "sqlite:///" + directory + "/eval.db"
        os.environ["LANGSMITH_TRACING"] = "false"
        os.environ["CATALOG_SEED_DEMO"] = "true"
        os.environ["CATALOG_VECTOR_BACKEND"] = "local"
        os.environ.pop("OPENAI_API_KEY", None)
        from app import db
        if db._session_factory is not None:
            raise RuntimeError("Run evaluations in a fresh process to isolate the database")
        from app.main import app
        from fastapi.testclient import TestClient
        try:
            with TestClient(app) as client:
                yield make_target(client)
        finally:
            if db._engine is not None:
                db._engine.dispose()


def score_cases(target, cases):
    rows = []
    for example in cases:
        try:
            actual = target(example["inputs"])
        except Exception as exc:
            actual = {"status": 0, "body": {}, "execution_error": type(exc).__name__}
        scores = {e.__name__: e({"outputs": actual}, example)["score"] for e in EVALUATORS}
        rows.append({"case_id": example["inputs"]["case_id"], "scores": scores, "latency_ms": actual.get("latency_ms"),
                     "passed": all(scores[e.__name__] == 1 for e in GATES)})
    return rows


def publish(path, cases, target, cli):
    from langsmith import Client, evaluate
    from langsmith.utils import LangSmithNotFoundError
    # Same env/endpoint credentials as the CLI. Only synthetic fixtures are sent.
    client = Client(hide_inputs=False, hide_outputs=False, auto_batch_tracing=False)
    suffix = hashlib.sha256(path.read_bytes()).hexdigest()[:10]
    name = f"guiltless-{path.stem}-{suffix}"
    try:
        dataset = client.read_dataset(dataset_name=name)  # Read-only SDK preflight.
    except LangSmithNotFoundError:
        subprocess.run([cli, "dataset", "upload", str(path), "--name", name,
                        "--description", "Synthetic Guiltless regression fixtures; no user conversations or medical validation."], check=True)
        dataset = client.read_dataset(dataset_name=name)
    examples = list(client.list_examples(dataset_id=dataset.id))
    expected = sorted(json.dumps({"inputs": c["inputs"], "outputs": c["outputs"]}, sort_keys=True) for c in cases)
    existing = sorted(json.dumps({"inputs": e.inputs, "outputs": e.outputs}, sort_keys=True) for e in examples)
    if expected != existing:
        raise RuntimeError("Remote dataset differs from reviewed fixture; refusing to overwrite")
    try:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except subprocess.CalledProcessError:
        revision = "unknown"
    experiment = evaluate(target, data=examples, client=client, evaluators=EVALUATORS,
                          experiment_prefix=f"guiltless-{path.stem}", max_concurrency=1,
                          metadata={"source_commit": revision, "fixture_hash": suffix,
                                    "evaluation_code_hash": hashlib.sha256(b"".join(p.read_bytes() for p in sorted(Path(__file__).parent.glob("*.py")))).hexdigest(),
                                    "environment": "isolated-sqlite", "synthetic": True,
                                    "production_validation": False})
    experiment.wait()
    results = list(experiment)
    expected_keys = {e.__name__ for e in EVALUATORS}
    if len(results) != len(examples):
        raise RuntimeError("Experiment did not evaluate every dataset example")
    for result in results:
        feedback = result["evaluation_results"]["results"]
        if {score.key for score in feedback} != expected_keys:
            raise RuntimeError("Experiment is missing required quality scores")
        if any(score.score != 1 for score in feedback if score.key in {e.__name__ for e in GATES}):
            raise RuntimeError("Published experiment failed a required quality gate")
    client.flush()
    return {"dataset": name, "dataset_id": str(dataset.id), "examples": len(examples),
            "experiment": experiment.experiment_name}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true", help="Upload synthetic datasets and experiment results to LangSmith")
    parser.add_argument("--env-file")
    parser.add_argument("--output", default="evals/reports/latest.json")
    parser.add_argument("--langsmith-cli", default=shutil.which("langsmith") or str(Path.home() / ".local/bin/langsmith"))
    args = parser.parse_args()
    if args.env_file:
        from dotenv import dotenv_values
        # Do not import DATABASE_URL, OpenAI credentials or production memory.
        for key, value in dotenv_values(args.env_file).items():
            if key in {"LANGSMITH_API_KEY", "LANGSMITH_ENDPOINT", "LANGSMITH_PROJECT", "LANGSMITH_WORKSPACE_ID"} and value:
                os.environ.setdefault(key, value)
    if args.publish and not os.getenv("LANGSMITH_API_KEY"):
        parser.error("LANGSMITH_API_KEY is required for publishing")
    if args.publish:
        subprocess.run([args.langsmith_cli, "dataset", "list", "--limit", "1"], check=True)
    report = {"environment": "isolated-sqlite", "synthetic": True, "suites": {}}
    with isolated_target() as target:
        for path in sorted(DATA.glob("*-v1.json")):
            cases = load_cases(path)
            rows = score_cases(target, cases)
            suite = {"cases": len(rows), "passed": sum(r["passed"] for r in rows), "rows": rows,
                     "metrics": {e.__name__: round(sum(r["scores"][e.__name__] for r in rows) / len(rows), 4) for e in EVALUATORS}}
            print(f"{path.stem}: {suite['passed']}/{suite['cases']} passed")
            for row in rows:
                if not row["passed"]:
                    print("FAIL", row["case_id"], [k for k, v in row["scores"].items() if v == 0])
            if args.publish:
                suite["langsmith"] = publish(path, cases, target, args.langsmith_cli)
                print(json.dumps(suite["langsmith"]))
            report["suites"][path.stem] = suite
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    raise SystemExit(0 if all(s["passed"] == s["cases"] for s in report["suites"].values()) else 1)


if __name__ == "__main__":
    main()
