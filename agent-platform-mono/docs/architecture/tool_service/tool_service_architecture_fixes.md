# Tool Service 架构问题修正

> 版本：v6.4  
> 日期：2026-04-02  
> 状态：架构问题修正

本文档针对 `tool_service_final_design.md` v6.3 中发现的架构问题进行修正。

---

## 问题 1：health_check 实现有误导性

### 问题描述

```python
async def health_check(self) -> bool:
    """健康检查（通用实现）"""
    try:
        tools = await self.load_tools()
        return len(tools) >= 0  # ❌ 永远为 True
    except Exception:
        return False
```

**问题**：`len(tools) >= 0` 永远为 True，因为列表长度不可能为负数。

### 修正方案

#### 方案 A：检查工具数量（适用于大部分 Adapter）

```python
async def health_check(self) -> bool:
    """健康检查（通用实现）"""
    try:
        tools = await self.load_tools()
        return len(tools) > 0  # ✅ 至少有一个工具才算健康
    except Exception:
        return False
```

#### 方案 B：Ping 服务端点（适用于 External/Internal MCP）

```python
# ExternalMCPAdapter
async def health_check(self) -> bool:
    """健康检查（Ping MCP Server）"""
    try:
        response = await self._client.post(
            f"{self.endpoint}/health",
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=5,
        )
        return response.status_code == 200
    except Exception:
        return False
```

#### 推荐方案：分层健康检查

```python
# core/tool_service/base/adapter.py
class ToolAdapter(ABC):
    """工具适配器基类"""
    
    async def health_check(self) -> bool:
        """
        健康检查（通用实现）。
        
        默认实现：检查是否能成功加载工具。
        子类可以覆盖此方法实现更精确的健康检查（如 ping 端点）。
        """
        try:
            tools = await self.load_tools()
            return len(tools) > 0  # ✅ 至少有一个工具
        except Exception:
            return False
    
    async def health_check_detailed(self) -> dict:
        """
        详细健康检查（可选）。
        
        返回更详细的健康状态信息。
        """
        try:
            tools = await self.load_tools()
            return {
                "healthy": len(tools) > 0,
                "tool_count": len(tools),
                "adapter_type": self.get_adapter_type(),
            }
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
                "adapter_type": self.get_adapter_type(),
            }
```


```python
# ExternalMCPAdapter 覆盖健康检查
class ExternalMCPAdapter(ToolAdapter):
    async def health_check(self) -> bool:
        """健康检查（Ping MCP Server）"""
        try:
            response = await self._client.post(
                f"{self.endpoint}/health",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=5,
            )
            return response.status_code == 200
        except Exception:
            return False
```

---

## 问题 2：External MCP 工具缓存只在内存里

### 问题描述

```python
class ExternalMCPAdapter(ToolAdapter):
    def __init__(self, name: str, endpoint: str, token: str):
        self._tools_cache: Dict[str, dict] = {}  # ❌ 实例级内存缓存
```

**问题**：
1. `_tools_cache` 是实例级字典，服务重启后需要重新 `load_tools()`
2. 文档没有说明缓存刷新时机的设计
3. 多实例部署时，每个实例都有自己的缓存，可能不一致

### 修正方案

#### 方案 A：添加缓存刷新机制

