# AppForge

AppForge takes a plain English description of an app and turns it into a complete, validated configuration — UI layout, API endpoints, database schema, auth rules, and business logic — ready to hand off to a runtime or code generator.

You describe what you want to build. It figures out the rest.

> Built on [Groq](https://console.groq.com) + LLaMA 3.3 70B. Completely free to run.

---

## What it actually does

You type something like:

> *"Build a CRM with login, contacts, a dashboard, role-based access for admins and sales reps, and a premium plan with Stripe payments."*

And you get back a structured JSON config covering every layer of that app — which pages exist and what's on them, what API endpoints are needed and what they accept, how the database should be structured, which roles can do what, and what business rules to enforce.

The important part is that this config is *consistent*. The UI fields map to real API endpoints. The API endpoints reference columns that actually exist in the database. The auth roles are the same everywhere. That sounds obvious, but it's exactly what breaks when you ask a language model to do all of this in one shot.

---

## Why it's built this way

The naive approach — one big prompt, one big output — produces output that looks right but isn't. You end up with API routes that reference DB fields that were never defined, or UI forms pointing at endpoints that don't exist. The model is pattern-matching, not reasoning about consistency.

AppForge treats this as a compiler problem. Each stage has a single, narrow job: extract intent, design the architecture, generate each schema, check everything is consistent, repair what isn't. No stage tries to do everything at once. The output of each stage becomes the input to the next, and the refinement pass specifically exists to catch the cross-layer mismatches that slip through.

The repair engine is worth calling out separately. When validation finds a problem, it doesn't throw everything away and start over — it identifies which layer is broken and fixes only that part, with the rest of the config as context. It's faster, uses fewer tokens, and produces more predictable results than a blind retry.

---

## Getting started

**1. Get a free Groq API key**

Head to [console.groq.com/keys](https://console.groq.com/keys), sign up, and generate a key. Takes about two minutes and costs nothing.

**2. Set up the project**


cd appforge
pip install -r requirements.txt
cp .env.example .env


Open `.env` and add your key — make sure there's no space after the `=`:

GROQ_API_KEY=gsk_your_key_here


**3. Start it**


python run.py


Open [http://localhost:8000](http://localhost:8000). The frontend and backend both run from that single command.

---

## The pipeline stages

When you hit Generate, your prompt goes through six stages in sequence:

**Intent Extraction** parses what you're asking for into a structured form — entities, user roles, features, whether auth or payments are involved. If something's ambiguous, it makes a reasonable assumption and logs it so you can see it in the output.

**Architecture Design** takes that intent and maps out the overall structure — what pages the app needs, how the API should be grouped, what the database looks like at a high level, and how roles map to access patterns.

**Schema Generation** is where the detailed contracts are produced: full UI page specs with component layouts and form fields, API endpoint definitions with request and response shapes, database table definitions with proper column types and foreign keys, and JWT auth configuration with per-role permissions.

**Refinement** reads everything that was just generated and looks for inconsistencies between layers. A UI field pointing at a nonexistent endpoint, an API route using a column that wasn't defined, a role referenced in the UI but missing from auth — this stage finds and fixes those before anything gets validated.

**Validation + Repair** runs a deterministic rule-based check across the full config. If it finds problems, the repair engine handles them layer by layer rather than regenerating from scratch.

**Execution Report** does a final sanity check — verifies that all the structural pieces needed to actually build the app are present, and lists the simulated API routes as confirmation.

---

## Project structure


appforge/
├── run.py                  # Everything starts here
├── requirements.txt
├── .env.example
├── backend/
│   ├── pipeline.py         # The six-stage compiler
│   ├── schemas.py          # Pydantic type definitions
│   ├── validator.py        # Cross-layer consistency checks
│   ├── repair.py           # Targeted repair engine
│   └── server.py           # Standalone FastAPI server
├── frontend/
│   └── index.html          # Full UI, single file, no build step
└── evaluation/
    └── evaluate.py         # 20-case benchmark suite




## API reference

**POST /generate**

Send a prompt, get a full config back.


{ "prompt": "Build a CRM with login, contacts, and admin analytics" }


Response shape:


{
  "status": "success",
  "intent": { "app_name": "...", "roles": ["admin", "sales"], ... },
  "config": {
    "ui_schema": { ... },
    "api_schema": { ... },
    "db_schema": { ... },
    "auth_schema": { ... },
    "business_logic": [ ... ]
  },
  "validation": {
    "is_valid": true,
    "errors": [],
    "warnings": []
  },
  "metrics": {
    "tokens_used": 11400,
    "retries": 0,
    "repair_count": 0,
    "stage_times": { "intent": 1.1, "architecture": 3.2, "total": 18.4 },
    "assumptions": []
  },
  "execution_report": {
    "status": "executable",
    "simulated_routes": ["GET /api/v1/contacts", "POST /api/v1/auth/login"]
  }
}


If your prompt is too vague, you'll get `"status": "clarification_needed"` with a message explaining what's missing rather than a broken output.

**POST /validate**

Pass any config JSON to run the consistency checker against it independently.

**GET /test-groq**

Hits the Groq API directly with a minimal request and tells you which model is working. Useful for debugging connection issues before running the full pipeline.

---

## Troubleshooting

**`Client.__init__() got an unexpected keyword argument 'proxies'`**

This is a version conflict between the `groq` library and a newer version of `httpx`. Fix it with:

```bash
pip install httpx==0.27.2
```

**`GROQ_API_KEY is not set` warning on the page even though your key is in `.env`**

Check that your `.env` file doesn't have a space after the equals sign. It should be `GROQ_API_KEY=gsk_...` not `GROQ_API_KEY= gsk_...`. The extra space becomes part of the key value.

**`Internal Server Error` when generating**

Open your terminal where `python run.py` is running — the full Python traceback will be printed there after the last fix. The most common causes are a rate limit on the free Groq tier (wait 60 seconds and try again) or a model that's been deprecated (the pipeline will automatically try fallback models, but you can also check which models are available at [console.groq.com](https://console.groq.com)).

**The stage indicators all turn red immediately**

This usually means the server isn't running or something crashed on startup. Check the terminal output from `python run.py` for any import errors.

---

## Running the evaluation suite


cd evaluation
python evaluate.py


This runs the pipeline against 20 test cases — 10 realistic product descriptions covering common app types, and 10 edge cases designed to stress-test the failure handling (vague prompts, contradictory requirements, underspecified inputs, pure jargon). Results land in `evaluation_results.json` with per-case breakdowns and aggregate metrics: success rate, executable rate, average latency, token usage, and retry/repair counts.

---

## A few design decisions

**Temperature is different per stage.** Intent extraction runs at 0.1 because you want deterministic parsing — the same prompt should produce the same structured output. Architecture gets 0.2 because some flexibility in structural choices is fine. Refinement and repair run at 0.1 because those are pure consistency-fixing operations where creativity is the enemy.

**The model has a fallback chain.** If LLaMA 3.3 70B is unavailable or returns an error, the pipeline automatically tries LLaMA 3.1 70B, then llama3-70b-8192, then Mixtral. The first model that responds successfully is used for the rest of that request.

**JSON extraction has three fallback levels.** The pipeline tries direct `json.loads()` first, then looks for a fenced code block, then uses regex to find the outermost `{...}` block. Most LLM outputs parse on the first try, but the fallbacks catch the cases where the model adds a preamble or explanation before the JSON.

---

## Extending the pipeline

Adding a new stage is straightforward. Define a method on `AppForgePipeline` in `backend/pipeline.py`:


def stage_security_review(self, schema: dict) -> dict:
    system = "You are a security auditor. Review this schema and flag vulnerabilities."
    raw = self._call_llm(system, f"Schema: {json.dumps(schema)}", temperature=0.1)
    return self._extract_json(raw)


Then call it from `run()` wherever it belongs in the sequence. The pattern is always the same: call `_call_llm`, extract JSON from the response, return the result. The retry logic and token tracking are handled automatically.
