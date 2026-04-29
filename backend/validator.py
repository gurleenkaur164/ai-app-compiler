"""
SchemaValidator — validates cross-layer consistency across UI, API, DB, Auth schemas.
This is the core quality gate of the pipeline.
"""

from schemas import ValidationResult


class SchemaValidator:
    def validate(self, config: dict) -> ValidationResult:
        errors = []
        warnings = []

        ui = config.get("ui_schema", {})
        api = config.get("api_schema", {})
        db = config.get("db_schema", {})
        auth = config.get("auth_schema", {})

        # ── Top-level presence checks ──
        if not ui:
            errors.append("MISSING: ui_schema is empty or absent")
        if not api:
            errors.append("MISSING: api_schema is empty or absent")
        if not db:
            errors.append("MISSING: db_schema is empty or absent")
        if not auth:
            errors.append("MISSING: auth_schema is empty or absent")

        # ── DB checks ──
        db_tables = {t["name"].lower(): t for t in db.get("tables", [])}
        if not db_tables:
            errors.append("DB: No tables defined")

        db_fields_by_table = {}
        for tname, tdata in db_tables.items():
            fields = [f["name"].lower() for f in tdata.get("fields", [])]
            db_fields_by_table[tname] = fields
            # Each table must have primary key
            has_pk = any(f.get("primary_key") for f in tdata.get("fields", []))
            if not has_pk:
                warnings.append(f"DB table '{tname}' has no primary key field")

        # ── API checks ──
        api_endpoints = api.get("endpoints", [])
        if not api_endpoints:
            errors.append("API: No endpoints defined")

        api_roles_used = set()
        for ep in api_endpoints:
            for role in ep.get("roles", []):
                api_roles_used.add(role)
            if not ep.get("method"):
                errors.append(f"API endpoint '{ep.get('path', '?')}' missing method")
            if not ep.get("path"):
                errors.append("API endpoint missing path")

        # ── Auth checks ──
        auth_roles = set(auth.get("roles", []))
        if not auth_roles:
            errors.append("AUTH: No roles defined")

        # Roles used in API must exist in auth
        orphan_roles = api_roles_used - auth_roles
        if orphan_roles:
            errors.append(f"AUTH: Roles used in API but not defined in auth_schema: {orphan_roles}")

        # ── UI checks ──
        ui_pages = ui.get("pages", [])
        if not ui_pages:
            errors.append("UI: No pages defined")

        for page in ui_pages:
            if not page.get("name"):
                errors.append("UI: Page missing name")
            if not page.get("path"):
                warnings.append(f"UI page '{page.get('name', '?')}' missing path")

        # ── Cross-layer: API <-> DB ──
        # Check that endpoints referencing table names have those tables
        for ep in api_endpoints:
            path_parts = ep.get("path", "").lower().replace("/api/v1/", "").split("/")
            resource = path_parts[0].rstrip("s") if path_parts else ""  # naive singular
            if resource and len(resource) > 2:
                if resource not in db_tables and resource + "s" not in db_tables:
                    warnings.append(f"API path '{ep.get('path')}' references resource '{resource}' not clearly mapped to a DB table")

        # ── Business logic ──
        biz = config.get("business_logic", [])
        if not biz:
            warnings.append("No business logic rules defined")

        is_valid = len(errors) == 0
        return ValidationResult(is_valid=is_valid, errors=errors, warnings=warnings)