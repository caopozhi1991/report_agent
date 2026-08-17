from __future__ import annotations


class ModuleRegistry:
    def __init__(self):
        self._modules = {}
        self._asset_type_map = {}

    def register(self, module, asset_types: list):
        if not hasattr(module, "name") or not module.name:
            raise ValueError("Module must have a non-empty name")
        self._modules[module.name] = module
        for asset_type in asset_types:
            self._asset_type_map.setdefault(asset_type, [])
            if module.name not in self._asset_type_map[asset_type]:
                self._asset_type_map[asset_type].append(module.name)

    def get_enabled_modules(self, asset_type: str, enabled_names: list) -> list:
        available = self._asset_type_map.get(asset_type, [])
        order = []
        for name in available:
            if name in enabled_names:
                order.append(self._modules[name])
        return order
