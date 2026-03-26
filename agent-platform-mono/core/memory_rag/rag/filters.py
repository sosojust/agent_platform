from __future__ import annotations
from typing import Any, Dict, List, Tuple
from qdrant_client.models import Filter, FieldCondition, MatchValue


ALLOWED_FIELDS = {
    "tenant_id",
    "policyId",
    "claimStatus",
    "companyId",
    "updatedAt",
}


def _validate_field(field: str) -> None:
    if field not in ALLOWED_FIELDS:
        raise ValueError(f"field_not_allowed: {field}")


def _translate_atom(ast: Dict[str, Any]) -> Tuple[str, List[FieldCondition]]:
    if "EQ" in ast:
        field, value = ast["EQ"]
        _validate_field(field)
        return "must", [FieldCondition(key=field, match=MatchValue(value=value))]
    if "IN" in ast:
        field, values = ast["IN"]
        _validate_field(field)
        conds = [FieldCondition(key=field, match=MatchValue(value=v)) for v in values]
        return "should", conds
    if "EXISTS" in ast:
        field = ast["EXISTS"]
        _validate_field(field)
        raise ValueError("EXISTS_not_supported")
    raise ValueError("unsupported_atom")


def build_qdrant_filter(filter_ast: Dict[str, Any] | None) -> Filter | None:
    if not filter_ast:
        return None
    must: List[FieldCondition] = []
    should: List[FieldCondition] = []
    if "AND" in filter_ast:
        items = filter_ast["AND"]
        for it in items:
            kind, conds = _translate_atom(it)
            if kind == "must":
                must.extend(conds)
            elif kind == "should":
                should.extend(conds)
    else:
        kind, conds = _translate_atom(filter_ast)
        if kind == "must":
            must.extend(conds)
        elif kind == "should":
            should.extend(conds)
    if should:
        return Filter(must=must, should=should)
    return Filter(must=must)
