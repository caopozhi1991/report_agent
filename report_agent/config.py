import os

CONFIG = {
    "data_dir": "./data",
    "output_dir": "./reports",
    "cache_dir": "./cache",
    "default_asset_type": "stock",
    "account_types": {
        "1219020189": "stock",
        "1206016764": "stock",
    },
    "initial_capital": {
        "1219020189": 600000,
        "1206016764": 100000,
    },
    "enabled_modules": {
        "1219020189": ["summary", "equity", "trade", "llm_analysis"],
        "1206016764": ["summary", "equity"],
    },
    "llm": {
        "enabled": False,
        "api_key": os.getenv("OPENAI_API_KEY", ""),
        "model": "gpt-4o-mini",
        "temperature": 0.7,
    },
}
