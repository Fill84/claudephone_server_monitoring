# ClaudePhone Server Monitoring Plugin

A server monitoring plugin for [ClaudePhone](https://github.com/Fill84/ClaudePhone) that provides health checks via ping and HTTP.

## Features

- **Ping checks** — verify servers are reachable via ICMP ping
- **HTTP/HTTPS checks** — check if web endpoints are responding
- **Individual or bulk** — check a single server by name or all at once
- **Bilingual** — full Dutch and English support with automatic language detection
- **Dashboard settings page** — configure servers and check interval from the web UI
- **JSON configuration** — flexible server list with name, type, host, port, and URL

## Requirements

- [ClaudePhone](https://github.com/Fill84/ClaudePhone) installed and running

## Installation

### Via Dashboard (recommended)

1. Open the ClaudePhone dashboard
2. Go to the **Plugins** tab
3. Enter the GitHub repository URL and click **Install**

### Manual

Copy the `monitoring` directory into `src/plugins/` in your ClaudePhone installation and restart the container.

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `MONITORING_SERVERS` | JSON array of server objects (see below) | `[]` |
| `MONITORING_CHECK_INTERVAL` | Health check interval in seconds | `60` |

### Server object format

```json
[
  {"name": "Web", "type": "ping", "host": "192.168.1.1"},
  {"name": "API", "type": "http", "host": "api.example.com", "port": 8080},
  {"name": "Dashboard", "type": "https", "url": "https://dashboard.example.com/health"}
]
```

Each server object supports the following fields:

| Field | Description | Required |
|-------|-------------|----------|
| `name` | Display name of the server | yes |
| `type` | Check type: `ping`, `http`, or `https` | yes |
| `host` | Hostname or IP address | yes (unless `url` is set) |
| `port` | Port number for HTTP/HTTPS checks | no |
| `url` | Full URL for HTTP/HTTPS checks (overrides host/port) | no |

Configure these via the dashboard Settings page.

## Usage

Once configured, ask about server status during a phone call:

- "Server status" / "Server status"
- "Are the servers online?" / "Zijn de servers online?"
- "Check Web" / "Controleer Web"
- "Ping storage-unit" / "Ping storage-unit"

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
