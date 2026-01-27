"""
Constants and configuration values for AI Translator.
"""

# ============== VERSION ==============
VERSION = "1.7.0"
APP_NAME = "AI Translator"
GITHUB_REPO = "sytacxinh/ai-translator"

# ============== NETWORK ==============
LOCK_PORT = 47823  # Port for single instance lock

# ============== TIMING ==============
COOLDOWN = 2.0  # Translation cooldown in seconds

# ============== AVAILABLE LANGUAGES ==============
# Format: (English name, ISO code, Native name)
LANGUAGES = [
    ("Vietnamese", "vi", "Tiếng Việt"),
    ("English", "en", "English"),
    ("Japanese", "ja", "日本語"),
    ("Chinese Simplified", "zh-CN", "中文简体"),
    ("Chinese Traditional", "zh-TW", "中文繁體"),
    ("Korean", "ko", "한국어"),
    ("French", "fr", "Français"),
    ("German", "de", "Deutsch"),
    ("Spanish", "es", "Español"),
    ("Italian", "it", "Italiano"),
    ("Portuguese", "pt", "Português"),
    ("Russian", "ru", "Русский"),
    ("Thai", "th", "ไทย"),
    ("Indonesian", "id", "Bahasa Indonesia"),
    ("Malay", "ms", "Bahasa Melayu"),
    ("Hindi", "hi", "हिन्दी"),
    ("Arabic", "ar", "العربية"),
    ("Dutch", "nl", "Nederlands"),
    ("Polish", "pl", "Polski"),
    ("Turkish", "tr", "Türkçe"),
    ("Swedish", "sv", "Svenska"),
    ("Danish", "da", "Dansk"),
    ("Norwegian", "no", "Norsk"),
    ("Finnish", "fi", "Suomi"),
    ("Greek", "el", "Ελληνικά"),
    ("Czech", "cs", "Čeština"),
    ("Romanian", "ro", "Română"),
    ("Hungarian", "hu", "Magyar"),
    ("Ukrainian", "uk", "Українська"),
    ("Afrikaans", "af", "Afrikaans"),
    ("Albanian", "sq", "Shqip"),
    ("Amharic", "am", "አማርኛ"),
    ("Armenian", "hy", "Հdelays"),
    ("Azerbaijani", "az", "Azərbaycan"),
    ("Basque", "eu", "Euskara"),
    ("Belarusian", "be", "Беларуская"),
    ("Bengali", "bn", "বাংলা"),
    ("Bosnian", "bs", "Bosanski"),
    ("Bulgarian", "bg", "Български"),
    ("Catalan", "ca", "Català"),
    ("Cebuano", "ceb", "Cebuano"),
    ("Chichewa", "ny", "Chichewa"),
    ("Corsican", "co", "Corsu"),
    ("Croatian", "hr", "Hrvatski"),
    ("Esperanto", "eo", "Esperanto"),
    ("Estonian", "et", "Eesti"),
    ("Filipino", "tl", "Filipino"),
    ("Frisian", "fy", "Frysk"),
    ("Galician", "gl", "Galego"),
    ("Georgian", "ka", "ქართული"),
    ("Gujarati", "gu", "ગુજરાતી"),
    ("Haitian Creole", "ht", "Kreyòl Ayisyen"),
    ("Hausa", "ha", "Hausa"),
    ("Hawaiian", "haw", "Ōlelo Hawaiʻi"),
    ("Hebrew", "iw", "עברית"),
    ("Hmong", "hmn", "Hmoob"),
    ("Icelandic", "is", "Íslenska"),
    ("Igbo", "ig", "Igbo"),
    ("Irish", "ga", "Gaeilge"),
    ("Javanese", "jw", "Jawa"),
    ("Kannada", "kn", "ಕನ್ನಡ"),
    ("Kazakh", "kk", "Қазақ"),
    ("Khmer", "km", "ខ្មែរ"),
    ("Kurdish (Kurmanji)", "ku", "Kurdî"),
    ("Kyrgyz", "ky", "Кыргызча"),
    ("Lao", "lo", "ລາວ"),
    ("Latin", "la", "Latina"),
    ("Latvian", "lv", "Latviešu"),
    ("Lithuanian", "lt", "Lietuvių"),
    ("Luxembourgish", "lb", "Lëtzebuergesch"),
    ("Macedonian", "mk", "Македонски"),
    ("Malagasy", "mg", "Malagasy"),
    ("Malayalam", "ml", "മലയാളം"),
    ("Maltese", "mt", "Malti"),
    ("Maori", "mi", "Māori"),
    ("Marathi", "mr", "मराठी"),
    ("Mongolian", "mn", "Монгол"),
    ("Myanmar (Burmese)", "my", "မြန်မာ"),
    ("Nepali", "ne", "नेपाली"),
    ("Pashto", "ps", "پښتو"),
    ("Persian", "fa", "فارسی"),
    ("Punjabi", "pa", "ਪੰਜਾਬੀ"),
    ("Samoan", "sm", "Gagana faʻa Sāmoa"),
    ("Scots Gaelic", "gd", "Gàidhlig"),
    ("Serbian", "sr", "Српски"),
    ("Sesotho", "st", "Sesotho"),
    ("Shona", "sn", "chiShona"),
    ("Sindhi", "sd", "سنڌي"),
    ("Sinhala", "si", "සිංහල"),
    ("Slovak", "sk", "Slovenčina"),
    ("Slovenian", "sl", "Slovenščina"),
    ("Somali", "so", "Soomaali"),
    ("Sundanese", "su", "Basa Sunda"),
    ("Swahili", "sw", "Kiswahili"),
    ("Tajik", "tg", "Тоҷикӣ"),
    ("Tamil", "ta", "தமிழ்"),
    ("Telugu", "te", "తెలుగు"),
    ("Urdu", "ur", "اردو"),
    ("Uzbek", "uz", "Oʻzbek"),
    ("Welsh", "cy", "Cymraeg"),
    ("Xhosa", "xh", "isiXhosa"),
    ("Yiddish", "yi", "ייִדיש"),
    ("Yoruba", "yo", "Yorùbá"),
    ("Zulu", "zu", "isiZulu"),
]

