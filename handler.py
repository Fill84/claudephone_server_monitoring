"""Server monitoring handler - health checks via ping and HTTP."""

import logging
import subprocess
import sys
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)


class MonitoringHandler:
    """Perform health checks on configured servers."""

    def __init__(self, servers: List[Dict[str, Any]]):
        self.servers = servers

    def handle(self, text: str, language: str = "en") -> str:
        """Handle a monitoring query."""
        text_lower = text.lower()

        # Check for a specific server name
        for server in self.servers:
            name = server.get("name", "").lower()
            if name and name in text_lower:
                result = self._check_server(server)
                return self._format_single(result, language)

        # Default: check all servers
        results = self.check_all()
        return self._format_all(results, language)

    def check_all(self) -> List[Dict[str, Any]]:
        """Check all configured servers and return results."""
        results = []
        for server in self.servers:
            results.append(self._check_server(server))
        return results

    def _check_server(self, server: Dict[str, Any]) -> Dict[str, Any]:
        """Check a single server's health."""
        name = server.get("name", "Unknown")
        check_type = server.get("type", "ping").lower()
        host = server.get("host", "")
        port = server.get("port")
        url = server.get("url", "")

        result = {"name": name, "host": host, "type": check_type, "online": False}

        try:
            if check_type == "http" or check_type == "https":
                target_url = url or f"{check_type}://{host}"
                if port:
                    target_url = url or f"{check_type}://{host}:{port}"
                result["online"] = self._check_http(target_url)
            else:
                result["online"] = self._check_ping(host)
        except Exception as e:
            logger.warning("Health check failed for %s: %s", name, e)
            result["error"] = str(e)

        return result

    def _check_ping(self, host: str) -> bool:
        """Ping a host and return True if reachable."""
        if not host:
            return False
        try:
            param = "-n" if sys.platform == "win32" else "-c"
            cmd = ["ping", param, "1", "-W", "2", host]
            result = subprocess.run(
                cmd, capture_output=True, timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, Exception):
            return False

    def _check_http(self, url: str) -> bool:
        """Check if an HTTP endpoint is reachable."""
        if not url:
            return False
        try:
            r = requests.get(url, timeout=5, verify=False)
            return r.status_code < 500
        except Exception:
            return False

    def _format_single(self, result: Dict[str, Any], language: str) -> str:
        """Format a single server check result for TTS."""
        name = result["name"]
        online = result["online"]
        if language == "nl":
            status = "online" if online else "offline"
            return f"{name} is {status}."
        else:
            status = "online" if online else "offline"
            return f"{name} is {status}."

    def _format_all(self, results: List[Dict[str, Any]], language: str) -> str:
        """Format all server check results for TTS."""
        if not results:
            if language == "nl":
                return "Er zijn geen servers geconfigureerd."
            return "No servers are configured."

        online = [r for r in results if r["online"]]
        offline = [r for r in results if not r["online"]]

        if language == "nl":
            parts = []
            if online:
                names = ", ".join(r["name"] for r in online)
                parts.append(f"{len(online)} server{'s' if len(online) != 1 else ''} online: {names}")
            if offline:
                names = ", ".join(r["name"] for r in offline)
                parts.append(f"{len(offline)} server{'s' if len(offline) != 1 else ''} offline: {names}")
            return ". ".join(parts) + "."
        else:
            parts = []
            if online:
                names = ", ".join(r["name"] for r in online)
                parts.append(f"{len(online)} server{'s' if len(online) != 1 else ''} online: {names}")
            if offline:
                names = ", ".join(r["name"] for r in offline)
                parts.append(f"{len(offline)} server{'s' if len(offline) != 1 else ''} offline: {names}")
            return ". ".join(parts) + "."
