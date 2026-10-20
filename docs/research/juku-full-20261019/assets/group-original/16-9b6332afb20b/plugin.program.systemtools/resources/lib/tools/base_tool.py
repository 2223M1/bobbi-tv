# -*- coding: utf-8 -*-
"""Base tool abstraction and registry for Kodi System Tools."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Type


class BaseTool(ABC):
    """Abstract base class for all toolbox tools."""

    id: str = ""
    title_id: int = 30000
    description_id: int = 30000
    icon: str = "DefaultProgram.png"
    order: int = 100

    @classmethod
    def get_id(cls) -> str:
        return cls.id

    @classmethod
    def get_title_id(cls) -> int:
        return cls.title_id

    @classmethod
    def get_description_id(cls) -> int:
        return cls.description_id

    @classmethod
    def get_icon(cls) -> str:
        return cls.icon

    @abstractmethod
    def run(self, params: Dict[str, str]) -> None:
        """Execute the tool action."""
        raise NotImplementedError


class ToolRegistry:
    """Registry pattern to dynamically discover and register toolbox modules."""

    _tools: Dict[str, Type[BaseTool]] = {}
    _order: List[str] = []

    @classmethod
    def register(cls, tool_cls: Type[BaseTool]) -> Type[BaseTool]:
        """Decorator or method to register a tool class."""
        tool_id = tool_cls.id
        if not tool_id:
            raise ValueError(f"Tool class {tool_cls.__name__} must define a non-empty 'id'")
        cls._tools[tool_id] = tool_cls
        if tool_id not in cls._order:
            cls._order.append(tool_id)
        # Sort registered tools by tool_cls.order
        cls._order.sort(key=lambda tid: cls._tools[tid].order)
        return tool_cls

    @classmethod
    def get(cls, tool_id: str) -> Optional[BaseTool]:
        """Instantiate and return tool by ID."""
        tool_cls = cls._tools.get(tool_id)
        if tool_cls:
            return tool_cls()
        return None

    @classmethod
    def get_all(cls) -> List[Type[BaseTool]]:
        """Return list of all registered tool classes sorted by order."""
        return [cls._tools[tid] for tid in cls._order if tid in cls._tools]

    @classmethod
    def dispatch(cls, tool_id: str, params: Dict[str, str]) -> bool:
        """Dispatch action to the registered tool."""
        tool = cls.get(tool_id)
        if tool:
            tool.run(params)
            return True
        return False
