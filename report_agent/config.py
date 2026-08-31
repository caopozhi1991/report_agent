import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parent.parent / ".env")

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
        "1219020189": 1000000,
        "1206016764": 100000,
    },
    "account_names": {
        "1219020189": "chenwei",
        "1206016764": "xiaofeng",
    },
    "enabled_modules": {
        "1219020189": ["summary", "equity", "trade", "llm_analysis"],
        "1206016764": ["summary", "equity"],
    },
    "benchmarks": {
        "enabled": os.getenv("REPORT_BENCHMARK_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"},
        "api_key": os.getenv("TICKFLOW_API_KEY", ""),
        "symbols": {
            "沪深300": "000300.SH",
            "上证指数": "000001.SH",
        },
    },
    "llm": {
        "enabled": os.getenv("REPORT_LLM_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"},
        "api_key": os.getenv("OPENAI_API_KEY", ""),
        "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "temperature": float(os.getenv("OPENAI_TEMPERATURE", "0.7")),
    },
}
