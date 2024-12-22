from pydantic import BaseModel, HttpUrl
from typing import Optional, Literal, Union, Any
from enum import Enum
from datetime import datetime
from magenta.core.models import ChatMessage # role, content, message_id, timestamp


class CodeSnippet(BaseModel):
  type: Literal["execution", "suggestion"]
  language: Literal["R", "py"]
  code_snippet: str


class CodeResponse(BaseModel):
  message_id: str
  role: Literal["user", "assistant"]
  response: str


class CodePair(BaseModel):
    input: CodeSnippet
    output: Optional[CodeResponse] = None


class CodePairMessage(ChatMessage):
  type: Literal["code_pair"]
  code_pair: CodePair


class AnalysisSession(BaseModel):
  session_id: str
  context_id: str
  messages: list[ChatMessage] | None = None
  code_snippets: list[CodePairMessage] | None = None
  sysprompt_id: str = "radiant0"
  chat_id: str | None = None
  tenant_id: str = "default"


class AnalysisResponse(BaseModel):
  session_id: str
  response_inner: ChatMessage # the inner dialogue of the assistant
  response_message: ChatMessage | None = None # message from the assistant to the user
  code_snippet: CodeSnippet | None = None
  code_suggestion: CodeSnippet | None = None


