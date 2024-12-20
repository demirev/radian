from typing import List, Optional, Literal, Union, Dict
from fastapi import APIRouter, Query, HTTPException, BackgroundTasks
from app.core.models import AnalysisSession, CodeSnippet, CodeResponse, CodePair, CodePairMessage
from magenta.routes.chats import create_chat, delete_chat, send_chat
from magenta.core.config import tenant_collections
from magenta.core.models import ChatMessage, TaskStatus
from magenta.services.chat_service import process_chat
from datetime import datetime
import uuid

analysis_router = APIRouter(prefix="/analysis", tags=["analysis"])


@analysis_router.get("/", response_model=List[AnalysisSession])
async def list_analysis_sessions(
  session_id: Optional[str] = Query(None, title="Session ID", description="Filter by session ID"),
  context_id: Optional[str] = Query(None, title="Context ID", description="Filter by context ID"),
  tenant_id: str = "default",
):
  analysis_collection = tenant_collections.get_collection(tenant_id, "analysis")

  query = {}
  if session_id:
    query["session_id"] = session_id
  if context_id:
    query["context_id"] = context_id

  analysis_sessions = analysis_collection.find(query, {"_id": 0})

  analysis_objects = [AnalysisSession(**analysis_session) for analysis_session in analysis_sessions]
  
  return list(analysis_objects)


@analysis_router.post("/", response_model=AnalysisSession)
async def create_analysis_session(
  context_id: str, 
  tenant_id: str = "default",
  sysprompt_id: str = "radiant0"
):
  analysis_collection = tenant_collections.get_collection(tenant_id, "analysis")

  session_id = str(uuid.uuid4())

  # create a chat
  chat = await create_chat(
    chat_id=session_id, # match the session id of the analysis session object
    context_id=context_id,
    tenant_id=tenant_id,
    sysprompt_id=sysprompt_id
  )

  analysis_session = AnalysisSession(
    context_id=context_id,
    session_id=session_id,
    tenant_id=tenant_id,
    sysprompt_id=sysprompt_id,
    chat_id=chat.chat_id,
  )
  
  analysis_collection.insert_one(analysis_session.model_dump(exclude_none=True))

  return analysis_session


@analysis_router.get("/{session_id}", response_model=AnalysisSession)
async def get_analysis_session(session_id: str, tenant_id: str = "default"):
  analysis_collection = tenant_collections.get_collection(tenant_id, "analysis")

  analysis_session = analysis_collection.find_one({"session_id": session_id}, {"_id": 0})
  if not analysis_session:
    raise HTTPException(status_code=404, detail="Analysis session not found")
  
  analysis_session = AnalysisSession(**analysis_session)
  return analysis_session


@analysis_router.delete("/{session_id}", response_model=Dict[str, str])
async def delete_analysis_session(session_id: str, tenant_id: str = "default"):
  analysis_collection = tenant_collections.get_collection(tenant_id, "analysis")

  analysis_collection.delete_one({"session_id": session_id})
  await delete_chat(session_id, tenant_id)

  return {"status": "success"}


@analysis_router.get("/{session_id}/messages", response_model=List[str])
async def get_messages_from_analysis_session(session_id: str, tenant_id: str = "default"):
  analysis_collection = tenant_collections.get_collection(tenant_id, "analysis")

  messages = analysis_collection.find_one({"session_id": session_id}, {"messages": 1, "_id": 0})
  if not messages:
    raise HTTPException(status_code=404, detail="No messages found")
  
  return messages["messages"]


@analysis_router.post("/{session_id}/messages", response_model=TaskStatus)
async def add_message_to_analysis_session(
  session_id: str,
  message: str,
  background_tasks: BackgroundTasks,
  tenant_id: str = "default",
  dry_run: bool = False
):
  analysis_collection = tenant_collections.get_collection(tenant_id, "analysis")

  message_to_process = "[USER MESSAGE]\n\n" + message # add a prefix to the message to indicate to the LLM that this is a user message

  message_id = str(uuid.uuid4())
  
  background_tasks.add_task(
    process_chat,
    chat_id=session_id,
    message_id=message_id,
    new_message=message_to_process,
    dry_run=dry_run,
    context_arguments={"session_id": session_id},
    json_mode=False,
    tool_choice="auto"
  )
  
  message_object = ChatMessage(
    message_id=message_id,
    content=message,
    role="user",
    timestamp=datetime.now()
  )

  analysis_collection.update_one(
    {"session_id": session_id},
    {"$push": {"messages": message_object.model_dump(exclude_none=True)}}
  )

  return TaskStatus(task_id=message_id, status="success")


@analysis_router.get("/{session_id}/code", response_model=List[CodePair])
async def get_code_from_analysis_session(session_id: str, tenant_id: str = "default"):
  analysis_collection = tenant_collections.get_collection(tenant_id, "analysis")

  code_snippets = analysis_collection.find_one({"session_id": session_id}, {"code_snippets": 1, "_id": 0})
  return code_snippets["code_snippets"]


@analysis_router.post("/{session_id}/code", response_model=TaskStatus)
async def add_code_to_analysis_session(
  session_id: str,
  code: CodePair,
  background_tasks: BackgroundTasks,
  tenant_id: str = "default",
  dry_run: bool = False
):
  analysis_collection = tenant_collections.get_collection(tenant_id, "analysis")

  message_to_process = "[CODE]\n\n[INPUT]\n\n```" + code["input"]["code_snippet"] + "```\n\n"

  if code["output"]:
    message_to_process += "[OUTPUT]\n\n```" + code["output"]["response"] + "```\n\n"

  code_message_id = str(uuid.uuid4())

  background_tasks.add_task(
    process_chat,
    chat_id=session_id,
    message_id=code_message_id,
    new_message=message_to_process,
    dry_run=dry_run,
    context_arguments={"session_id": session_id},
    json_mode=False,
    tool_choice="auto"
  )

  code_message_object = CodePairMessage(
    message_id=code_message_id,
    content=message_to_process,
    role="user",
    timestamp=datetime.now(),
    type="code_pair",
    code_pair=code
  )

  analysis_collection.update_one(
    {"session_id": session_id}, 
    {"$push": {"code_snippets": code_message_object.model_dump(exclude_none=True)}}
  )

  return TaskStatus(task_id=code_message_id, status="success")

