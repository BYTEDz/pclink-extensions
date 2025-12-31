# PCLink Extensions

Official extensions repository for [PCLink](https://github.com/BYTEDz/pclink) - Control your PC from your phone.

## 📁 Repository Structure

```
pclink-extensions/
├── extensions/          # All extension implementations
├── templates/           # Starter templates
└── README.md           # This file
```

## 🚀 Quick Start

### Installing Extensions

1. Download the extension `.zip` file
2. Open PCLink app → Extensions → Install
3. Select the downloaded file
4. Enable the extension

### Creating Extensions

See the **PCLink Wiki** for the detailed Extension Development Guide.

## 📦 Available Extensions

Browse the full [**Extensions Catalog**](EXTENSIONS.md) to see all officially supported extensions, their descriptions, and platform compatibility.

## 🛠️ Development

### Prerequisites

- Python 3.11+
- PCLink Server 8.9.0+

### Extension Structure

```
your-extension/
├── extension.yaml       # Metadata
├── extension.py         # Backend logic
└── templates/           # Web UI (optional)
    └── index.html
```

### Quick Template

Use the template in `templates/starter-template/` to get started quickly.

- **PCLink Wiki**: Complete developer documentation.

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork this repository
2. Create your extension in `extensions/`
3. Test thoroughly
4. Submit a pull request

## 📄 License

AGPL-3.0 - See LICENSE file for details

## 🔗 Links

- [PCLink Main Repository](https://github.com/BYTEDz/pclink)
- [Documentation](https://pclink.bytedz.xyz)
- [Discord Community](https://discord.gg/pclink)
