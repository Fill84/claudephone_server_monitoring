"""Server monitoring plugin - health checks via ping and HTTP."""

import json
from typing import Any, Dict, List

from ..base import ConfigField, PluginBase, PluginMeta


class ServerMonitoringPlugin(PluginBase):
    """Server monitoring integration as a plugin."""

    @property
    def meta(self) -> PluginMeta:
        return PluginMeta(
            name="server_monitoring",
            display_name="Server Monitoring",
            description="Periodic health checks via ping and HTTP",
            version="1.0.0",
            author="Phillippe Pelzer",
        )

    @property
    def keywords(self) -> Dict[str, List[str]]:
        return {
            "nl": [
                "server", "servers", "status", "ping",
                "online", "offline", "draait", "monitoring",
                "web-unit", "storage-unit", "render-unit",
            ],
            "en": [
                "server", "servers", "status", "ping",
                "online", "offline", "running", "monitoring",
                "web-unit", "storage-unit", "render-unit",
            ],
        }

    @property
    def category_names(self) -> Dict[str, List[str]]:
        return {
            "nl": ["monitoring", "servers"],
            "en": ["monitoring", "servers"],
        }

    @property
    def category_options(self) -> Dict[str, Dict[str, Any]]:
        return {
            "nl": {
                "name": "Server Monitoring",
                "options": [
                    "Status van alle servers",
                    "Ping een specifieke server",
                    "Controleer of een server online is",
                ],
            },
            "en": {
                "name": "Server Monitoring",
                "options": [
                    "Status of all servers",
                    "Ping a specific server",
                    "Check if a server is online",
                ],
            },
        }

    @property
    def config_schema(self) -> List[ConfigField]:
        return [
            ConfigField(key="MONITORING_SERVERS", label="Servers (JSON)",
                        field_type="textarea",
                        placeholder='[{"name":"Web","type":"ping","host":"192.168.1.1"}]'),
            ConfigField(key="MONITORING_CHECK_INTERVAL", label="Check Interval (sec)",
                        default="60", hot_reload=True),
        ]

    def setup(self, context) -> None:
        super().setup(context)
        self._handler = None

    def on_enable(self) -> None:
        from .handler import MonitoringHandler
        servers_raw = self.context.get_env("MONITORING_SERVERS", "[]")
        try:
            servers = json.loads(servers_raw) if servers_raw else []
        except json.JSONDecodeError:
            servers = []
        if servers:
            self._handler = MonitoringHandler(servers)

    def on_disable(self) -> None:
        self._handler = None

    def handle(self, text: str, language: str = "en") -> str:
        if not self._handler:
            return self._msg(
                "Monitoring is not available.",
                "Monitoring is niet beschikbaar.",
                language,
            )
        return self._handler.handle(text, language)

    def check_all(self) -> list:
        """Expose check_all for the monitoring loop in agent.py."""
        if self._handler:
            return self._handler.check_all()
        return []
