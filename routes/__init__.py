from .prompts import prompts_router
from .documents import documents_router
from .chats import chats_router
from .tools import tools_router
from .tenants import tenants_router

__all__ = ['prompts_router', 'documents_router', 'chats_router', 'tools_router', 'tenants_router']
