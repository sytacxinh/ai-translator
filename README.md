# AI Translator

![Version](https://img.shields.io/badge/version-1.7.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-yellow.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Platform](https://img.shields.io/badge/platform-Windows-informational.svg)

A powerful Windows desktop application for instant text translation using AI. Select any text, press a hotkey, and get translations instantly - no window switching needed!

## Highlights

- **Instant Translation** - Select text, press hotkey, get translation in tooltip
- **14 AI Providers** - Google Gemini (free!), OpenAI, Claude, DeepSeek, Groq, and more
- **Vision & OCR** - Screenshot any region and translate text from images
- **File Processing** - Translate documents (.docx, .txt, .srt, .pdf)
- **120+ Languages** - Comprehensive language support
- **Custom Hotkeys** - Configure any key combination for any language

---

## Features

### Quick Translation Hotkeys
| Hotkey | Language |
|--------|----------|
| `Win+Alt+V` | Vietnamese |
| `Win+Alt+E` | English |
| `Win+Alt+J` | Japanese |
| `Win+Alt+C` | Chinese Simplified |
| `Win+Alt+S` | Screenshot OCR (if vision enabled) |

**+ 4 customizable hotkeys** for any language of your choice.

### Vision & File Processing
- **Screenshot OCR** - Capture any screen region and extract/translate text
- **Image Translation** - Drag & drop images for OCR and translation
- **Document Support** - Process `.docx`, `.txt`, `.srt`, `.pdf` files
- **Multi-file Batch** - Translate multiple files in a single API request
- **Drag & Drop** - Simply drop files onto the translator window

### Multi-Provider Support

| Provider | Models | Free Tier |
|----------|--------|-----------|
| **Google Gemini** | gemini-2.0-flash, gemini-pro | 1,500 req/day |
| **OpenAI** | gpt-4o, gpt-4-turbo, gpt-3.5 | No |
| **Anthropic** | claude-3.5-sonnet, claude-3-haiku | No |
| **DeepSeek** | deepseek-chat, deepseek-coder | Yes |
| **Groq** | llama-3.3-70b, mixtral-8x7b | Yes |
| **xAI** | grok-2, grok-vision | No |
| **Mistral** | mistral-large, pixtral | No |
| **Perplexity** | sonar-pro, sonar | No |
| **Cerebras** | llama-3.3-70b | Yes |
| **SambaNova** | Meta-Llama-3.1-405B | Yes |
| **Together** | Llama-3.2-Vision | No |
| **SiliconFlow** | Qwen2.5, DeepSeek | Yes |
| **OpenRouter** | 100+ models | Varies |

**Smart Routing** - Automatically detects provider from API key or model name.

### User Interface
- **Compact Tooltip** - Translation appears near cursor, auto-sizes to content
- **Full Translator** - Rich window with language selector, custom prompts, attachments
- **Dark Theme** - Modern UI with ttkbootstrap
- **System Tray** - Runs quietly in background
- **Translation History** - Review and reuse past translations (up to 100 entries)

### Smart Features
- **Dictionary Mode** - Single words get definitions, pronunciation, examples
- **Custom Prompts** - Add instructions like "Make it formal" or "Technical terms only"
- **Clipboard Preservation** - Your files/images in clipboard are preserved
- **Auto-start** - Optionally start with Windows
- **Auto-update** - Get notified of new versions

---

## Installation

### Prerequisites
- Windows 10/11
- Python 3.10+ (if running from source)
- An API key (Google Gemini is free!)

### Option 1: Download EXE (Recommended)
1. Go to [Releases](https://github.com/sytacxinh/ai-translator/releases)
2. Download `AITranslator_v1.7.0.exe`
3. Run the application
4. Enter your API key in Settings

### Option 2: Run from Source

```bash
# Clone repository
git clone https://github.com/sytacxinh/ai-translator.git
cd ai-translator

# Install dependencies
pip install -r requirements.txt

# Run
python main.py

# Or run without console window
# Double-click run_silent.vbs
```

### Get Your Free API Key

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Click "Create API Key"
3. Copy the key and paste in Settings

---

## Usage

### Basic Translation
1. **Start the app** - Look for "AI" icon in system tray
2. **Select any text** in any application
3. **Press hotkey** (e.g., `Win+Alt+V` for Vietnamese)
4. **Translation appears** in a tooltip near your cursor

### Tooltip Actions
- **Copy** - Copy translation to clipboard
- **Open Translator** - Open full window with more options
- **Settings** - Quick access to configuration
- **X** or `Escape` - Close tooltip

### Full Translator Window
Right-click tray icon → "Open Translator" or click from tooltip

Features:
- Edit original text
- Choose from 120+ languages
- Add custom prompt for translation style
- Attach images or files
- View translation history

### Screenshot OCR
1. Enable vision in Settings (requires vision-capable model)
2. Press `Win+Alt+S`
3. Draw rectangle around text to translate
4. Translation appears in tooltip

### File Translation
1. Open Full Translator
2. Click **+** button or drag & drop files
3. Supported: Images (PNG, JPG, GIF, WebP), Documents (DOCX, TXT, SRT, PDF)
4. Click Translate - all files processed in single API call

---

## Configuration

### Settings Tabs

**General**
- Auto-start with Windows
- Check for updates
- Enable/disable history
- Theme selection

**Hotkeys**
- View default hotkeys
- Record custom hotkeys (click "Record" then press keys)
- Assign any language to any hotkey

**API Key**
- Add multiple API keys
- Auto-detect provider or select manually
- Test connection
- View vision/file capabilities

### Custom Prompts
In translator window, use "Custom prompt" field:
- "Make it formal" - Business communication
- "Use casual tone" - Friendly messages
- "Technical translation" - Documentation
- "Explain like I'm 5" - Simple explanations
- "Preserve formatting" - Keep structure

---

## Project Structure

```
ai-translator/
├── main.py                 # Entry point
├── config.py               # Configuration management
├── requirements.txt        # Dependencies
├── src/
│   ├── app.py              # Main application (1,684 lines)
│   ├── constants.py        # Languages, providers, models
│   ├── core/
│   │   ├── api_manager.py  # AI provider management
│   │   ├── translation.py  # Translation service
│   │   ├── hotkey.py       # Global hotkey system
│   │   ├── clipboard.py    # Clipboard operations
│   │   ├── screenshot.py   # Screen capture for OCR
│   │   ├── multimodal.py   # Vision processing
│   │   ├── file_processor.py # Document text extraction
│   │   ├── pdf_ocr.py      # Scanned PDF OCR (NEW)
│   │   ├── history.py      # Translation history
│   │   ├── crypto.py       # Secure API key storage (DPAPI)
│   │   ├── ssl_pinning.py  # SSL certificate pinning
│   │   ├── auth.py         # Windows Hello authentication (NEW)
│   │   └── provider_health.py # Smart provider fallback (NEW)
│   ├── ui/
│   │   ├── settings.py     # Settings window
│   │   ├── attachments.py  # File attachment widget
│   │   ├── history_dialog.py # History viewer with search
│   │   ├── progress_dialog.py # Progress indicator
│   │   ├── toast.py        # Toast notifications (NEW)
│   │   └── dialogs.py      # Error dialogs
│   └── utils/
│       ├── logging_setup.py    # Logging
│       ├── single_instance.py  # Prevent duplicates
│       └── updates.py          # Auto-update
├── tests/                  # Unit tests
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_api_manager.py
│   └── test_file_processor.py
└── logs/                   # Application logs
```

---

## Troubleshooting

### API Error / Connection Failed
1. Open Settings → API Key tab
2. Verify your API key is correct
3. Select correct Provider (or use "Auto")
4. Click "Test" to verify connection

### Translation Not Working
- Ensure text is selected (try Ctrl+C manually first)
- Wait for cooldown (2 seconds between translations)
- Some apps may block clipboard access
- Check logs folder for error details

### Hotkeys Not Working
- Check Settings → Hotkeys for configured shortcuts
- Try running as administrator
- Some apps capture certain key combinations
- Ensure no hotkey conflicts with other software

### Vision/File Features Disabled
- You need a vision-capable model (e.g., Gemini 2.0 Flash, GPT-4o)
- Go to Settings → API Key → Click "Test"
- If test shows "Image OK", vision is enabled

---

## Technical Details

### Architecture
- **Threading Model**: Main thread (UI), Translation thread (async), Hotkey thread (Windows messages), Tray thread (pystray)
- **Queue System**: Thread-safe queue for translation results
- **Hotkey System**: Windows RegisterHotKey API (zero CPU when idle)
- **Provider Detection**: Model name → API key pattern → Heuristics → Default

### Dependencies
| Package | Purpose |
|---------|---------|
| google-generativeai | Google Gemini API |
| pyperclip | Clipboard access |
| pystray | System tray icon |
| Pillow | Image processing |
| ttkbootstrap | Modern UI |
| pywin32 | Windows clipboard/registry |
| python-docx | DOCX file reading |
| pysrt | Subtitle parsing |
| chardet | Encoding detection |
| windnd | Drag & drop support |
| PyPDF2 | PDF text extraction |
| PyMuPDF | Scanned PDF OCR |
| winsdk | Windows Hello authentication |

### Configuration Storage
- **Location**: `%APPDATA%/AITranslator/config.json`
- **Contents**: API keys, hotkeys, history, preferences
- **Auto-start**: Windows Registry entry

---

## What's New in v1.7.0

### Security Enhancements
- **Windows Hello Authentication** - Protect API keys with PIN, Fingerprint, or Face recognition
- **Show All API Keys** - One-click to reveal/hide all keys (with authentication)
- **Password Fallback** - Falls back to Windows password if Windows Hello unavailable
- **Soft Rate Limiting** - 5 attempts per authentication dialog

### New Features
- **Smart Provider Fallback** - Auto-switch to backup API when primary fails
- **Scanned PDF OCR** - Extract text from image-based PDFs using AI vision
- **Toast Notifications** - Non-intrusive notifications with auto-dismiss
- **Search History** - Filter translation history by keyword

### UI Improvements
- **Synced Show/Hide Buttons** - Individual and "Show All" buttons stay in sync
- **Better Settings UI** - Improved API key management experience

### Previous in v1.6.0
- Encrypted API Keys (Windows DPAPI)
- SSL Certificate Pinning (TLS 1.2+)
- PDF Support
- Progress Indicator
- Type hints & Unit tests

### Previous in v1.5.0
- Modular architecture refactoring
- 14 AI providers with auto-detection
- Vision & OCR, file processing
- Drag & drop, translation history

---

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### Development Setup
```bash
git clone https://github.com/sytacxinh/ai-translator.git
cd ai-translator
pip install -r requirements.txt
python main.py
```

### Building EXE
```bash
pip install pyinstaller
pyinstaller AITranslator.spec
# Output: dist/AITranslator_v1.7.0.exe
```

### Running Tests
```bash
pip install pytest pytest-cov pytest-mock
pytest tests/ --cov=src --cov-report=html
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- Powered by Google Gemini AI, OpenAI, Anthropic, and other AI providers
- Built with Python, Tkinter, and ttkbootstrap
- Icons and UI inspired by modern design principles

---

**Made with care for translators, developers, and anyone who works across languages.**