# ============== AI PROVIDERS ==============
PROVIDERS_LIST = [
    "Auto", "Google", "OpenAI", "Anthropic", "DeepSeek",
    "Groq", "xAI", "Mistral", "Perplexity", "Cerebras",
    "SambaNova", "Together", "SiliconFlow", "OpenRouter"
]

# Maps specific model patterns to their native providers
MODEL_PROVIDER_MAP = {
    # === GROQ ===
    'groq': [
        'llama-3.1-70b-versatile', 'llama-3.1-8b-instant', 'llama-3.2-1b-preview',
        'llama-3.2-3b-preview', 'llama-3.2-11b-vision-preview', 'llama-3.2-90b-vision-preview',
        'llama-3.3-70b-versatile', 'llama-3.3-70b-specdec',
        'llama3-70b-8192', 'llama3-8b-8192', 'llama-guard-3-8b',
        'mixtral-8x7b-32768', 'gemma-7b-it', 'gemma2-9b-it',
        'whisper-large-v3', 'whisper-large-v3-turbo', 'distil-whisper-large-v3-en',
    ],
    # === MISTRAL AI ===
    'mistral': [
        'mistral-large-latest', 'mistral-large-2411', 'mistral-large-2407',
        'mistral-medium-latest', 'mistral-small-latest', 'mistral-small-2409',
        'ministral-8b-latest', 'ministral-3b-latest',
        'open-mistral-nemo', 'open-mistral-7b', 'open-mixtral-8x7b', 'open-mixtral-8x22b',
        'codestral-latest', 'codestral-mamba-latest',
        'pixtral-large-latest', 'pixtral-12b-latest',
    ],
    # === DEEPSEEK ===
    'deepseek': [
        'deepseek-chat', 'deepseek-coder', 'deepseek-reasoner',
    ],
    # === XAI (Grok) ===
    'xai': [
        'grok-beta', 'grok-vision-beta', 'grok-2', 'grok-2-vision', 'grok-2-1212',
    ],
    # === PERPLEXITY ===
    'perplexity': [
        'sonar', 'sonar-pro', 'sonar-reasoning', 'sonar-reasoning-pro',
        'llama-3.1-sonar-small-128k-online', 'llama-3.1-sonar-large-128k-online',
        'llama-3.1-sonar-huge-128k-online',
    ],
    # === CEREBRAS ===
    'cerebras': [
        'llama3.1-8b', 'llama3.1-70b', 'llama-3.3-70b',
    ],
    # === SAMBANOVA ===
    'sambanova': [
        'Meta-Llama-3.1-8B-Instruct', 'Meta-Llama-3.1-70B-Instruct',
        'Meta-Llama-3.1-405B-Instruct', 'Meta-Llama-3.2-1B-Instruct',
        'Meta-Llama-3.2-3B-Instruct', 'Meta-Llama-3.3-70B-Instruct',
    ],
    # === TOGETHER ===
    'together': [
        'meta-llama/Llama-3.2-3B-Instruct-Turbo', 'meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo',
        'meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo', 'meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo',
        'meta-llama/Llama-3.3-70B-Instruct-Turbo',
        'mistralai/Mixtral-8x7B-Instruct-v0.1', 'mistralai/Mistral-7B-Instruct-v0.3',
        'Qwen/Qwen2.5-7B-Instruct-Turbo', 'Qwen/Qwen2.5-72B-Instruct-Turbo',
        'google/gemma-2-9b-it', 'google/gemma-2-27b-it',
        'deepseek-ai/deepseek-llm-67b-chat',
    ],
    # === SILICONFLOW ===
    'siliconflow': [
        'Qwen/Qwen2.5-7B-Instruct', 'Qwen/Qwen2.5-14B-Instruct', 'Qwen/Qwen2.5-32B-Instruct',
        'Qwen/Qwen2.5-72B-Instruct', 'Qwen/Qwen2.5-Coder-7B-Instruct',
        'Qwen/QwQ-32B-Preview', 'Qwen/Qwen2-VL-72B-Instruct',
        'deepseek-ai/DeepSeek-V3', 'deepseek-ai/DeepSeek-V2.5', 'deepseek-ai/DeepSeek-Coder-V2-Instruct',
        'THUDM/glm-4-9b-chat', 'internlm/internlm2_5-7b-chat',
        '01-ai/Yi-1.5-9B-Chat', '01-ai/Yi-1.5-34B-Chat',
        'Pro/Qwen/Qwen2.5-7B-Instruct', 'Pro/deepseek-ai/DeepSeek-V3',
    ],
}

