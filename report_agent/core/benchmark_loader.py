from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_BENCHMARKS = {
    "沪深300": "000300.SH",
    "上证指数": "000001.SH",
}


def to_yyyymmdd(value: object) -> str:
    """统一日期为 YYYYMMDD，兼容 2026-07-20 / 20260720。"""
    text = str(value).strip().replace("-", "").replace("/", "").replace(".", "")
    if len(text) >= 8 and text[:8].isdigit():
        return text[:8]
    return str(value)


class BenchmarkLoader:
    """通过 TickFlow 拉取指数日 K，并归一化到与策略净值可比的单位净值。"""

    def __init__(
        self,
        cache_dir: str | Path = "./cache",
        symbols: dict[str, str] | None = None,
        api_key: str = "",
        enabled: bool = True,
    ):
        self.enabled = enabled
        self.api_key = (api_key or "").strip()
        self.symbols = symbols or dict(DEFAULT_BENCHMARKS)
        self.cache_dir = Path(cache_dir) / "benchmarks"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = None

    def get_normalized_series(self, nav_series: pd.Series) -> dict[str, pd.Series]:
        if not self.enabled or nav_series is None or nav_series.empty:
            return {}

        # 保留原始 index 供绘图对齐，同时用统一日期做行情匹配
        original_index = nav_series.index
        nav_dates = [to_yyyymmdd(d) for d in original_index]
        start_date = min(nav_dates)
        end_date = max(nav_dates)
        result: dict[str, pd.Series] = {}

        for name, symbol in self.symbols.items():
            try:
                closes = self._load_closes(symbol, start_date, end_date)
                closes = self._ensure_end_prices(closes, symbol, nav_dates)
                normalized = self._normalize_to_nav(closes, nav_dates, original_index)
                if not normalized.dropna().empty:
                    result[name] = normalized
            except Exception as exc:
                print(f"⚠️ 基准指数 {name}({symbol}) 拉取失败，已跳过: {exc}")
        return result

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from tickflow import TickFlow
        except ImportError as exc:
            raise ImportError("未安装 tickflow，请执行: pip install \"tickflow[all]\"") from exc

        if self.api_key:
            self._client = TickFlow(api_key=self.api_key)
        else:
            self._client = TickFlow.free()
        return self._client

    def _load_closes(self, symbol: str, start_date: str, end_date: str) -> pd.Series:
        cached = self._read_cache(symbol)
        if cached is not None and self._covers_range(cached, start_date, end_date):
            return cached

        closes = self._fetch_closes(symbol, start_date, end_date)
        if cached is not None and not cached.empty:
            closes = pd.concat([cached, closes]).groupby(level=0).last().sort_index()
        self._write_cache(symbol, closes)
        return closes

    def _fetch_closes(self, symbol: str, start_date: str, end_date: str) -> pd.Series:
        start_dt = self._parse_yyyymmdd(start_date) - timedelta(days=10)
        end_dt = self._parse_yyyymmdd(end_date) + timedelta(days=2)
        start_ms = int(start_dt.timestamp() * 1000)
        end_ms = int(end_dt.timestamp() * 1000)

        tf = self._get_client()
        df = tf.klines.get(
            symbol,
            period="1d",
            start_time=start_ms,
            end_time=end_ms,
            count=10000,
            adjust="none",
            as_dataframe=True,
        )
        if df is None or len(df) == 0:
            return pd.Series(dtype=float)

        trade_dates = pd.to_datetime(df["trade_date"]).dt.strftime("%Y%m%d")
        closes = pd.Series(pd.to_numeric(df["close"], errors="coerce").values, index=trade_dates, dtype=float)
        closes.index = [to_yyyymmdd(d) for d in closes.index]
        closes = closes[~closes.index.duplicated(keep="last")].sort_index().dropna()
        return closes

    def _ensure_end_prices(self, closes: pd.Series, symbol: str, nav_dates: list[str]) -> pd.Series:
        """补齐策略期末仍缺的指数点：优先实时价，否则沿用最近收盘价。

        免费日 K 收盘后常滞后约 1 日，会导致指数比策略少一天；该补齐不写入磁盘缓存。
        """
        if closes is None or closes.empty:
            return closes

        last_date = to_yyyymmdd(closes.index.max())
        missing = [d for d in nav_dates if d > last_date]
        if not missing:
            return closes

        updated = closes.copy()
        quote_price = self._fetch_last_price(symbol)
        if quote_price is not None:
            for day in missing:
                updated.loc[day] = quote_price
            print(f"ℹ️ {symbol} 日K未含 {missing[-1]}，已用实时行情补齐")
            return updated.sort_index()

        last_price = float(closes.iloc[-1])
        for day in missing:
            updated.loc[day] = last_price
        print(
            f"ℹ️ {symbol} 日K仅到 {last_date}，已用该日收盘价对齐策略期末 {missing[-1]}；"
            f"配置 TICKFLOW_API_KEY 可改为拉取当日实时点位"
        )
        return updated.sort_index()

    def _fetch_last_price(self, symbol: str) -> float | None:
        if not self.api_key:
            return None
        try:
            from tickflow import TickFlow

            tf = TickFlow(api_key=self.api_key)
            quotes = tf.quotes.get(symbols=[symbol])
            if not quotes:
                return None
            item = quotes[0] if isinstance(quotes, list) else quotes
            if isinstance(item, dict):
                price = item.get("last_price", item.get("close"))
            else:
                price = getattr(item, "last_price", None) or getattr(item, "close", None)
            if price is None:
                return None
            return float(price)
        except Exception as exc:
            print(f"⚠️ {symbol} 实时行情补齐失败: {exc}")
            return None

    def _normalize_to_nav(
        self,
        closes: pd.Series,
        nav_dates: list[str],
        original_index: pd.Index,
    ) -> pd.Series:
        if closes.empty:
            return pd.Series(dtype=float, index=original_index)

        closes = closes.copy()
        closes.index = [to_yyyymmdd(d) for d in closes.index]
        closes = closes[~closes.index.duplicated(keep="last")].sort_index()

        calendar = sorted(set(closes.index.tolist() + nav_dates))
        on_calendar = closes.reindex(calendar).ffill()
        aligned = on_calendar.reindex(nav_dates)

        valid = aligned.dropna()
        if valid.empty or float(valid.iloc[0]) == 0:
            return pd.Series(dtype=float, index=original_index)

        base = float(valid.iloc[0])
        normalized = aligned / base
        return pd.Series(normalized.values, index=original_index, dtype=float)

    @staticmethod
    def _covers_range(closes: pd.Series, start_date: str, end_date: str) -> bool:
        if closes is None or closes.empty:
            return False
        start = to_yyyymmdd(start_date)
        end = to_yyyymmdd(end_date)
        return to_yyyymmdd(closes.index.min()) <= start and to_yyyymmdd(closes.index.max()) >= end

    def _cache_path(self, symbol: str) -> Path:
        safe = symbol.replace(".", "_")
        return self.cache_dir / f"{safe}.json"

    def _read_cache(self, symbol: str) -> pd.Series | None:
        path = self._cache_path(symbol)
        if not path.exists():
            return None
        try:
            payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            closes = payload.get("closes", {})
            if not closes:
                return None
            series = pd.Series({to_yyyymmdd(k): float(v) for k, v in closes.items()}, dtype=float)
            return series.sort_index()
        except Exception:
            return None

    def _write_cache(self, symbol: str, closes: pd.Series) -> None:
        if closes is None or closes.empty:
            return
        path = self._cache_path(symbol)
        payload = {
            "symbol": symbol,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "closes": {to_yyyymmdd(k): float(v) for k, v in closes.items()},
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _parse_yyyymmdd(value: str) -> datetime:
        return datetime.strptime(to_yyyymmdd(value), "%Y%m%d")
