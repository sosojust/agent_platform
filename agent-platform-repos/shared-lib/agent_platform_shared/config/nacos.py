"""Nacos 动态配置，各服务启动时调用 init_nacos_config()。"""
import json
from agent_platform_shared.logging.logger import get_logger

logger = get_logger(__name__)


def init_nacos_config(settings) -> None:
    if not settings.nacos.server_addr:
        logger.info("nacos_skipped", reason="NACOS_SERVER_ADDR not set")
        return
    try:
        import nacos
        client = nacos.NacosClient(
            server_addresses=settings.nacos.server_addr,
            namespace=settings.nacos.namespace,
        )
        raw = client.get_config(settings.nacos.data_id, settings.nacos.group, timeout=5)
        if raw:
            _apply(settings, json.loads(raw))
            logger.info("nacos_config_loaded")

        def on_change(_, cfg_str):
            try:
                _apply(settings, json.loads(cfg_str))
                logger.info("nacos_config_updated")
            except Exception as e:
                logger.error("nacos_update_failed", error=str(e))

        client.add_config_watcher(settings.nacos.data_id, settings.nacos.group, on_change)
    except Exception as e:
        logger.warning("nacos_init_failed", error=str(e))


def _apply(settings, config: dict) -> None:
    """将 Nacos 下发的动态参数写入 settings._dynamic，各服务读取时优先使用。"""
    if not hasattr(settings, "_dynamic"):
        settings._dynamic = {}
    settings._dynamic.update(config)