```python
class ExternalMCPAdapter(ToolAdapter):
    def __init__(
        self,
        name: str,
        endpoint: str,
        token: str,
        cache_ttl: int = 3600,  # 缓存 1 小时
    ):
        self.name = name
        self.endpoint = endpoint.rstrip("/")
        self.token = token
        self._client = httpx.AsyncClient(timeout=30)
        self._tools_cache: Dict[str, dict] = {}
        self._cache_ttl = cache_ttl
        self._last_load_time: float | None = None
    
    async def load_tools(self, force_refresh: bool = False) -> List[ToolMetadata]:
        """
        从外部 MCP Server 加载工具。
        
        Args:
            force_refresh: 强制刷新缓存
        """
        import time
        
        # 检查缓存是否过期
        if not force_refresh and self._last_load_time:
            elapsed = time.time() - self._last_load_time
            if elapsed < self._cache_ttl and self._tools_cache:
                logger.debug(
                    "external_mcp_using_cache",
                    name=self.name,
                    cache_age=elapsed,
                )
                # 从缓存构建 ToolMetadata 列表
                return self._build_metadata_from_cache()
        
        # 从远程加载
        try:
            response = await self._client.post(
                f"{self.endpoint}/mcp/list_tools",
                headers={"Authorization": f"Bearer {self.token}"},
            )
            response.raise_for_status()
            data = response.json()
            
            tools = []
            self._tools_cache.clear()  # 清空旧缓存
            
            for tool_def in data.get("tools", []):
                tool_name = f"{self.name}:{tool_def['name']}"
                
                metadata = ExternalMCPToolMetadata(
                    name=tool_name,
                    description=tool_def.get("description", ""),
                    type=ToolType.TOOL,
                    category=self.name,
                    input_schema=tool_def.get("inputSchema", {}),
                    output_schema=tool_def.get("outputSchema"),
                    tags=["external", "mcp", self.name],
                    mcp_server_name=self.name,
                    original_tool_name=tool_def['name'],
                )
                
                tools.append(metadata)
                self._tools_cache[tool_name] = tool_def
            
            self._last_load_time = time.time()
            
            logger.info(
                "external_mcp_tools_loaded",
                name=self.name,
                endpoint=self.endpoint,
                count=len(tools),
            )
            
            return tools
        
        except Exception as e:
            logger.error(
                "external_mcp_load_failed",
                name=self.name,
                endpoint=self.endpoint,
                error=str(e),
            )
            # 如果有旧缓存，返回旧缓存（降级）
            if self._tools_cache:
                logger.warning(
                    "external_mcp_using_stale_cache",
                    name=self.name,
                )
                return self._build_metadata_from_cache()
            return []
    
    def _build_metadata_from_cache(self) -> List[ToolMetadata]:
        """从缓存构建 ToolMetadata 列表"""
        tools = []
        for tool_name, tool_def in self._tools_cache.items():
            metadata = ExternalMCPToolMetadata(
                name=tool_name,
                description=tool_def.get("description", ""),
                type=ToolType.TOOL,
                category=self.name,
                input_schema=tool_def.get("inputSchema", {}),
                output_schema=tool_def.get("outputSchema"),
                tags=["external", "mcp", self.name],
                mcp_server_name=self.name,
                original_tool_name=tool_def['name'],
            )
            tools.append(metadata)
        return tools
```


#### 方案 B：使用 Redis 作为共享缓存（推荐用于生产环境）

```python
class ExternalMCPAdapter(ToolAdapter):
    def __init__(
        self,
        name: str,
        endpoint: str,
        token: str,
        redis_client=None,
        cache_ttl: int = 3600,
    ):
        self.name = name
        self.endpoint = endpoint.rstrip("/")
        self.token = token
        self._client = httpx.AsyncClient(timeout=30)
        self._redis = redis_client
        self._cache_ttl = cache_ttl
        self._cache_key = f"tool_service:external_mcp:{name}:tools"
    
    async def load_tools(self, force_refresh: bool = False) -> List[ToolMetadata]:
        """从外部 MCP Server 加载工具（使用 Redis 缓存）"""
        import json
        
        # 尝试从 Redis 获取缓存
        if not force_refresh and self._redis:
            try:
                cached_data = await self._redis.get(self._cache_key)
                if cached_data:
                    logger.debug(
                        "external_mcp_using_redis_cache",
                        name=self.name,
                    )
                    tools_data = json.loads(cached_data)
                    return self._deserialize_tools(tools_data)
            except Exception as e:
                logger.warning(
                    "external_mcp_redis_cache_failed",
                    name=self.name,
                    error=str(e),
                )
        
        # 从远程加载
        try:
            response = await self._client.post(
                f"{self.endpoint}/mcp/list_tools",
                headers={"Authorization": f"Bearer {self.token}"},
            )
            response.raise_for_status()
            data = response.json()
            
            tools = []
            for tool_def in data.get("tools", []):
                tool_name = f"{self.name}:{tool_def['name']}"
                
                metadata = ExternalMCPToolMetadata(
                    name=tool_name,
                    description=tool_def.get("description", ""),
                    type=ToolType.TOOL,
                    category=self.name,
                    input_schema=tool_def.get("inputSchema", {}),
                    output_schema=tool_def.get("outputSchema"),
                    tags=["external", "mcp", self.name],
                    mcp_server_name=self.name,
                    original_tool_name=tool_def['name'],
                )
                
                tools.append(metadata)
            
            # 保存到 Redis
            if self._redis:
                try:
                    tools_data = self._serialize_tools(tools)
                    await self._redis.setex(
                        self._cache_key,
                        self._cache_ttl,
                        json.dumps(tools_data),
                    )
                except Exception as e:
                    logger.warning(
                        "external_mcp_redis_save_failed",
                        name=self.name,
                        error=str(e),
                    )
            
            logger.info(
                "external_mcp_tools_loaded",
                name=self.name,
                endpoint=self.endpoint,
                count=len(tools),
            )
            
            return tools
        
        except Exception as e:
            logger.error(
                "external_mcp_load_failed",
                name=self.name,
                endpoint=self.endpoint,
                error=str(e),
            )
            return []
```

