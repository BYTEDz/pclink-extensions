# 📦 PCLink Extensions Catalog

The following is a verified list of officially supported extensions. These are maintained for performance, security, and UI consistency with the PCLink ecosystem.

| Icon | Extension             | Description                                                        | Category     | Platforms |
| :--- | :-------------------- | :----------------------------------------------------------------- | :----------- | :-------- |
| 🎛️   | **The DJ Mixer**      | Deep integration with Windows Audio Engine for per-app control.    | Media        | 🪟        |
| 🌙   | **Night Owl**         | Display brightness and Night Light hardware control.               | Utility      | 🪟        |
| 📊   | **Gamer HUD**         | Ultra-low latency system telemetry for performance tuning.         | System       | 🪟 🐧 🍎  |
| 📈   | **PC Speed Test**     | High-precision broadband and LAN throughput diagnostics.           | Utility      | 🪟 🐧 🍎  |
| 🧹   | **Clean Master**      | Advanced optimization engine to remove system artifacts and junk.  | Utility      | 🪟 🐧 🍎  |
| 🛡️   | **Network Guard**     | Real-time firewall and bandwidth orchestration.                    | Security     | 🪟 🐧 🍎  |
| 📋   | **Clipboard History** | Synchronized storage for multi-device clipboard management.        | Productivity | 🪟        |
| 📝   | **Quick Notes**       | Minimalist persistent notes with instant cloud-less sync.          | Productivity | 🪟 🐧 🍎  |
| 🛠️   | **Dev Assistant**     | Developer orchestration tool for Git, NPM, and Flutter.            | Developer    | 🪟 🐧 🍎  |
| 📶   | **WiFi Sharer**       | One-tap credential sharing via secure local QR generation.         | Utility      | 🪟        |
| 🧪   | **Capabilities Demo** | Showcase of Fullscreen, Rotation, Keyboard, and Mouse UI features. | Developer    | 🪟 🐧 🍎  |

---

### Technical Specifications

- **Framework**: `PCLink Extension Core v2.0`
- **Frontend**: Standardized via **PCLink Theme SDK** for native UX consistency.
- **Backend**: Asynchronous Python processing with isolated dependency loading.

### Platform Legend

- 🪟 **Windows**: Deep integration via WinAPI and COM.
- 🐧 **Linux**: Native support for major distributions (Ubuntu, Fedora, Arch).
- 🍎 **macOS**: Optimized for modern macOS environments.

> [!TIP]  
> All extensions listed here are audited for the **PCLink Security Model**. Dangerous hardware permissions are explicitly declared in each manifest.
