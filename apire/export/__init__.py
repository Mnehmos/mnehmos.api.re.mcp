"""Exporters: projections of the evidence graph into specification formats.

Every document carries evidence per element and a speculative section for
anything below the caller's floor. Exports contain no credential material by
construction (redaction happened at ingestion) and implement no calls.
"""

from __future__ import annotations

from .architecture import architecture_document
from .asyncapi import asyncapi_document
from .json_schema import json_schema_document
from .mcp_candidate import mcp_candidate_document
from .openapi import openapi_document
from .protocol_spec import protocol_spec_document

EXPORTERS = {
    "openapi": openapi_document,
    "asyncapi": asyncapi_document,
    "json_schema": json_schema_document,
    "protocol_spec": protocol_spec_document,
    "architecture": architecture_document,
    "mcp_candidate": mcp_candidate_document,
}

__all__ = ["EXPORTERS", "architecture_document", "asyncapi_document", "json_schema_document", "mcp_candidate_document", "openapi_document", "protocol_spec_document"]
