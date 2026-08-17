from __future__ import annotations

from abc import ABC, abstractmethod

import matplotlib.pyplot as plt


class AnalysisModule(ABC):
    name: str = ""
    display_name: str = ""

    @abstractmethod
    def analyze(self, account_state, config) -> dict:
        pass

    @abstractmethod
    def render(self, analysis_result):
        pass

    def should_run(self, account_state) -> bool:
        return True