#### 缓存刷新策略

1. **启动时加载**：服务启动时调用 `load_tools()`
2. **定期刷新**：后台任务定期刷新（如每小时）
3. **手动刷新**：提供 API 端点手动触发刷新
4. **失败降级**：加载失败时使用旧缓存

```python
# 在 ToolGateway 中添加刷新机制
class ToolGateway:
    async def refresh_external_tools(self, adapter_name: str | None = None):
        """
        刷新外部工具缓存。
        
        Args:
            adapter_name: 指定 adapter 名称，None 表示刷新所有
        """
        for name, entry in self._adapters.items():
            if adapter_name and name != adapter_name:
                continue
            
            if isinstance(entry.adapter, ExternalMCPAdapter):
                logger.info("refreshing_external_tools", adapter=name)
                tools = await entry.adapter.load_tools(force_refresh=True)
                # 重新注册工具
                for tool in tools:
                    self._tools[tool.name] = ToolEntry(
                        metadata=tool,
                        adapter=entry.adapter,
                    )
```


---

## 问题 3：SkillDefinition 和 ToolMetadata 数据结构不一致

### 问题描述

```python
@dataclass
class SkillDefinition:
    """Skill 定义（只存在 Adapter 实例里）"""
    name: str
    description: str
    prompt_template: str
    available_tools: List[str]
    llm_config: dict
    input_schema: dict

class SkillAdapter(ToolAdapter):
    def __init__(self, domain: str, tool_gateway):
        self._skills: Dict[str, SkillDefinition] = {}  # ❌ 只在实例里
    
    async def load_tools(self) -> List[ToolMetadata]:
        """加载时转换为 ToolMetadata"""
        for name, skill_def in self._skills.items():
            metadata = SkillToolMetadata(
                name=name,
                description=skill_def.description,
                # ... 从 SkillDefinition 复制字段
            )
```

**问题**：
1. `SkillDefinition` 只存在 Adapter 实例里，Adapter 销毁后定义就丢了
2. 多实例部署时，每个实例的 Skill 定义可能不一致
3. `SkillToolMetadata` 包含了 `SkillDefinition` 的所有信息，但需要手动同步

### 修正方案

#### 方案 A：统一使用 SkillToolMetadata（推荐）

