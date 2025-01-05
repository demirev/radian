from pydantic import BaseModel, HttpUrl
from typing import Optional, Literal, Union, Any
from enum import Enum
from datetime import datetime

class TaskStatus(str, Enum):
  created = "created"
  pending = "pending"
  submitted = "submitted"
  in_progress = "in_progress"
  completed = "completed"
  failed = "failed"
  updated = "updated"
  scheduled = "scheduled"
  cancelled = "cancelled" # TODO these can be cleaned up and consolidated


class Tenant(BaseModel):
  tenant_id: str
  name: Optional[str] = ""
  description: Optional[str] = ""


class Task(BaseModel):
  task_id: str
  status: TaskStatus
  type: Optional[str] = None
  result: Optional[dict] = None


class RagDocument(BaseModel):
  document_id: str
  table_name: str


class RagSpec(BaseModel):
  rag_documents: list[RagDocument]
  context_documents: list[RagDocument]
  rag_connecting_prompt: Optional[str] = None
  context_connecting_prompt: Optional[str] = None


class Prompt(BaseModel):
  prompt_id: str
  name: str
  type: Literal["system", "agent"]
  description: Optional[str] = None
  prompt: str
  toolset: Optional[list[str]] = None # this is defined in terms of function.name, not tool_id
  documents: Optional[RagSpec] = None


class Document(BaseModel):
  document_id: str
  name: str
  type: str
  description: Optional[str] = None
  full_text: Optional[str] = None
  metadata: Optional[dict] = None
  chunks: Optional[int] = None
  chunks_text: Optional[list[str]] = None
  status: TaskStatus


class ChatInternalMessage(BaseModel):
  role: str
  content: str


class ChatMessage(ChatInternalMessage):
  message_id: str
  timestamp: datetime


class AgentType(Enum):
  test_agent = "test_agent"
  test_rag_agent = "test_rag_agent"


class HttpMethod(str, Enum):
  GET = "GET"
  POST = "POST"
  PUT = "PUT"
  DELETE = "DELETE"


class Chat(BaseModel):
  chat_id: str
  agent: Optional[str] = None #even though the input is AgentType, we convert it to str so it can be stored in MongoDB
  context_id: str
  sysprompt_id: str
  description: Optional[str] = None
  messages: list[ChatMessage]
  statuses: list[dict]


class ToolParameter(BaseModel):
	type: Literal["string", "integer", "array"]
	description: str
	enum: Optional[list[str]] = None
	items: Optional[dict] = None
	min_items: Optional[int] = None
	max_items: Optional[int] = None


class ToolParameters(BaseModel):
	type: Literal["object"]
	properties: dict[str, ToolParameter]
	required: list[str]


class ToolBody(BaseModel):
	name: str
	description: str
	parameters: ToolParameters


class ExternalToolBody(ToolBody):
  url: HttpUrl
  method: HttpMethod


class Tool(BaseModel):
	tool_id: str
	type: Literal["function", "external"]
	function: ToolBody


class ExternalTool(Tool):
	function: ExternalToolBody


class ContextParameter(BaseModel):
	name: str
	type: Literal["string", "integer", "array"]
	description: str
	items: Optional[dict] = None
	min_items: Optional[int] = None
	max_items: Optional[int] = None


class ToolWithContext(Tool):
	function: Union[ToolBody, ExternalToolBody]
	context_parameters: Optional[list[ContextParameter]] = None
