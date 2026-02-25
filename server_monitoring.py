"""Server monitoring plugin - health checks via ping, HTTP(S), and SSH."""

import html as html_mod
import json
import logging
import re
import time
from typing import Any, Dict, List

from ..base import ConfigField, DashboardPage, DashboardWidget, PluginBase, PluginMeta

logger = logging.getLogger(__name__)


class ServerMonitoringPlugin(PluginBase):
    """Server monitoring integration as a plugin."""

    @property
    def meta(self) -> PluginMeta:
        return PluginMeta(
            name="server_monitoring",
            display_name="Server Monitoring",
            description="Periodic health checks via ping, HTTP(S), and SSH",
            version="2.0.0",
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
            ConfigField(
                key="MONITORING_CHECK_INTERVAL",
                label="Check Interval (sec)",
                default="60",
                hot_reload=True,
            ),
        ]

    # --- Dashboard ---

    @property
    def dashboard_pages(self) -> List[DashboardPage]:
        return [
            DashboardPage(id="settings", title="Settings", type="config"),
            DashboardPage(id="status", title="Server Status", type="custom"),
        ]

    @property
    def dashboard_widgets(self) -> List[DashboardWidget]:
        return [
            DashboardWidget(
                id="status_overview",
                title="Server Status",
                icon="monitor",
                size="small",
                order=30,
            ),
        ]

    # --- Lifecycle ---

    def setup(self, context) -> None:
        super().setup(context)
        self._handler = None

    def on_enable(self) -> None:
        from .handler import MonitoringHandler
        servers = self._load_servers()
        self._handler = MonitoringHandler(servers)

    def on_disable(self) -> None:
        self._handler = None

    def test_connection(self) -> bool:
        servers = self._load_servers()
        if not servers:
            return True
        from .handler import MonitoringHandler
        handler = MonitoringHandler(servers)
        results = handler.check_all()
        return any(r.get("online") for r in results)

    # --- Handle voice commands ---

    def handle(self, text: str, language: str = "en") -> str:
        if not self._handler:
            return self._msg(
                "Monitoring is not available.",
                "Monitoring is niet beschikbaar.",
                language,
            )
        return self._handler.handle(text, language)

    def check_all(self) -> List[str]:
        """Return alert strings for the monitoring loop in agent.py.

        Only returns alerts for servers that transitioned from online to offline.
        Returns an empty list when all servers are stable.
        """
        if self._handler:
            return self._handler.get_alerts()
        return []

    # --- API Actions (via generic plugin action route) ---

    def handle_api_action(self, action: str, data: dict) -> dict:
        if action == "servers/list":
            return {"servers": self._load_servers()}

        if action == "servers/status":
            return self._action_full_status()

        if action == "servers/add":
            return self._action_add_server(data)

        m = re.match(r"^servers/(\d+)/(delete|test|update)$", action)
        if m:
            index = int(m.group(1))
            op = m.group(2)
            if op == "delete":
                return self._action_delete_server(index)
            if op == "test":
                return self._action_test_server(index)
            if op == "update":
                return self._action_update_server(index, data)

        return {"error": "Unknown action"}

    def _action_add_server(self, data: dict) -> dict:
        name = data.get("name", "").strip()
        check_type = data.get("type", "ping").strip().lower()
        host = data.get("host", "").strip()
        port = data.get("port", "").strip()
        url = data.get("url", "").strip()

        if not name:
            return {"error": "Server name is required"}
        if check_type in ("http", "https") and not url:
            return {"error": "URL is required for HTTP(S)"}
        if check_type in ("ping", "ssh") and not host:
            return {"error": "Host is required for " + check_type.upper()}
        if check_type not in ("ping", "http", "https", "ssh"):
            return {"error": "Type must be ping, http, https, or ssh"}

        server = {"name": name, "type": check_type, "host": host}
        if port:
            server["port"] = int(port)
        if url:
            server["url"] = url

        servers = self._load_servers()
        servers.append(server)
        self._save_servers(servers)
        return {"success": True, "server": server}

    def _action_delete_server(self, index: int) -> dict:
        servers = self._load_servers()
        if index < 0 or index >= len(servers):
            return {"error": "Invalid server index"}
        removed = servers.pop(index)
        self._save_servers(servers)
        logger.info("Deleted server %s (index %d), %d remaining", removed.get("name"), index, len(servers))
        return {"success": True, "removed": removed}

    def _action_test_server(self, index: int) -> dict:
        servers = self._load_servers()
        if index < 0 or index >= len(servers):
            return {"error": "Invalid server index"}
        from .handler import MonitoringHandler
        handler = MonitoringHandler(servers)
        return handler._check_server(servers[index])

    def _action_update_server(self, index: int, data: dict) -> dict:
        servers = self._load_servers()
        if index < 0 or index >= len(servers):
            return {"error": "Invalid server index"}

        name = data.get("name", "").strip()
        check_type = data.get("type", "ping").strip().lower()
        host = data.get("host", "").strip()
        port = data.get("port", "").strip()
        url = data.get("url", "").strip()

        if not name:
            return {"error": "Server name is required"}
        if check_type in ("http", "https") and not url:
            return {"error": "URL is required for HTTP(S)"}
        if check_type in ("ping", "ssh") and not host:
            return {"error": "Host is required for " + check_type.upper()}
        if check_type not in ("ping", "http", "https", "ssh"):
            return {"error": "Type must be ping, http, https, or ssh"}

        server = {"name": name, "type": check_type, "host": host}
        if port:
            server["port"] = int(port)
        if url:
            server["url"] = url

        servers[index] = server
        self._save_servers(servers)
        logger.info("Updated server %s (index %d)", name, index)
        return {"success": True, "server": server}

    def _action_full_status(self) -> dict:
        """Return full status from the last monitoring cycle."""
        if self._handler:
            return self._handler.get_full_status()
        from .handler import MonitoringHandler
        servers = self._load_servers()
        if not servers:
            return {"servers": [], "last_check": 0}
        handler = MonitoringHandler(servers)
        results = handler.check_all()
        return {"servers": results, "last_check": time.time()}

    # --- Dashboard rendering ---

    def render_widget(self, widget_id: str) -> str:
        if widget_id == "status_overview":
            return self._render_status_widget()
        return ""

    def render_page(self, page_id: str) -> str:
        if page_id == "settings":
            return self._render_settings_page()
        if page_id == "status":
            return self._render_status_page()
        return ""

    # --- Internal helpers ---

    def _load_servers(self) -> List[Dict[str, Any]]:
        """Load server list from database/env."""
        raw = self.context.get_env("MONITORING_SERVERS", "[]") if self.context else "[]"
        # Strip surrounding quotes (from .env shell syntax)
        if raw and len(raw) >= 2:
            if (raw[0] == "'" and raw[-1] == "'") or (raw[0] == '"' and raw[-1] == '"'):
                raw = raw[1:-1]
        try:
            servers = json.loads(raw) if raw else []
        except json.JSONDecodeError:
            logger.warning("Failed to parse MONITORING_SERVERS: %s", raw[:100])
            servers = []
        return servers if isinstance(servers, list) else []

    def _save_servers(self, servers: List[Dict[str, Any]]) -> None:
        """Save server list to database and update handler."""
        self.context.set_env("MONITORING_SERVERS", json.dumps(servers))
        if self._handler:
            self._handler.update_servers(servers)

    def _render_status_widget(self) -> str:
        """Compact widget showing online/offline counts."""
        return """
        <div id="mon-widget" style="text-align:center;padding:8px">
            <div id="mon-widget-text" style="color:#94a3b8">Loading...</div>
        </div>
        <script>
        (function() {
            const A = '/api/plugins/server_monitoring/action';
            async function refresh() {
                try {
                    const r = await fetch(A + '/servers/status');
                    const d = await r.json();
                    const results = d.servers || [];
                    if (!results.length) {
                        document.getElementById('mon-widget-text').innerHTML =
                            '<span style="color:#64748b">No servers configured</span>';
                        return;
                    }
                    const on = results.filter(r => r.online).length;
                    const off = results.length - on;
                    let html = '';
                    if (on) html += '<span style="color:#22c55e;font-weight:600">' + on + ' online</span>';
                    if (on && off) html += ' &middot; ';
                    if (off) html += '<span style="color:#ef4444;font-weight:600">' + off + ' offline</span>';
                    document.getElementById('mon-widget-text').innerHTML = html;
                } catch(e) {
                    document.getElementById('mon-widget-text').innerHTML =
                        '<span style="color:#ef4444">Error</span>';
                }
            }
            refresh();
            setInterval(refresh, 30000);
        })();
        </script>
        """

    def _render_settings_page(self) -> str:
        """Settings page with server management form."""
        interval = self.context.get_env("MONITORING_CHECK_INTERVAL", "60") if self.context else "60"
        servers = self._load_servers()
        servers_json = json.dumps(servers)

        # Build server table HTML server-side so it renders without JS
        if servers:
            rows = ""
            for i, s in enumerate(servers):
                name = html_mod.escape(s.get("name", ""))
                stype = s.get("type", "ping")
                type_label = "HTTP(S)" if stype in ("http", "https") else stype.upper()
                target_raw = s.get("url") or (
                    s.get("host", "") + (":" + str(s["port"]) if s.get("port") else "")
                )
                target = html_mod.escape(target_raw)
                rows += (
                    f'<tr id="mon-row-{i}" style="border-bottom:1px solid #1e293b">'
                    f'<td style="padding:6px 8px;font-weight:500">{name}</td>'
                    f'<td style="padding:6px 8px;color:#94a3b8;font-size:0.85rem">{type_label}</td>'
                    f'<td style="padding:6px 8px;color:#94a3b8;font-size:0.85rem">{target}</td>'
                    f'<td id="mon-st-{i}" style="padding:6px 8px;text-align:center;color:#64748b;font-size:0.85rem">-</td>'
                    f'<td style="padding:4px 8px;text-align:right;white-space:nowrap">'
                    f'<button class="btn-sm" onclick="monEdit({i})" style="margin-right:4px;font-size:0.75rem;padding:2px 8px">Edit</button>'
                    f'<button class="btn-sm" onclick="monTest({i})" style="margin-right:4px;font-size:0.75rem;padding:2px 8px">Test</button>'
                    f'<button class="btn-sm" onclick="monDel({i})" style="background:#7f1d1d;font-size:0.75rem;padding:2px 8px">Delete</button>'
                    f"</td></tr>"
                )
            table_html = (
                '<table style="width:100%;border-collapse:collapse">'
                '<tr style="border-bottom:1px solid #334155;color:#94a3b8;font-size:0.75rem">'
                '<th style="text-align:left;padding:4px 8px">Name</th>'
                '<th style="text-align:left;padding:4px 8px">Type</th>'
                '<th style="text-align:left;padding:4px 8px">Target</th>'
                '<th style="text-align:center;padding:4px 8px;width:80px">Status</th>'
                '<th style="text-align:right;padding:4px 8px;width:160px"></th></tr>'
                + rows + "</table>"
            )
        else:
            table_html = '<p style="color:#64748b;margin:0">No servers configured yet. Add one below.</p>'

        # JavaScript in a regular string to avoid f-string brace escaping
        js_code = """
(function() {
    var MON_ACT = '/api/plugins/server_monitoring/action';
    var monServers = __SERVERS_JSON__;

    function _esc(s) {
        if (!s && s !== 0) return '';
        var d = document.createElement('div');
        d.textContent = String(s);
        return d.innerHTML.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function monRender(servers) {
        monServers = servers;
        var el = document.getElementById('mon-server-list');
        if (!el) return;
        if (!servers.length) {
            el.innerHTML = '<p style="color:#64748b;margin:0">No servers configured yet. Add one below.</p>';
            return;
        }
        var h = '<table style="width:100%;border-collapse:collapse">';
        h += '<tr style="border-bottom:1px solid #334155;color:#94a3b8;font-size:0.75rem">'
            + '<th style="text-align:left;padding:4px 8px">Name</th>'
            + '<th style="text-align:left;padding:4px 8px">Type</th>'
            + '<th style="text-align:left;padding:4px 8px">Target</th>'
            + '<th style="text-align:center;padding:4px 8px;width:80px">Status</th>'
            + '<th style="text-align:right;padding:4px 8px;width:160px"></th></tr>';
        servers.forEach(function(s, i) {
            var tl = (s.type === 'http' || s.type === 'https') ? 'HTTP(S)' : s.type.toUpperCase();
            var tgt = s.url || (s.host + (s.port ? ':' + s.port : ''));
            h += '<tr id="mon-row-' + i + '" style="border-bottom:1px solid #1e293b">'
                + '<td style="padding:6px 8px;font-weight:500">' + _esc(s.name) + '</td>'
                + '<td style="padding:6px 8px;color:#94a3b8;font-size:0.85rem">' + tl + '</td>'
                + '<td style="padding:6px 8px;color:#94a3b8;font-size:0.85rem">' + _esc(tgt) + '</td>'
                + '<td id="mon-st-' + i + '" style="padding:6px 8px;text-align:center;color:#64748b;font-size:0.85rem">-</td>'
                + '<td style="padding:4px 8px;text-align:right;white-space:nowrap">'
                + '<button class="btn-sm" onclick="monEdit(' + i + ')" style="margin-right:4px;font-size:0.75rem;padding:2px 8px">Edit</button>'
                + '<button class="btn-sm" onclick="monTest(' + i + ')" style="margin-right:4px;font-size:0.75rem;padding:2px 8px">Test</button>'
                + '<button class="btn-sm" onclick="monDel(' + i + ')" style="background:#7f1d1d;font-size:0.75rem;padding:2px 8px">Delete</button>'
                + '</td></tr>';
        });
        h += '</table>';
        el.innerHTML = h;
    }

    async function monRefresh() {
        try {
            var r = await fetch(MON_ACT + '/servers/list');
            var d = await r.json();
            monRender(d.servers || []);
        } catch(e) {
            var el = document.getElementById('mon-server-list');
            if (el) el.innerHTML = '<p style="color:#ef4444">Failed to load servers: ' + e + '</p>';
        }
    }

    window.monTypeChanged = function() {
        var type = document.getElementById('mon-type').value;
        var hostWrap = document.getElementById('mon-host-wrap');
        var portWrap = document.getElementById('mon-port-wrap');
        var urlWrap = document.getElementById('mon-url-wrap');
        if (type === 'http') {
            hostWrap.style.display = 'none';
            portWrap.style.display = 'none';
            urlWrap.style.display = '';
        } else if (type === 'ssh') {
            hostWrap.style.display = '';
            portWrap.style.display = '';
            urlWrap.style.display = 'none';
        } else {
            hostWrap.style.display = '';
            portWrap.style.display = 'none';
            urlWrap.style.display = 'none';
        }
    };

    window.monAdd = async function() {
        var type = document.getElementById('mon-type').value;
        var name = document.getElementById('mon-name').value.trim();
        var host = document.getElementById('mon-host').value.trim();
        var port = document.getElementById('mon-port').value.trim();
        var url = document.getElementById('mon-url').value.trim();
        if (!name) { alert('Name is required'); return; }
        if (type === 'http' && !url) { alert('URL is required for HTTP(S)'); return; }
        if ((type === 'ping' || type === 'ssh') && !host) { alert('Host is required'); return; }
        try {
            var body = {name: name, type: type, host: host, port: port, url: url};
            if (type === 'http' && url.startsWith('https://')) body.type = 'https';
            var r = await fetch(MON_ACT + '/servers/add', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(body),
            });
            var d = await r.json();
            if (d.success) {
                document.getElementById('mon-name').value = '';
                document.getElementById('mon-host').value = '';
                document.getElementById('mon-port').value = '';
                document.getElementById('mon-url').value = '';
                monRefresh();
                try { toast('Server added!', 'success'); } catch(_) {}
            } else {
                var msg = d.error || 'Failed to add server';
                try { toast(msg, 'error'); } catch(_) { alert(msg); }
            }
        } catch(e) {
            try { toast('Error: ' + e, 'error'); } catch(_) { alert('Error: ' + e); }
        }
    };

    window.monDel = async function(index) {
        if (!confirm('Delete this server?')) return;
        try {
            var r = await fetch(MON_ACT + '/servers/' + index + '/delete', {method: 'POST'});
            var d = await r.json();
            if (d.success) {
                monRefresh();
                try { toast('Server removed', 'success'); } catch(_) {}
            } else {
                var msg = d.error || 'Failed to delete';
                try { toast(msg, 'error'); } catch(_) { alert(msg); }
            }
        } catch(e) {
            try { toast('Error: ' + e, 'error'); } catch(_) { alert('Error: ' + e); }
        }
    };

    window.monTest = async function(index) {
        var el = document.getElementById('mon-st-' + index);
        if (!el) return;
        el.innerHTML = '...';
        el.style.color = '#94a3b8';
        try {
            var r = await fetch(MON_ACT + '/servers/' + index + '/test', {method: 'POST'});
            var d = await r.json();
            var rt = d.response_time_ms != null ? ' (' + d.response_time_ms + 'ms)' : '';
            if (d.online) {
                el.innerHTML = '&#9679; Online' + rt;
                el.style.color = '#22c55e';
            } else {
                el.innerHTML = '&#9679; Offline';
                el.style.color = '#ef4444';
            }
        } catch(e) {
            el.innerHTML = 'Error';
            el.style.color = '#ef4444';
        }
    };

    window.monTestAll = async function() {
        for (var i = 0; i < monServers.length; i++) window.monTest(i);
    };

    window.monEdit = function(index) {
        var s = monServers[index];
        var row = document.getElementById('mon-row-' + index);
        if (!row || !s) return;
        var isHttp = s.type === 'http' || s.type === 'https';
        var isSsh = s.type === 'ssh';
        row.innerHTML = '<td style="padding:6px 8px">'
            + '<input id="mon-en-' + index + '" value="' + _esc(s.name) + '" placeholder="Name" style="width:100%">'
            + '</td>'
            + '<td style="padding:6px 8px">'
            + '<select id="mon-et-' + index + '" onchange="monEditType(' + index + ')" style="width:100%">'
            + '<option value="ping"' + (s.type === 'ping' ? ' selected' : '') + '>Ping</option>'
            + '<option value="http"' + (isHttp ? ' selected' : '') + '>HTTP(S)</option>'
            + '<option value="ssh"' + (isSsh ? ' selected' : '') + '>SSH</option>'
            + '</select>'
            + '</td>'
            + '<td style="padding:6px 8px">'
            + '<span id="mon-ehw-' + index + '"' + (isHttp ? ' style="display:none"' : '') + '>'
            + '<input id="mon-eh-' + index + '" value="' + _esc(s.host || '') + '" placeholder="Host / IP" style="width:' + (isSsh ? '70%' : '100%') + '">'
            + '<input id="mon-ep-' + index + '" value="' + _esc(String(s.port || '')) + '" placeholder="22" style="width:25%;margin-left:5%' + (isSsh ? '' : ';display:none') + '">'
            + '</span>'
            + '<span id="mon-euw-' + index + '"' + (!isHttp ? ' style="display:none"' : '') + '>'
            + '<input id="mon-eu-' + index + '" value="' + _esc(s.url || '') + '" placeholder="URL" style="width:100%">'
            + '</span>'
            + '</td>'
            + '<td></td>'
            + '<td style="padding:4px 8px;text-align:right;white-space:nowrap">'
            + '<button class="btn-sm" onclick="monSaveEdit(' + index + ')" style="margin-right:4px;font-size:0.75rem;padding:2px 8px;background:#166534">Save</button>'
            + '<button class="btn-sm" onclick="monCancelEdit()" style="font-size:0.75rem;padding:2px 8px">Cancel</button>'
            + '</td>';
    };

    window.monEditType = function(index) {
        var type = document.getElementById('mon-et-' + index).value;
        var hw = document.getElementById('mon-ehw-' + index);
        var uw = document.getElementById('mon-euw-' + index);
        var ep = document.getElementById('mon-ep-' + index);
        var eh = document.getElementById('mon-eh-' + index);
        if (type === 'http') {
            hw.style.display = 'none';
            uw.style.display = '';
        } else if (type === 'ssh') {
            hw.style.display = '';
            uw.style.display = 'none';
            ep.style.display = '';
            eh.style.width = '70%';
        } else {
            hw.style.display = '';
            uw.style.display = 'none';
            ep.style.display = 'none';
            eh.style.width = '100%';
        }
    };

    window.monSaveEdit = async function(index) {
        var type = document.getElementById('mon-et-' + index).value;
        var name = document.getElementById('mon-en-' + index).value.trim();
        var host = document.getElementById('mon-eh-' + index).value.trim();
        var port = document.getElementById('mon-ep-' + index).value.trim();
        var url = document.getElementById('mon-eu-' + index).value.trim();
        if (!name) { alert('Name is required'); return; }
        var body = {name: name, type: type, host: host, port: port, url: url};
        if (type === 'http' && url.startsWith('https://')) body.type = 'https';
        try {
            var r = await fetch(MON_ACT + '/servers/' + index + '/update', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(body),
            });
            var d = await r.json();
            if (d.success) {
                monRefresh();
                try { toast('Server updated!', 'success'); } catch(_) {}
            } else {
                var msg = d.error || 'Update failed';
                try { toast(msg, 'error'); } catch(_) { alert(msg); }
            }
        } catch(e) {
            try { toast('Error: ' + e, 'error'); } catch(_) { alert('Error: ' + e); }
        }
    };

    window.monCancelEdit = function() {
        monRender(monServers);
    };

    window.monSaveInterval = async function() {
        var val = document.getElementById('mon-interval').value;
        try {
            await fetch('/api/config/', {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({key: 'MONITORING_CHECK_INTERVAL', value: val}),
            });
            try { toast('Interval saved!', 'success'); } catch(_) {}
        } catch(e) {
            try { toast('Save failed: ' + e, 'error'); } catch(_) { alert('Save failed: ' + e); }
        }
    };
})();
""".replace("__SERVERS_JSON__", servers_json)

        return f"""
        <div class="card" style="margin-bottom:16px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
                <h3 style="margin:0">Servers</h3>
                <button class="btn-sm" onclick="monTestAll()">Test All</button>
            </div>
            <div id="mon-server-list">
                {table_html}
            </div>
            <div style="border-top:1px solid #334155;margin-top:16px;padding-top:16px">
                <h4 style="margin:0 0 12px 0;font-size:0.9rem;color:#94a3b8">Add Server</h4>
                <div style="display:flex;gap:8px;align-items:end;flex-wrap:wrap">
                    <div style="min-width:100px">
                        <label style="font-size:0.75rem;color:#64748b;display:block;margin-bottom:2px">Type</label>
                        <select id="mon-type" onchange="monTypeChanged()" style="width:100%">
                            <option value="ping">Ping</option>
                            <option value="http">HTTP(S)</option>
                            <option value="ssh">SSH</option>
                        </select>
                    </div>
                    <div style="flex:1;min-width:120px">
                        <label style="font-size:0.75rem;color:#64748b;display:block;margin-bottom:2px">Name</label>
                        <input id="mon-name" type="text" placeholder="Web Server" style="width:100%">
                    </div>
                    <div id="mon-host-wrap" style="flex:1;min-width:120px">
                        <label style="font-size:0.75rem;color:#64748b;display:block;margin-bottom:2px">Host / IP</label>
                        <input id="mon-host" type="text" placeholder="192.168.1.1" style="width:100%">
                    </div>
                    <div id="mon-port-wrap" style="width:80px;display:none">
                        <label style="font-size:0.75rem;color:#64748b;display:block;margin-bottom:2px">Port</label>
                        <input id="mon-port" type="text" placeholder="22" style="width:100%">
                    </div>
                    <div id="mon-url-wrap" style="flex:2;min-width:200px;display:none">
                        <label style="font-size:0.75rem;color:#64748b;display:block;margin-bottom:2px">URL</label>
                        <input id="mon-url" type="text" placeholder="https://example.com/health" style="width:100%">
                    </div>
                    <button class="btn-sm" onclick="monAdd()" style="white-space:nowrap;height:32px">Add</button>
                </div>
            </div>
        </div>
        <div class="card">
            <h3>Settings</h3>
            <div class="form-row">
                <label>Check Interval (seconds)</label>
                <div style="display:flex;gap:6px">
                    <input id="mon-interval" type="number" value="{interval}" min="10" style="flex:1">
                    <button class="btn-sm" onclick="monSaveInterval()">Save</button>
                </div>
                <small style="color:#64748b">How often the background monitoring loop checks all servers.</small>
            </div>
        </div>
        <script>{js_code}</script>
        """

    def _render_status_page(self) -> str:
        """Live status page with auto-refresh."""
        return """
        <div class="card">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
                <h3 style="margin:0">Server Status</h3>
                <button class="btn-sm" onclick="monStatusRefresh()">Refresh</button>
            </div>
            <div id="mon-status-list">
                <p style="color:#94a3b8">Checking servers...</p>
            </div>
        </div>
        <script>
        const MON_ACT_S = '/api/plugins/server_monitoring/action';

        async function monStatusRefresh() {
            const el = document.getElementById('mon-status-list');
            try {
                const r = await fetch(MON_ACT_S + '/servers/status');
                const d = await r.json();
                const results = d.servers || [];
                const lastCheck = d.last_check;
                if (!results.length) {
                    el.innerHTML = '<p style="color:#64748b">No servers configured. Go to Settings to add servers.</p>';
                    return;
                }

                let html = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px">';
                results.forEach((r, i) => {
                    const color = r.online ? '#22c55e' : '#ef4444';
                    const status = r.online ? 'Online' : 'Offline';
                    const bg = r.online ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)';
                    const typeLabel = (r.type === 'http' || r.type === 'https') ? 'HTTP(S)' : r.type.toUpperCase();
                    const rtMs = r.response_time_ms != null ? r.response_time_ms + ' ms' : '-';
                    html += '<div style="background:' + bg + ';border:1px solid ' + color + '33;border-radius:8px;padding:12px">'
                        + '<div style="font-weight:600;margin-bottom:4px">' + r.name + '</div>'
                        + '<div style="color:' + color + ';font-size:0.9rem;font-weight:500">' + status + '</div>'
                        + '<div style="color:#64748b;font-size:0.75rem;margin-top:4px">' + typeLabel + ' &middot; ' + (r.host || '') + '</div>'
                        + '<div style="color:#64748b;font-size:0.75rem;margin-top:2px">Response: ' + rtMs + '</div>'
                        + '</div>';
                });
                html += '</div>';
                if (lastCheck) {
                    const ago = Math.round((Date.now() / 1000 - lastCheck));
                    html += '<p style="color:#64748b;font-size:0.75rem;margin-top:12px">Last checked: '
                        + (ago < 60 ? ago + 's ago' : Math.round(ago / 60) + 'm ago') + '</p>';
                }
                el.innerHTML = html;
            } catch(e) {
                el.innerHTML = '<p style="color:#ef4444">Failed to check servers: ' + e + '</p>';
            }
        }

        monStatusRefresh();
        setInterval(monStatusRefresh, 30000);
        </script>
        """