```python
# 移除 SkillDefinition，直接使用 SkillToolMetadata
class SkillAdapter(ToolAdapter):
    def __init__(self, domain: str, tool_gateway):
        self.domain = domain
        self.tool_gateway = tool_gateway
        self.executor = SkillExecutor(tool_gateway)
        # ✅ 直接存储 SkillToolMetadata
        self._skills: Dict[str, SkillToolMetadata] = {}
    
    def register_skill(self, metadata: SkillToolMetadata):
        """
        注册一个 Skill。
        
        Args:
            metadata: Skill 元数据（包含所有必要信息）
        """
        # 验证类型
        if not isinstance(metadata, SkillToolMetadata):
            raise TypeError(f"Expected SkillToolMetadata, got {type(metadata)}")
        
        # 确保类型正确
        metadata.type = ToolType.SKILL
        metadata.adapter_type = AdapterType.SKILL
        
        self._skills[metadata.name] = metadata
        
        logger.info(
            "skill_registered",
            name=metadata.name,
            domain=self.domain,
            tool_count=len(metadata.available_tools),
        )
    
    async def load_tools(self) -> List[SkillToolMetadata]:
        """加载所有已注册的 Skill"""
        logger.info(
            "skill_tools_loaded",
            domain=self.domain,
            count=len(self._skills),
        )
        return list(self._skills.values())  # ✅ 直接返回
    
    async def invoke_tool(
        self,
        metadata: ToolMetadata,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> Any:
        """执行 Skill"""
        skill_metadata = self._skills.get(metadata.name)
        if not skill_metadata:
            raise ValueError(f"Skill not found: {metadata.name}")
        
        # ✅ 直接传递 SkillToolMetadata
        return await self.executor.execute(skill_metadata, arguments, context)


# SkillExecutor 也相应调整
class SkillExecutor:
    def __init__(self, tool_gateway):
        self.tool_gateway = tool_gateway
    
    async def execute(
        self,
        skill_metadata: SkillToolMetadata,  # ✅ 接收 SkillToolMetadata
        arguments: dict,
        context: ToolContext,
    ):
        """执行 Skill"""
        # 1. 渲染 prompt 模板
        prompt = self._render_prompt(skill_metadata.prompt_template, arguments)
        
        # 2. 获取可用工具
        tool_functions = []
        for tool_name in skill_metadata.available_tools:
            tool_entry = self.tool_gateway._tools.get(tool_name)
            if tool_entry:
                tool_functions.append(self._wrap_tool_for_agent(tool_entry, context))
        
        if not tool_functions:
            raise ValueError(f"No available tools for skill: {skill_metadata.name}")
        
        # 3. 创建 LLM Agent
        llm = llm_gateway.get_chat([], scene="skill_execution")
        
        agent = create_react_agent(
            model=llm,
            tools=tool_functions,
        )
        
        # 4. 执行 Agent
        logger.info(
            "skill_executing",
            skill_name=skill_metadata.name,
            tool_count=len(tool_functions),
            tenant_id=context.tenant_id,
        )
        
        result = await agent.ainvoke({
            "messages": [{"role": "user", "content": prompt}]
        })
        
        # 5. 提取结果
        final_message = result["messages"][-1]
        
        return {
            "skill": skill_metadata.name,
            "result": final_message.content,
            "tool_calls": len([m for m in result["messages"] if hasattr(m, "tool_calls")]),
        }
```


#### 方案 B：持久化 Skill 定义（推荐用于生产环境）

