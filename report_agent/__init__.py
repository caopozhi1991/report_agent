import matplotlib
from matplotlib import font_manager

candidates = [
    "Microsoft YaHei",
    "SimHei",
    "Microsoft JhengHei",
    "Noto Sans CJK SC",
    "WenQuanYi Micro Hei",
    "Arial Unicode MS",
    "sans-serif",
]

available = [font for font in candidates if any(f.name == font for f in font_manager.fontManager.ttflist)]
if not available:
    available = ["sans-serif"]

matplotlib.rcParams["font.sans-serif"] = available
matplotlib.rcParams["axes.unicode_minus"] = False

from .agent import MultiAccountReportAgent

__all__ = ["MultiAccountReportAgent"]
