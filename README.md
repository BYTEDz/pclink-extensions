<div align="center">

# PCLink Extensions

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Registry Status](https://github.com/BYTEDz/pclink-extensions/actions/workflows/package-extensions.yml/badge.svg)](https://github.com/BYTEDz/pclink-extensions/actions/workflows/package-extensions.yml)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![Extensions Catalog](https://img.shields.io/badge/Extensions-Browse%20Catalog-brightgreen)](EXTENSIONS.md)

**The official repository for [PCLink](https://github.com/BYTEDz/PCLink) extensions.**  
This repository contains extensions that provide additional features, automation capabilities, and workflow integrations for the PCLink ecosystem.

</div>

---

## <img src="https://api.iconify.design/lucide:book-open.svg?color=%23888888" width="18" height="18" alt="Documentation" valign="middle" /> Documentation

**Complete technical documentation is available in the [PCLink Wiki](https://github.com/BYTEDz/PCLink/wiki)**

- <img src="https://api.iconify.design/lucide:code.svg?color=%23888888" width="14" height="14" alt="Code" valign="middle" /> [Extension Development Guide](https://github.com/BYTEDz/PCLink/wiki/Extension-Development) - Guide for building extensions
- <img src="https://api.iconify.design/lucide:palette.svg?color=%23888888" width="14" height="14" alt="Theme" valign="middle" /> [Theme SDK](https://github.com/BYTEDz/PCLink/wiki/Theme-SDK) - Styling specifications for extension web UIs
- <img src="https://api.iconify.design/lucide:git-pull-request.svg?color=%23888888" width="14" height="14" alt="Contributing" valign="middle" /> [Contributing Guide](CONTRIBUTING.md) - Guidelines for submitting extensions
- <img src="https://api.iconify.design/lucide:cpu.svg?color=%23888888" width="14" height="14" alt="Architecture" valign="middle" /> [Marketplace Architecture](https://github.com/BYTEDz/PCLink/wiki/Marketplace-Architecture) - Overview of the registry ecosystem

---

## <img src="https://api.iconify.design/lucide:terminal.svg?color=%23888888" width="18" height="18" alt="Terminal" valign="middle" /> Quick Start

### <img src="https://api.iconify.design/lucide:download.svg?color=%23888888" width="16" height="16" alt="Download" valign="middle" /> Installing Extensions

1. **Browse the Marketplace**: Open the PCLink client application and navigate to the **Extensions** menu.
2. **Installation**: Select the target extension from the official directory to install it directly.
3. **Manual Installation**: Alternatively, download the compressed archive (`.zip` format) from the [Releases](https://github.com/BYTEDz/pclink-extensions/releases) page and load it via the manual installation option in the client.

### <img src="https://api.iconify.design/lucide:plus.svg?color=%23888888" width="16" height="16" alt="Plus" valign="middle" /> Creating Extensions

Developers can create custom integrations using the provided [Starter Template](templates/starter-template/) as a baseline for development.

---

## <img src="https://api.iconify.design/lucide:folder-tree.svg?color=%23888888" width="18" height="18" alt="Folder Tree" valign="middle" /> Repository Structure

```text
pclink-extensions/
├── extensions/          # Official extension implementations
├── scripts/             # Registry generation & automation tools
├── templates/           # Starter templates for developers
├── EXTENSIONS.md        # Human-readable catalog
└── extensions.json      # Machine-readable marketplace registry
```

---

## <img src="https://api.iconify.design/lucide:check-square.svg?color=%23888888" width="18" height="18" alt="Standards" valign="middle" /> Repository Standards

Extensions submitted to this repository must adhere to the following specifications:

- **Metadata Specification**: Every extension must include a valid `extension.yaml` file.
- **Asset Requirements**: Extension icons must be provided in PNG or SVG format and located at `static/icon.png`.
- **Security Compliance**: Sensitive or privileged permissions must be explicitly declared and documented in the configuration.
- **Resource Optimization**: Extensions must be designed for a low resource footprint and avoid unoptimized background execution.

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