```python
# 使用数据库或配置文件持久化 Skill 定义
class SkillRegistry:
    """
    Skill 注册表（持久化）。
    
    支持：
    - 数据库存储
    - 配置文件存储
    - 版本管理
    """
    
    def __init__(self, storage_backend: str = "database"):
        """
        Args:
            storage_backend: "database" | "file" | "redis"
        """
        self.backend = self._init_backend(storage_backend)
    
    async def register_skill(self, metadata: SkillToolMetadata):
        """注册 Skill（持久化）"""
        await self.backend.save(metadata)
        logger.info(
            "skill_registered_persistent",
            name=metadata.name,
            version=metadata.version,
        )
    
    async def load_skill(self, name: str) -> SkillToolMetadata | None:
        """加载 Skill"""
        return await self.backend.load(name)
    
    async def list_skills(self, domain: str | None = None) -> List[SkillToolMetadata]:
        """列出所有 Skill"""
        return await self.backend.list_all(domain=domain)
    
    async def delete_skill(self, name: str):
        """删除 Skill"""
        await self.backend.delete(name)


# 数据库存储实现
class DatabaseSkillBackend:
    """使用数据库存储 Skill 定义"""
    
    async def save(self, metadata: SkillToolMetadata):
        """保存到数据库"""
        import json
        
        skill_data = {
            "name": metadata.name,
            "description": metadata.description,
            "category": metadata.category,
            "prompt_template": metadata.prompt_template,
            "available_tools": json.dumps(metadata.available_tools),
            "llm_config": json.dumps(metadata.llm_config),
            "input_schema": json.dumps(metadata.input_schema),
            "output_schema": json.dumps(metadata.output_schema) if metadata.output_schema else None,
            "tags": json.dumps(metadata.tags),
            "version": metadata.version,
            "source_domain": metadata.source_domain,
        }
        
        # 使用 SQLAlchemy 或其他 ORM
        await db.execute(
            """
            INSERT INTO skills (name, description, category, prompt_template, 
                               available_tools, llm_config, input_schema, output_schema,
                               tags, version, source_domain)
            VALUES (:name, :description, :category, :prompt_template,
                    :available_tools, :llm_config, :input_schema, :output_schema,
                    :tags, :version, :source_domain)
            ON CONFLICT (name) DO UPDATE SET
                description = EXCLUDED.description,
                prompt_template = EXCLUDED.prompt_template,
                available_tools = EXCLUDED.available_tools,
                llm_config = EXCLUDED.llm_config,
                input_schema = EXCLUDED.input_schema,
                output_schema = EXCLUDED.output_schema,
                tags = EXCLUDED.tags,
                version = EXCLUDED.version,
                updated_at = NOW()
            """,
            skill_data,
        )
    
    async def load(self, name: str) -> SkillToolMetadata | None:
        """从数据库加载"""
        import json
        
        row = await db.fetch_one(
            "SELECT * FROM skills WHERE name = :name",
            {"name": name},
        )
        
        if not row:
            return None
        
        return SkillToolMetadata(
            name=row["name"],
            description=row["description"],
            category=row["category"],
            prompt_template=row["prompt_template"],
            available_tools=json.loads(row["available_tools"]),
            llm_config=json.loads(row["llm_config"]),
            input_schema=json.loads(row["input_schema"]),
            output_schema=json.loads(row["output_schema"]) if row["output_schema"] else None,
            tags=json.loads(row["tags"]),
            version=row["version"],
            source_domain=row["source_domain"],
        )
    
    async def list_all(self, domain: str | None = None) -> List[SkillToolMetadata]:
        """列出所有 Skill"""
        import json
        
        if domain:
            rows = await db.fetch_all(
                "SELECT * FROM skills WHERE source_domain = :domain",
                {"domain": domain},
            )
        else:
            rows = await db.fetch_all("SELECT * FROM skills")
        
        skills = []
        for row in rows:
            skills.append(SkillToolMetadata(
                name=row["name"],
                description=row["description"],
                category=row["category"],
                prompt_template=row["prompt_template"],
                available_tools=json.loads(row["available_tools"]),
                llm_config=json.loads(row["llm_config"]),
                input_schema=json.loads(row["input_schema"]),
                output_schema=json.loads(row["output_schema"]) if row["output_schema"] else None,
                tags=json.loads(row["tags"]),
                version=row["version"],
                source_domain=row["source_domain"],
            ))
        
        return skills


# SkillAdapter 使用持久化注册表
class SkillAdapter(ToolAdapter):
    def __init__(self, domain: str, tool_gateway, skill_registry: SkillRegistry):
        self.domain = domain
        self.tool_gateway = tool_gateway
        self.executor = SkillExecutor(tool_gateway)
        self.registry = skill_registry  # ✅ 使用持久化注册表
    
    async def register_skill(self, metadata: SkillToolMetadata):
        """注册 Skill（持久化）"""
        await self.registry.register_skill(metadata)
    
    async def load_tools(self) -> List[SkillToolMetadata]:
        """从持久化存储加载 Skill"""
        return await self.registry.list_skills(domain=self.domain)
    
    async def invoke_tool(
        self,
        metadata: ToolMetadata,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> Any:
        """执行 Skill"""
        # 从持久化存储加载最新定义
        skill_metadata = await self.registry.load_skill(metadata.name)
        if not skill_metadata:
            raise ValueError(f"Skill not found: {metadata.name}")
        
        return await self.executor.execute(skill_metadata, arguments, context)
```


