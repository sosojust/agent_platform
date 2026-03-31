"""
Nacos 动态配置接入。

职责：
  - 启动时从 Nacos 拉取动态参数，覆盖 settings 中的默认值
  - 注册变更监听，运行时热更新，无需重启服务
  - Nacos 不可用时静默降级，不影响服务启动

Nacos 中管理的配置（适合频繁调整、不需要重启的参数）：
  {
    "llm_default_model": "openai/gpt-4o-mini",
    "llm_strong_model": "openai/gpt-4o",
    "rag_top_k_recall": 20,
    "rag_top_k_rerank": 5,
    "rag_rerank_threshold": 0.3,
    "agent_max_steps": 10,
    "enabled_domains": ["policy", "claim", "customer"]
  }

不适合放 Nacos（应放 .env / K8s Secret）：
  - API Key（OPENAI_API_KEY 等敏感值）
  - 数据库连接串
  - Redis / Milvus 连接地址
"""
import json
from shared.logging.logger import get_logger

logger = get_logger(__name__)


def init_nacos_config(settings) -> None:
    """
    初始化 Nacos 配置。
    NACOS_SERVER_ADDR 为空时直接跳过，纯 .env 模式运行。
    """
    if not settings.nacos.server_addr:
        logger.info("nacos_skipped", reason="NACOS_SERVER_ADDR not set, using .env only")
        return

    try:
        import nacos
        client = nacos.NacosClient(
            server_addresses=settings.nacos.server_addr,
            namespace=settings.nacos.namespace,
        )

        # 首次拉取
        raw = client.get_config(settings.nacos.data_id, settings.nacos.group, timeout=5)
        if raw:
            _apply_config(settings, json.loads(raw))
            logger.info("nacos_config_loaded", data_id=settings.nacos.data_id)

        # 注册热更新监听
        def on_change(_, config_str: str) -> None:
            try:
                _apply_config(settings, json.loads(config_str))
                logger.info("nacos_config_updated")
            except Exception as e:
                logger.error("nacos_config_update_failed", error=str(e))

        client.add_config_watcher(
            settings.nacos.data_id, settings.nacos.group, on_change
        )

    except Exception as e:
        # Nacos 不可用不应该阻断服务启动
        logger.warning("nacos_init_failed", error=str(e), fallback="using .env defaults")


def _apply_config(settings, config: dict) -> None:
    """将 Nacos 下发的配置更新到动态配置代理"""
    # 保持对静态配置对象的直接修改，以兼容旧代码直接访问 settings.llm.xxx
    if "llm_default_model" in config:
        settings.llm.default_model = config["llm_default_model"]
    if "llm_strong_model" in config:
        settings.llm.strong_model = config["llm_strong_model"]
    if "llm_medium_model" in config:
        settings.llm.medium_model = config["llm_medium_model"]
    if "llm_nano_model" in config:
        settings.llm.nano_model = config["llm_nano_model"]
    if "llm_local_model" in config:
        settings.llm.local_model = config["llm_local_model"]
    if "llm_router_deployments" in config:
        settings.llm.router_deployments = json.dumps(config["llm_router_deployments"], ensure_ascii=False)
    if "llm_router_cooldown_seconds" in config:
        settings.llm.router_cooldown_seconds = int(config["llm_router_cooldown_seconds"])
    if "llm_router_max_attempts" in config:
        settings.llm.router_max_attempts = int(config["llm_router_max_attempts"])
    if "llm_cache_enabled" in config:
        settings.llm.cache_enabled = bool(config["llm_cache_enabled"])
    if "llm_cache_default_ttl_seconds" in config:
        settings.llm.cache_default_ttl_seconds = int(config["llm_cache_default_ttl_seconds"])
    if "llm_cache_scene_ttl" in config:
        settings.llm.cache_scene_ttl = json.dumps(config["llm_cache_scene_ttl"], ensure_ascii=False)
    if "llm_cache_task_ttl" in config:
        settings.llm.cache_task_ttl = json.dumps(config["llm_cache_task_ttl"], ensure_ascii=False)
    if "llm_cache_max_entries" in config:
        settings.llm.cache_max_entries = int(config["llm_cache_max_entries"])

    # 统一存入统一的动态访问缓存
    settings.update_dynamic(config)