# API Key Patterns for provider detection
API_KEY_PATTERNS = {
    'gsk_': 'groq',           # Groq keys start with gsk_
    'sk-ant-': 'anthropic',   # Anthropic keys start with sk-ant-
    'xai-': 'xai',            # xAI keys start with xai-
    'sk-or-v1-': 'openrouter', # OpenRouter keys
    'pplx-': 'perplexity',    # Perplexity keys
    # Note: sk- is used by OpenAI, DeepSeek, Together, SiliconFlow - need model name
}

# ============== VISION MODELS ==============
# Models that support vision/image input. Supports wildcards (*).
# Note: Naming patterns like 'vision', 'VL', 'pixtral' are also detected in multimodal.py
VISION_MODELS = {
    'google': ['gemini-*'],  # All Gemini models support vision
    'openai': ['gpt-4-vision-*', 'gpt-4o', 'gpt-4o-*'],  # Note: o1 models do NOT support vision
    'anthropic': ['claude-3-*', 'claude-3.5-*', 'claude-3-5-*'],  # Wildcard support
    'groq': ['llama-3.2-*-vision-*', 'llava-*'],
    'xai': ['grok-*-vision*', 'grok-vision-*'],
    'mistral': ['pixtral-*'],
    'together': ['meta-llama/Llama-3.2-*-Vision-*', 'Qwen/Qwen2-VL-*', '*-vision-*'],
    'siliconflow': ['Qwen/Qwen2-VL-*', '*-VL-*'],
    'openrouter': ['*'],  # OpenRouter aggregates models - rely on naming heuristics
}
