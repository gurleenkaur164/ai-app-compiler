"""
AppForge Pipeline - A multi-stage compiler for natural language → working app configs
Stages: Intent → Architecture → Schema → Refinement → Validation → Output
"""

import json
import time
import re
from typing import Any
from groq import Groq
from schemas import AppConfig, ValidationResult
from validator import SchemaValidator
from repair import RepairEngine

class AppForgePipeline:
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key)
        self.validator = SchemaValidator()
        self.repair = RepairEngine(self.client)
        # Primary model — fallback list if this fails
        self.model = "llama-3.3-70b-versatile"
        self.fallback_models = ["llama-3.1-70b-versatile", "llama3-70b-8192", "mixtral-8x7b-32768"]
        self.metrics = {
            "retries": 0,
            "repair_count": 0,
            "stage_times": {},
            "tokens_used": 0,
            "assumptions": []
        }

    def _call_llm(self, system: str, user: str, temperature: float = 0.2) -> str:
        """Centralized LLM call with token tracking and model fallback."""
        models_to_try = [self.model] + self.fallback_models
        last_error = None
        for model in models_to_try:
            try:
                resp = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user}
                    ],
                    temperature=temperature,
                    max_tokens=4000
                )
                if model != self.model:
                    print(f"[AppForge] Using fallback model: {model}")
                    self.model = model  # stick with working model
                self.metrics["tokens_used"] += resp.usage.total_tokens
                return resp.choices[0].message.content.strip()
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                # Only try fallback on model-not-found or deprecation errors
                if any(x in err_str for x in ["model", "not found", "decommissioned", "deprecated"]):
                    print(f"[AppForge] Model {model} failed: {e}, trying next...")
                    continue
                # For other errors (rate limit, auth, network) raise immediately
                raise
        raise RuntimeError(f"All models failed. Last error: {last_error}")

    def _extract_json(self, text: str) -> dict:
        """Robustly extract JSON from LLM output."""
        # Try direct parse
        try:
            return json.loads(text)
        except:
            pass
        # Try code block extraction
        match = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', text)
        if match:
            try:
                return json.loads(match.group(1))
            except:
                pass
        # Try finding first { ... } block
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group(0))
            except:
                pass
        raise ValueError(f"Could not extract JSON from response: {text[:300]}")

    # ─────────────────────────────────────────────
    # STAGE 1 — Intent Extraction
    # ─────────────────────────────────────────────
    def stage_intent(self, prompt: str) -> dict:
        t0 = time.time()
        system = """You are an expert software requirements analyst.
Extract structured intent from a natural language app description.
Return ONLY valid JSON, no explanation, no markdown fences.

Schema:
{
  "app_name": "string",
  "app_type": "string (crm|ecommerce|saas|dashboard|social|other)",
  "core_features": ["list of main features"],
  "entities": ["list of data entities e.g. User, Product, Order"],
  "roles": ["list of user roles"],
  "auth_required": true,
  "payment_required": true,
  "assumptions": ["list of assumptions made for vague parts"]
}"""
        user = f"Extract intent from this app description:\n\n{prompt}"
        raw = self._call_llm(system, user, temperature=0.1)
        result = self._extract_json(raw)
        self.metrics["assumptions"].extend(result.get("assumptions", []))
        self.metrics["stage_times"]["intent"] = round(time.time() - t0, 2)
        return result

    # ─────────────────────────────────────────────
    # STAGE 2 — System Design / Architecture
    # ─────────────────────────────────────────────
    def stage_architecture(self, intent: dict) -> dict:
        t0 = time.time()
        system = """You are a senior software architect.
Given a structured intent, design the full application architecture.
Return ONLY valid JSON, no explanation, no markdown fences.

Schema:
{
  "pages": [{"name": "string", "path": "string", "access": ["roles"], "components": ["list"]}],
  "api_groups": [{"group": "string", "base_path": "string", "endpoints": [
    {"method": "GET|POST|PUT|DELETE", "path": "string", "description": "string",
     "auth_required": true, "roles": ["list"], "request_body": {}, "response": {}}
  ]}],
  "db_tables": [{"name": "string", "fields": [
    {"name": "string", "type": "string", "required": true, "unique": false, "foreign_key": null}
  ], "relations": [{"type": "has_many|belongs_to|many_to_many", "target": "string"}]}],
  "auth": {"provider": "jwt", "roles": ["list"], "permissions": {}}
}"""
        user = f"Design architecture for this intent:\n\n{json.dumps(intent, indent=2)}"
        raw = self._call_llm(system, user, temperature=0.2)
        result = self._extract_json(raw)
        self.metrics["stage_times"]["architecture"] = round(time.time() - t0, 2)
        return result

    # ─────────────────────────────────────────────
    # STAGE 3 — Schema Generation
    # ─────────────────────────────────────────────
    def stage_schema(self, intent: dict, arch: dict) -> dict:
        t0 = time.time()
        system = """You are a schema generation engine.
Given intent and architecture, produce a complete, cross-consistent schema config.
Return ONLY valid JSON, no explanation, no markdown fences.

Produce:
{
  "ui_schema": {
    "theme": {"primary_color": "#hex", "font": "string", "mode": "light|dark"},
    "pages": [{"name":"string","path":"string","layout":"string","sections":[
      {"type":"form|table|chart|card|hero","title":"string","fields":[
        {"name":"string","type":"text|email|password|select|number|date|file","label":"string",
         "required":true,"api_source":null,"options":[]}
      ]}
    ]}]
  },
  "api_schema": {
    "base_url": "/api/v1",
    "endpoints": [{"id":"string","method":"string","path":"string","description":"string",
      "auth":true,"roles":[],"request_schema":{},"response_schema":{}}]
  },
  "db_schema": {
    "tables": [{"name":"string","fields":[
      {"name":"string","type":"VARCHAR|INT|BOOLEAN|TEXT|TIMESTAMP|DECIMAL","length":null,
       "primary_key":false,"nullable":false,"unique":false,"default":null,"foreign_key":null}
    ],"indexes":[]}]
  },
  "auth_schema": {
    "method": "JWT",
    "token_expiry": "24h",
    "roles": [],
    "permissions": {"role": {"resource": ["create","read","update","delete"]}}
  },
  "business_logic": [{"rule":"string","condition":"string","action":"string"}]
}"""
        user = f"Generate complete schema for:\nINTENT:\n{json.dumps(intent, indent=2)}\n\nARCHITECTURE:\n{json.dumps(arch, indent=2)}"
        raw = self._call_llm(system, user, temperature=0.15)
        result = self._extract_json(raw)
        self.metrics["stage_times"]["schema"] = round(time.time() - t0, 2)
        return result

    # ─────────────────────────────────────────────
    # STAGE 4 — Refinement (Cross-layer consistency)
    # ─────────────────────────────────────────────
    def stage_refinement(self, intent: dict, arch: dict, schema: dict) -> dict:
        t0 = time.time()
        system = """You are a consistency enforcement engine.
Review the complete schema across all layers and fix:
1. UI fields that reference non-existent API endpoints → fix references
2. API endpoints that use DB fields not in schema → add missing fields
3. Auth roles referenced in UI/API but not in auth_schema → add them
4. Business logic rules that contradict permissions → resolve conflicts
5. Any missing required fields across all layers

Return the COMPLETE fixed schema as valid JSON only, no markdown, no explanation.
Keep the same structure as the input schema."""
        user = f"""Review and fix cross-layer consistency:

INTENT: {json.dumps(intent, indent=2)}

CURRENT SCHEMA: {json.dumps(schema, indent=2)}"""
        raw = self._call_llm(system, user, temperature=0.1)
        result = self._extract_json(raw)
        self.metrics["stage_times"]["refinement"] = round(time.time() - t0, 2)
        return result

    # ─────────────────────────────────────────────
    # MAIN RUN — orchestrates all stages
    # ─────────────────────────────────────────────
    def run(self, prompt: str) -> dict:
        total_start = time.time()
        self.metrics = {"retries": 0, "repair_count": 0, "stage_times": {}, "tokens_used": 0, "assumptions": []}

        # Vagueness check
        if len(prompt.strip().split()) < 5:
            return {
                "status": "clarification_needed",
                "message": "Your prompt is too vague. Please describe: what the app does, who uses it, and key features.",
                "prompt": prompt
            }

        # Stage 1: Intent
        intent = self._run_stage("intent", lambda: self.stage_intent(prompt))

        # Stage 2: Architecture
        arch = self._run_stage("architecture", lambda: self.stage_architecture(intent))

        # Stage 3: Schema
        schema = self._run_stage("schema", lambda: self.stage_schema(intent, arch))

        # Stage 4: Refinement
        refined = self._run_stage("refinement", lambda: self.stage_refinement(intent, arch, schema))

        # Validation + Repair
        validation = self.validator.validate(refined)
        if not validation.is_valid:
            refined = self.repair.repair(refined, validation.errors, self._call_llm)
            self.metrics["repair_count"] += 1
            validation = self.validator.validate(refined)

        self.metrics["stage_times"]["total"] = round(time.time() - total_start, 2)

        return {
            "status": "success" if validation.is_valid else "partial",
            "intent": intent,
            "config": refined,
            "validation": {
                "is_valid": validation.is_valid,
                "errors": validation.errors,
                "warnings": validation.warnings
            },
            "metrics": self.metrics,
            "execution_report": self._generate_execution_report(refined, intent)
        }

    def _run_stage(self, name: str, fn) -> dict:
        """Run a stage with retry logic."""
        for attempt in range(3):
            try:
                return fn()
            except Exception as e:
                self.metrics["retries"] += 1
                if attempt == 2:
                    raise RuntimeError(f"Stage '{name}' failed after 3 attempts: {e}")
                time.sleep(1)

    def _generate_execution_report(self, config: dict, intent: dict) -> dict:
        """Simulate execution — prove the config is actionable."""
        report = {"status": "executable", "checks": [], "simulated_routes": [], "db_tables_count": 0}

        # Check DB
        db = config.get("db_schema", {})
        tables = db.get("tables", [])
        report["db_tables_count"] = len(tables)
        report["checks"].append({"check": "DB tables defined", "pass": len(tables) > 0})

        # Check API
        api = config.get("api_schema", {})
        endpoints = api.get("endpoints", [])
        report["checks"].append({"check": "API endpoints defined", "pass": len(endpoints) > 0})
        report["simulated_routes"] = [f"{e['method']} {e['path']}" for e in endpoints[:5]]

        # Check UI
        ui = config.get("ui_schema", {})
        pages = ui.get("pages", [])
        report["checks"].append({"check": "UI pages defined", "pass": len(pages) > 0})

        # Check Auth
        auth = config.get("auth_schema", {})
        report["checks"].append({"check": "Auth schema defined", "pass": bool(auth.get("method"))})

        failed = [c for c in report["checks"] if not c["pass"]]
        report["status"] = "executable" if not failed else "needs_fixes"
        report["failed_checks"] = failed
        return report