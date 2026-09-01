<div align="center">

<img src="pclink_extensions_banner.svg" alt="PCLink Extensions Banner" width="100%" />

# PCLink Extensions

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Package & Lint Status](https://github.com/BYTEDz/pclink-extensions/actions/workflows/package.yml/badge.svg)](https://github.com/BYTEDz/pclink-extensions/actions/workflows/package.yml)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![Extensions Catalog](https://img.shields.io/badge/Extensions-Browse%20Catalog-brightgreen)](EXTENSIONS.md)

**The official repository for [PCLink](https://github.com/BYTEDz/PCLink) Manifest v2 extensions.**  
This repository houses official extensions, backend automation modules, dashboard widgets, and development templates for the PCLink ecosystem.

</div>

---

## <img src="https://api.iconify.design/lucide:book-open.svg?color=%23888888" width="18" height="18" alt="Documentation" valign="middle" /> Documentation

**Complete technical documentation is available in the [PCLink Wiki](https://github.com/BYTEDz/PCLink/wiki)**

- <img src="https://api.iconify.design/lucide:code.svg?color=%23888888" width="14" height="14" alt="Code" valign="middle" /> [Extension Development Guide](https://github.com/BYTEDz/PCLink/wiki/Extension-Development) - Architecture, Manifest v2, and runtime options
- <img src="https://api.iconify.design/lucide:palette.svg?color=%23888888" width="14" height="14" alt="Theme" valign="middle" /> [Host Broker SDK](https://github.com/BYTEDz/PCLink/wiki/Host-Broker-SDK) - Client broker API & Material 3 styling tokens
- <img src="https://api.iconify.design/lucide:git-pull-request.svg?color=%23888888" width="14" height="14" alt="Contributing" valign="middle" /> [Contributing Guide](CONTRIBUTING.md) - Guidelines for package submission and verification
- <img src="https://api.iconify.design/lucide:cpu.svg?color=%23888888" width="14" height="14" alt="Architecture" valign="middle" /> [Marketplace Architecture](https://github.com/BYTEDz/PCLink/wiki/Marketplace-Architecture) - Registry lifecycle and SHA-256 integrity checks

---

## <img src="https://api.iconify.design/lucide:terminal.svg?color=%23888888" width="18" height="18" alt="Terminal" valign="middle" /> Quick Start

### <img src="https://api.iconify.design/lucide:download.svg?color=%23888888" width="16" height="16" alt="Download" valign="middle" /> Installing Extensions

1. **Integrated Marketplace**: Open the PCLink Web UI or Companion App and navigate to **Extensions → Marketplace**. Select any extension for direct one-click installation.
2. **Manual Installation**: Drag and drop any `.pclink` bundle directly into the Web UI **Extensions** tab, or load it via direct URL.
3. **Release Binaries**: Download standalone `.pclink` packages from the [Releases](https://github.com/BYTEDz/pclink-extensions/releases) page.

### <img src="https://api.iconify.design/lucide:plus.svg?color=%23888888" width="16" height="16" alt="Plus" valign="middle" /> Creating Extensions

Developers can build custom extensions using the provided [Starter Template](templates/starter-template/) as a baseline. Extensions support multiple execution models:

- **Broker Mode (`runtime: "none"`)**: Pure client-side JavaScript leveraging host storage, media, power, and notifications without background process overhead.
- **Python Worker (`runtime: "python"`)**: Isolated FastAPI backend subprocess with system bindings and IPC logging.
- **Node.js Worker (`runtime: "node"`)**: Supervised JavaScript server process.
- **Native Binary (`runtime: "binary"`)**: Pre-compiled platform executable (Rust, Go, C++).

---

## <img src="https://api.iconify.design/lucide:folder-tree.svg?color=%23888888" width="18" height="18" alt="Folder Tree" valign="middle" /> Repository Structure

```text
pclink-extensions/
├── extensions/          # Official Manifest v2 extension packages
├── scripts/             # Registry compiler, SHA-256 calculator & CI linter
│   ├── generate_registry.py
│   └── lint_extensions.py
├── templates/           # Starter template for developers
│   └── starter-template/
├── EXTENSIONS.md        # Human-readable catalog
└── extensions.json      # Machine-readable lean marketplace registry
```

---

## <img src="https://api.iconify.design/lucide:check-square.svg?color=%23888888" width="18" height="18" alt="Standards" valign="middle" /> Repository Standards

Extensions submitted to this repository must adhere to the following specifications:

- **Manifest Specification**: Every extension must include a valid `manifest.json` conforming to Manifest v2 (`manifest_version: 2`).
- **Target Compatibility**: Manifests must declare `min_server_version: "4.8.0"` and `pclink_version: ">=4.9.0"`.
- **Package Format**: Extensions are bundled as `.pclink` archives containing `manifest.json` at the root directory level.
- **Security Compliance**: Privileged capabilities (`system.exec`, `fs.write`, `input.inject`, `power.control`) must be explicitly specified under `permissions` and `declared_permissions`.
- **Static Verification**: All contributions must pass `python scripts/lint_extensions.py` before pull requests are merged.

---

## <img src="https://api.iconify.design/lucide:users.svg?color=%23888888" width="18" height="18" alt="Maintainers" valign="middle" /> Maintainers

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/AzharZouhir">
        <img src="https://github.com/AzharZouhir.png" width="100px;" alt="Azhar Zouhir"/>
        <br />
        <sub><b>Azhar Zouhir</b></sub>
      </a>
      <br />
      <sub>Creator & Lead Developer</sub>
      <br />
      <a href="mailto:support@bytedz.com"><img src="https://api.iconify.design/lucide:mail.svg?color=%23888888" width="14" height="14" alt="Email" valign="middle" /></a>
      <a href="https://github.com/AzharZouhir"><img src="https://api.iconify.design/lucide:github.svg?color=%23888888" width="14" height="14" alt="GitHub" valign="middle" /></a>
    </td>
  </tr>
</table>

---

<div align="center">

Free Palestine • Developed in Algeria

</div>