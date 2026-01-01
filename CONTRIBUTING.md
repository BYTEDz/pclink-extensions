# Contributing to PCLink Extensions

Thank you for your interest in contributing to PCLink Extensions! 🎉

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How to Contribute](#how-to-contribute)
- [Extension Guidelines](#extension-guidelines)
- [Submission Process](#submission-process)
- [Development Setup](#development-setup)

## 🤝 Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Focus on what is best for the community

## 🚀 How to Contribute

### Reporting Bugs

1. Check if the bug has already been reported
2. Create a detailed issue with:
   - Extension name and version
   - PCLink version
   - Steps to reproduce
   - Expected vs actual behavior
   - Screenshots if applicable

### Suggesting Features

1. Open an issue with the `enhancement` label
2. Describe the feature and its use case
3. Explain why it would be valuable

### Contributing Code

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-extension`)
3. Commit your changes (`git commit -m 'Add amazing extension'`)
4. Push to the branch (`git push origin feature/amazing-extension`)
5. Open a Pull Request

## 📝 Extension Guidelines

### Naming Convention

- Use lowercase with hyphens: `my-extension`
- Keep names descriptive and concise

### Code Quality

- **Follow PEP 8** for Python code
- **Add docstrings** to all classes and functions
- **Use type hints** where applicable
- **Handle errors gracefully** with proper logging
- **Test thoroughly** before submitting

### Security

- **Never hardcode credentials** or API keys
- **Validate all user input**
- **Use HTTPS** for external requests
- **Respect user privacy** - don't collect unnecessary data
- **Declare all permissions** in `extension.yaml`

### Performance

- **Minimize resource usage** (CPU, memory, network)
- **Use async/await** for I/O operations
- **Clean up resources** in the `cleanup()` method
- **Avoid blocking operations** in the main thread

### UI Design

- **Follow PCLink design language** (dark theme, modern UI)
- **Make it responsive** for different screen sizes
- **Use semantic HTML**
- **Optimize images** and assets
- **Test on mobile devices**

### 📚 Available Libraries (Don't Bundle These!)

PCLink ships with these libraries. **Import them directly** - no need to add to `lib/`:

**Core (All Platforms):**
`fastapi`, `pydantic`, `websockets`, `psutil`, `pyperclip`, `mss`, `keyboard`, `requests`, `cryptography`, `pyautogui`, `pynput`, `PyYAML`, `qrcode`, `aiofiles`, `Pillow`, `python-multipart`

**Windows Only:**
`pycaw`, `pywin32`, `comtypes`, `winsdk`

> 💡 See the [Extension Development Guide](https://github.com/BYTEDz/PCLink/wiki/Extension-Development) for version details.

## 📤 Submission Process

### 1. Prepare Your Extension

```bash
cd extensions/your-extension
# Ensure all files are present
ls -la
```

### 2. Test Locally

```bash
# Copy to PCLink extensions directory
cp -r your-extension ~/.pclink/extensions/

# Restart PCLink and test
# Check logs: tail -f ~/.pclink/pclink.log
```

### 3. Create Documentation

Add a README.md in your extension directory:

```markdown
# Extension Name

Brief description

## Features
- Feature 1
- Feature 2

## Installation
1. Step 1
2. Step 2

## Usage
How to use the extension

## Dependencies
- dependency1
- dependency2

## Screenshots
![Screenshot](screenshot.png)
```

### 4. Package for Distribution

```bash
cd your-extension
zip -r ../your-extension.zip .
```

### 5. Submit Pull Request

- Include extension in `extensions/` directory
- Update main README.md with extension info
- Add screenshots to `docs/screenshots/`
- Fill out the PR template

## 🛠️ Development Setup

### Prerequisites

```bash
# Python 3.11+
python --version

# PCLink Server
git clone https://github.com/BYTEDz/pclink.git
cd pclink
pip install -e .
```

### Local Testing

```bash
# Set custom extensions path
export PCLINK_EXTENSIONS_PATH=/path/to/pclink-extensions/extensions

# Run PCLink server
pclink-server
```

### Debugging

```python
# In your extension.py
self.logger.debug("Debug message")
self.logger.info("Info message")
self.logger.warning("Warning message")
self.logger.error("Error message")
```

View logs:
```bash
tail -f ~/.pclink/pclink.log
```

## 📚 Resources

- **PCLink Wiki**: Official Extension Development Guide & API Reference
- [Example Extensions](../extensions/)

## ❓ Questions?

- Open an issue
- Join our [Discord](https://discord.gg/pclink)
- Check [existing discussions](https://github.com/BYTEDz/pclink-extensions/discussions)

## 📄 License

By contributing, you agree that your contributions will be licensed under the AGPL-3.0 License.
