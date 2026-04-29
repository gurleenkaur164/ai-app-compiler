"""
Strict schema definitions for all AppForge output contracts.
"""

from pydantic import BaseModel, Field
from typing import Any, Optional
from dataclasses import dataclass, field


class AppConfig(BaseModel):
    ui_schema: dict = Field(..., description="UI pages, components, layout")
    api_schema: dict = Field(..., description="API endpoints with request/response schemas")
    db_schema: dict = Field(..., description="DB tables, fields, relations")
    auth_schema: dict = Field(..., description="Auth method, roles, permissions")
    business_logic: list = Field(default=[], description="Business rules")


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)