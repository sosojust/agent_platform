import json
import time
from typing import Any, Mapping

from langchain_core.messages import SystemMessage, HumanMessage

from core.ai_core.llm.client import llm_gateway
from core.memory_rag.memory.provider_protocols import LongTermExtractor
from shared.logging.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """
You are a memory extraction assistant. Your task is to extract important, structured facts from the conversation history.
Extract facts that would be useful for future interactions (e.g., user preferences, stated requirements, important context, background information).
Do not extract transient or conversational pleasantries.
Output a JSON list of objects, where each object has:
- "fact": The concise fact extracted (in the same language as the conversation).
- "category": The category of the fact (e.g., "preference", "requirement", "profile", "business_context", "other").
- "confidence": A float between 0.0 and 1.0 indicating how certain you are about this fact.

Return ONLY valid JSON.
Example:
[
  {"fact": "User is asking about a group insurance policy for 50 employees.", "category": "requirement", "confidence": 0.95},
  {"fact": "User prefers email communication.", "category": "preference", "confidence": 0.8}
]
"""

class LLMFactExtractor(LongTermExtractor):
    def __init__(self, task_type: str = "simple"):
        self.task_type = task_type

    @property
    def name(self) -> str:
        return "llm_fact_extractor"

    async def extract(
        self,
        messages: list[Mapping[str, Any]],
        tenant_id: str,
        conversation_id: str,
    ) -> list[dict[str, Any]]:
        if not messages:
            return []
            
        chat = llm_gateway.get_chat(tools=[], scene="memory_summary")
        
        conv_text = "\n".join([f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages])
        
        sys_msg = SystemMessage(content=SYSTEM_PROMPT)
        human_msg = HumanMessage(content=f"Conversation:\n{conv_text}\n\nExtract facts as JSON list:")
        
        try:
            response = await chat.ainvoke([sys_msg, human_msg])
            content = str(response.content).strip()
            
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            content = content.strip()
            
            data = json.loads(content)
            if not isinstance(data, list):
                return []
                
            now = int(time.time())
            facts = []
            for item in data:
                if not isinstance(item, dict) or "fact" not in item:
                    continue
                facts.append({
                    "content": item["fact"],
                    "category": item.get("category", "general"),
                    "confidence": float(item.get("confidence", 1.0)),
                    "createdAt": now,
                    "role": "system",
                    "timestamp": now,
                })
            
            logger.info(
                "facts_extracted", 
                tenant_id=tenant_id, 
                conversation_id=conversation_id, 
                fact_count=len(facts)
            )
            return facts
        except Exception as e:
            logger.error("fact_extraction_failed", error=str(e), tenant_id=tenant_id)
            return []
