# routers/__init__.py

# Импортируем роутер для удобного доступа извне
from .quest_router import quest_router

# Опционально: список экспортируемых объектов
__all__ = ['quest_router']