# Task 1.3 - Data Layering Model (Deferred)

## Status: ⏸️ Deferred

**Date**: 2026-04-01  
**Reason**: Architecture discussion needed

---

## Background

Task 1.3 aimed to implement a four-layer data model (Platform/Channel/Tenant/User) for the vector database. During implementation, we identified fundamental design questions that require deeper architectural discussion.

---

## Issues Identified

### 1. Platform vs Business Boundary

**Problem**: Initial implementation hardcoded business-specific data types in the platform layer.

```python
# ❌ Platform layer defining business types
class DataType(StrEnum):
    PRODUCT_TEMPLATE = "product_template"      # Insurance business
    PLATFORM_FAQ = "platform_faq"              # Insurance business
    PRODUCT_CATALOG = "product_catalog"        # Insurance business
    # ... more insurance-specific types
```

**Issue**: This makes the platform layer aware of specific business domains (insurance), limiting extensibility for other domains (HR, customer service, finance, etc.).

### 2. Extensibility Concerns

**Problem**: Adding new business scenarios requires modifying platform core code.

**Questions**:
- How should new business domains define their data types?
- Should the platform provide a registry mechanism?
- How to avoid type name conflicts across domains?

### 3. Scope Definition

**Problem**: The 4-layer classification (Platform/Channel/Tenant/User) may not fit all scenarios.

**Questions**:
- Is this classification flexible enough?
- Do we need additional layers (e.g., Organization, Department)?
- Should layers be configurable?

### 4. Collection Naming

**Problem**: Current naming convention is rigid.

```
Platform: platform__<data_type>
Channel:  channel__<channel_id>__<data_type>
Tenant:   tenant__<tenant_id>__<data_type>
User:     user__<tenant_id>__<user_id>__<data_type>
```

**Questions**:
- How to support dynamic business scenarios?
- Should naming be more flexible?
- How to handle collection versioning?

---

## Attempted Solutions

### Approach 1: Hardcoded Business Types (Rejected)

**Implementation**: Define all data types in platform layer as enums.

**Pros**:
- Type safety
- Clear mapping to scopes
- Easy validation

**Cons**:
- ❌ Not extensible
- ❌ Platform depends on business
- ❌ Violates open-closed principle
- ❌ Not a true "platform"

### Approach 2: Free-form Strings (Rejected)

**Implementation**: Change `data_type` from enum to string, let business layers define types freely.

**Pros**:
- ✅ Highly flexible
- ✅ Platform independent of business
- ✅ Easy to extend

**Cons**:
- ❌ No type safety
- ❌ No validation
- ❌ Potential naming conflicts
- ❌ Difficult to discover available types

---

## Questions for Architecture Discussion

### 1. Data Model System

**Core Question**: What is the overall data model philosophy for the platform?

**Sub-questions**:
- Should we have a centralized type registry?
- How do we balance flexibility and structure?
- What are the invariants that platform must enforce?

### 2. Scope Classification

**Core Question**: Is the 4-layer model the right abstraction?

**Sub-questions**:
- Are Platform/Channel/Tenant/User sufficient for all scenarios?
- Should scopes be hierarchical or flat?
- Can business layers define custom scopes?

### 3. Type Management

**Core Question**: How should data types be defined and managed?

**Options to consider**:
- **Option A**: Platform defines base types, business extends
- **Option B**: Business defines all types, platform provides registry
- **Option C**: Hybrid approach with namespacing
- **Option D**: Schema-based approach with validation

### 4. Collection Strategy

**Core Question**: How should collections be organized?

**Options to consider**:
- **Option A**: One collection per (scope, data_type) combination
- **Option B**: One collection per scope, filter by data_type
- **Option C**: Dynamic collection creation based on business needs
- **Option D**: Configurable collection strategy

### 5. Metadata Structure

**Core Question**: What metadata should be standardized?

**Required fields**:
- Scope identifiers (platform_id, channel_id, tenant_id, user_id)
- Source information (source_id, source_name)
- Timestamps (created_at, updated_at, expires_at)
- Content (text, language)

**Optional/Business-specific fields**:
- How to handle custom metadata?
- Should we use a flexible `metadata` dict?
- How to validate custom fields?

---

## Proposed Discussion Framework

### Phase 1: Principles Definition

Define core principles for the platform:
1. What makes this a "platform" vs a "system"?
2. What should be standardized vs flexible?
3. What are the non-negotiable constraints?

### Phase 2: Use Case Analysis

Analyze concrete use cases:
1. Insurance domain (current)
2. HR domain (hypothetical)
3. Customer service domain (hypothetical)
4. Finance domain (hypothetical)

For each domain:
- What data types do they need?
- How do they map to scopes?
- What are their unique requirements?

### Phase 3: Design Alternatives

Evaluate design alternatives:
1. Centralized registry vs distributed definition
2. Static types vs dynamic types
3. Strict validation vs loose validation
4. Single collection strategy vs multiple strategies

### Phase 4: Decision & Implementation

Make architectural decisions and document:
1. Chosen approach and rationale
2. Migration path from current state
3. Extension guidelines for business layers
4. Validation and governance mechanisms

---

## Impact on Other Tasks

### Blocked Tasks

The following tasks depend on Task 1.3 and are currently blocked:

- **Task 1.5** (IngestGateway): Needs data model for chunk metadata
- **Task 1.6** (Retrieval): Needs data model for filtering and retrieval
- **Task 1.7** (Memory): Needs data model for memory storage

### Can Proceed

The following tasks can proceed independently:

- **Task 1.4** (Vector Adapter): Can implement basic CRUD without specific data model
- **Task 1.4.5** (shared/libs): Independent of data model

---

## Rollback Actions Taken

1. ✅ Deleted `core/memory_rag/vector/` directory
2. ✅ Deleted `tests/core/memory_rag/` directory
3. ✅ Deleted `docs/architecture/platform_vs_business_design.md`
4. ✅ Updated `core/memory_rag/__init__.py` to empty state
5. ✅ Updated `docs/tasks/batch1_infrastructure.md` to mark Task 1.3 as deferred
6. ✅ Updated `docs/tasks/batch1_review.md` to remove Task 1.3 content
7. ✅ Verified all existing tests still pass (28 tests, 100% pass rate)

---

## Next Steps

1. **Schedule Architecture Discussion**:
   - Gather stakeholders
   - Review this document
   - Discuss questions and alternatives

2. **Document Decisions**:
   - Create architecture decision record (ADR)
   - Document chosen approach
   - Define extension guidelines

3. **Redesign Task 1.3**:
   - Implement based on architectural decisions
   - Create comprehensive tests
   - Update dependent tasks

4. **Resume Blocked Tasks**:
   - Unblock Tasks 1.5, 1.6, 1.7
   - Update implementation plans
   - Continue Batch 1 development

---

## Lessons Learned

1. **Start with Principles**: Should have defined platform principles before implementation
2. **Use Case Driven**: Need concrete use cases to validate design decisions
3. **Extensibility First**: Platform design must prioritize extensibility over convenience
4. **Early Validation**: Architectural questions should be resolved before coding

---

**Document Created**: 2026-04-01  
**Status**: Awaiting architecture discussion  
**Owner**: Platform Architecture Team
