from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from .account_state import AccountState


class CacheManager:
    SEED_DIR = "seeds"

    def __init__(self, cache_dir: str):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def save_state(self, account_id: str, date: str, state) -> str:
        account_dir = self.cache_dir / str(account_id)
        account_dir.mkdir(parents=True, exist_ok=True)
        target = account_dir / f"{date}.json"
        payload = state.to_dict() if hasattr(state, "to_dict") else state
        with target.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        return str(target)

    def load_state(self, account_id: str, date: str) -> Optional[AccountState]:
        target = self.cache_dir / str(account_id) / f"{date}.json"
        if not target.exists():
            return None
        with target.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        return AccountState.from_dict(payload)

    def load_or_seed(self, account_id: str, target_date: str):
        cached = self.load_state(account_id, target_date)
        if cached is not None:
            return cached

        prev_date = self.get_previous_date(account_id, target_date)
        if prev_date:
            prev_state = self.load_state(account_id, prev_date)
            if prev_state is not None:
                return prev_state

        seed_path = Path(self.cache_dir).parent / self.SEED_DIR / str(account_id) / "seed.json"
        if seed_path.exists():
            with seed_path.open("r", encoding="utf-8") as fh:
                seed_data = json.load(fh)
            seed_date = str(seed_data.get("date", target_date))
            self.save_state(account_id, seed_date, seed_data)
            return AccountState.from_seed(account_id, seed_data, seed_data.get("initial_capital", 0.0))

        return None

    def create_seed_template(self, account_id: str, date: str, initial_capital: float = 0.0) -> dict:
        return {
            "account_id": account_id,
            "date": date,
            "total_asset": 0.0,
            "profit": 0.0,
            "stock_mv": 0.0,
            "nav": 1.0,
            "peak_nav": 1.0,
            "peak_date": date,
            "initial_capital": float(initial_capital),
            "positions": [],
            "nav_history": {date: 1.0},
        }

    def list_dates(self, account_id: str) -> List[str]:
        account_dir = self.cache_dir / str(account_id)
        if not account_dir.exists():
            return []
        dates = []
        for file_path in account_dir.glob("*.json"):
            if file_path.stem:
                dates.append(file_path.stem)
        return sorted(dates)

    def get_previous_date(self, account_id: str, current_date: str) -> Optional[str]:
        dates = self.list_dates(account_id)
        if not dates:
            return None
        normalized = [d for d in dates if d < current_date]
        if not normalized:
            return None
        return max(normalized)