#### 配置文件存储实现（适用于简单场景）

```python
# config/skills/policy_skills.yaml
skills:
  - name: analyze_policy_risk
    description: 分析保单风险
    category: policy
    prompt_template: |
      请分析保单 {policy_id} 的风险。
      考虑以下因素：
      1. 保额是否合理
      2. 保费是否异常
      3. 投保人信息是否完整
    available_tools:
      - query_policy_basic
      - query_policy_claims
      - calculate_risk_score
    llm_config:
      model: gpt-4
      temperature: 0.3
    input_schema:
      type: object
      properties:
        policy_id:
          type: string
          description: 保单 ID
      required:
        - policy_id
    version: "1.0.0"
    tags:
      - skill
      - policy
      - risk


# 配置文件加载器
class FileSkillBackend:
    """使用 YAML 文件存储 Skill 定义"""
    
    def __init__(self, config_dir: str = "config/skills"):
        self.config_dir = config_dir
    
    async def load_all(self, domain: str | None = None) -> List[SkillToolMetadata]:
        """从配置文件加载所有 Skill"""
        import yaml
        from pathlib import Path
        
        skills = []
        config_path = Path(self.config_dir)
        
        for yaml_file in config_path.glob("*.yaml"):
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            
            for skill_data in data.get("skills", []):
                # 过滤 domain
                if domain and skill_data.get("category") != domain:
                    continue
                
                metadata = SkillToolMetadata(
                    name=skill_data["name"],
                    description=skill_data["description"],
                    category=skill_data["category"],
                    prompt_template=skill_data["prompt_template"],
                    available_tools=skill_data["available_tools"],
                    llm_config=skill_data.get("llm_config", {}),
                    input_schema=skill_data.get("input_schema", {}),
                    output_schema=skill_data.get("output_schema"),
                    tags=skill_data.get("tags", []),
                    version=skill_data.get("version", "1.0.0"),
                    source_domain=skill_data["category"],
                )
                skills.append(metadata)
        
        return skills
```

---

## 总结：推荐的架构改进

### 1. 健康检查

```python
# Base Adapter
async def health_check(self) -> bool:
    try:
        tools = await self.load_tools()
        return len(tools) > 0  # ✅ 修正
    except Exception:
        return False

# External MCP Adapter（覆盖）
async def health_check(self) -> bool:
    try:
        response = await self._client.post(
            f"{self.endpoint}/health",
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=5,
        )
        return response.status_code == 200
    except Exception:
        return False
```

### 2. 缓存策略

**开发环境**：
- 使用内存缓存 + TTL
- 提供手动刷新接口

**生产环境**：
- 使用 Redis 共享缓存
- 定期后台刷新
- 失败降级到旧缓存

### 3. Skill 定义管理

**开发环境**：
- 使用配置文件（YAML）
- 简单直观，易于修改

**生产环境**：
- 使用数据库持久化
- 支持版本管理
- 支持动态更新

### 4. 架构改进对比

| 问题 | 原设计 | 改进方案 |
|------|--------|---------|
| health_check | `len(tools) >= 0` 永远 True | `len(tools) > 0` 或 ping 端点 |
| 工具缓存 | 实例级内存，重启丢失 | Redis 共享缓存 + TTL + 刷新机制 |
| Skill 定义 | 只在 Adapter 实例里 | 持久化存储（数据库/配置文件） |
| 多实例部署 | 数据不一致 | 共享存储，数据一致 |

---

**文档维护者**：Agent Platform Team  
**最后更新**：2026-04-02  
**版本**：v6.4（架构问题修正）
