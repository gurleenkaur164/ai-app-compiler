"""
RepairEngine — Intelligent targeted repair of schema issues.
Instead of blind retry, we fix ONLY the broken parts.
"""

import json
import re


class RepairEngine:
    def __init__(self, groq_client):
        self.client = groq_client
        self.model = "llama-3.3-70b-versatile"

    def repair(self, config: dict, errors: list, llm_fn) -> dict:
        """
        Analyze errors and apply targeted repairs.
        Groups errors by layer and repairs each layer independently.
        """
        if not errors:
            return config

        # Group errors by layer
        layer_errors = {
            "db_schema": [],
            "api_schema": [],
            "ui_schema": [],
            "auth_schema": [],
            "cross_layer": []
        }

        for err in errors:
            if err.startswith("DB:") or "db" in err.lower():
                layer_errors["db_schema"].append(err)
            elif err.startswith("API:") or "api" in err.lower():
                layer_errors["api_schema"].append(err)
            elif err.startswith("UI:") or "ui" in err.lower():
                layer_errors["ui_schema"].append(err)
            elif err.startswith("AUTH:") or "auth" in err.lower():
                layer_errors["auth_schema"].append(err)
            else:
                layer_errors["cross_layer"].append(err)

        # Repair each broken layer
        for layer, layer_errs in layer_errors.items():
            if not layer_errs:
                continue

            if layer == "cross_layer":
                config = self._repair_cross_layer(config, layer_errs, llm_fn)
            else:
                config = self._repair_layer(config, layer, layer_errs, llm_fn)

        return config

    def _repair_layer(self, config: dict, layer: str, errors: list, llm_fn) -> dict:
        """Repair a single layer using targeted LLM call."""
        current_layer = config.get(layer, {})

        system = f"""You are a JSON repair engine. Fix ONLY the {layer} section.
Return ONLY the repaired {layer} JSON object, no explanation, no markdown.
Fix these specific errors: {json.dumps(errors)}"""

        user = f"Current {layer}:\n{json.dumps(current_layer, indent=2)}\n\nFull config context:\n{json.dumps({k: v for k, v in config.items() if k != layer}, indent=2)}"

        try:
            raw = llm_fn(system, user, temperature=0.1)
            repaired = self._extract_json(raw)
            config[layer] = repaired
        except Exception as e:
            # Fallback: apply structural fixes without LLM
            config[layer] = self._structural_fix(layer, current_layer, errors)

        return config

    def _repair_cross_layer(self, config: dict, errors: list, llm_fn) -> dict:
        """Repair cross-layer inconsistencies."""
        system = """You are a cross-layer schema consistency engine.
Fix cross-layer inconsistencies in this app config.
Return the COMPLETE fixed config as valid JSON only, no markdown."""

        user = f"Errors to fix: {json.dumps(errors)}\n\nConfig:\n{json.dumps(config, indent=2)}"

        try:
            raw = llm_fn(system, user, temperature=0.1)
            return self._extract_json(raw)
        except:
            return config

    def _structural_fix(self, layer: str, data: dict, errors: list) -> dict:
        """Rule-based fallback fixes for common issues."""
        if layer == "db_schema":
            tables = data.get("tables", [])
            for table in tables:
                fields = table.get("fields", [])
                # Ensure primary key exists
                has_pk = any(f.get("primary_key") for f in fields)
                if not has_pk and fields:
                    fields.insert(0, {
                        "name": "id",
                        "type": "INT",
                        "primary_key": True,
                        "nullable": False,
                        "unique": True,
                        "default": None,
                        "foreign_key": None
                    })
            return data

        if layer == "auth_schema":
            if not data.get("roles"):
                data["roles"] = ["admin", "user"]
            if not data.get("method"):
                data["method"] = "JWT"
            return data

        if layer == "api_schema":
            endpoints = data.get("endpoints", [])
            for ep in endpoints:
                if not ep.get("method"):
                    ep["method"] = "GET"
            return data

        return data

    def _extract_json(self, text: str) -> dict:
        try:
            return json.loads(text)
        except:
            pass
        match = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', text)
        if match:
            try:
                return json.loads(match.group(1))
            except:
                pass
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            return json.loads(match.group(0))
        raise ValueError("Cannot extract JSON")