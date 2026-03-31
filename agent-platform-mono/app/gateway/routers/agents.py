import json
import uuid
from typing import AsyncIterator, Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from core.agent_engine.agents.registry import agent_gateway
from core.agent_engine.checkpoints.redis_checkpoint import get_checkpointer
from core.agent_engine.orchestrator_factory import build_orchestrator
from core.agent_engine.workflows.state import make_initial_state
from shared.logging.logger import get_logger
from shared.middleware.tenant import (
    get_current_tenant_id,
    set_current_conversation_id,
    set_current_thread_id,
)
from shared.models.schemas import AgentRunRequest, AgentRunResponse

logger = get_logger(__name__)
router = APIRouter(tags=["agents"])


@router.post("/agent/run", response_model=AgentRunResponse, summary="同步运行 Agent")
async def run_agent(request: AgentRunRequest) -> AgentRunResponse:
    tenant_id = get_current_tenant_id()
    conversation_id = request.conversation_id or str(uuid.uuid4())
    set_current_conversation_id(conversation_id)
    set_current_thread_id(conversation_id)

    agent_meta = agent_gateway.get(request.agent_id)
    if not agent_meta:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{request.agent_id}' not found. "
            f"Available: {[a.agent_id for a in agent_gateway.list_all()]}",
        )

    initial_state = make_initial_state(
        messages=[HumanMessage(content=request.input)],
        conversation_id=conversation_id,
        tenant_id=tenant_id,
    )
    agent, mode = build_orchestrator(
        meta=agent_meta,
        tenant_id=tenant_id,
        user_input=request.input,
        state=initial_state,
    )
    checkpointer = await get_checkpointer()
    config = {"configurable": {"thread_id": conversation_id, "checkpointer": checkpointer}}

    try:
        result = await agent.ainvoke(initial_state, config=config)
        output = str(result["messages"][-1].content)
        logger.info(
            "agent_run_complete",
            agent_id=request.agent_id,
            conversation_id=conversation_id,
            steps=result.get("step_count", 0),
            mode=mode,
        )
        return AgentRunResponse(
            conversation_id=conversation_id,
            output=output,
            steps=[{"step_count": result.get("step_count", 0), "mode": mode}],
        )
    except Exception as e:
        logger.error("agent_run_failed", agent_id=request.agent_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agent/stream", summary="流式运行 Agent（SSE）")
async def stream_agent(request: AgentRunRequest) -> StreamingResponse:
    tenant_id = get_current_tenant_id()
    conversation_id = request.conversation_id or str(uuid.uuid4())
    set_current_conversation_id(conversation_id)
    set_current_thread_id(conversation_id)

    agent_meta = agent_gateway.get(request.agent_id)
    if not agent_meta:
        raise HTTPException(status_code=404, detail=f"Agent '{request.agent_id}' not found")

    initial_state = make_initial_state(
        messages=[HumanMessage(content=request.input)],
        conversation_id=conversation_id,
        tenant_id=tenant_id,
    )
    agent, mode = build_orchestrator(
        meta=agent_meta,
        tenant_id=tenant_id,
        user_input=request.input,
        state=initial_state,
    )
    checkpointer = await get_checkpointer()
    config = {"configurable": {"thread_id": conversation_id, "checkpointer": checkpointer}}

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for event in agent.astream_events(initial_state, config=config, version="v2"):
                kind = event["event"]
                if kind == "on_chat_model_stream":
                    token = event["data"]["chunk"].content
                    if token:
                        yield f"data: {json.dumps({'event': 'token', 'data': token})}\n\n"
                elif kind == "on_custom_event":
                    yield (
                        "data: "
                        f"{json.dumps({'event': event['name'], 'data': event['data']})}\n\n"
                    )
                elif kind == "on_tool_start":
                    yield f"data: {json.dumps({'event': 'step_start', 'data': event['name']})}\n\n"
                elif kind == "on_tool_end":
                    yield f"data: {json.dumps({'event': 'step_end', 'data': event['name']})}\n\n"
            yield f"data: {json.dumps({'event': 'done', 'data': {'mode': mode}})}\n\n"
        except Exception as e:
            logger.error("agent_stream_error", error=str(e))
            yield f"data: {json.dumps({'event': 'error', 'data': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/agent/list", summary="列出所有已注册的 Agent")
async def list_agents() -> list[dict[str, Any]]:
    return [
        {
            "agent_id": a.agent_id,
            "name": a.name,
            "description": a.description,
            "tags": a.tags,
            "version": a.version,
        }
        for a in agent_gateway.list_all()
    ]
