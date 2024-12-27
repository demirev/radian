from typing import List, Optional, Literal, Union, Dict
from fastapi import APIRouter, Query, HTTPException, BackgroundTasks
from app.core.models import AnalysisSession, CodeSnippet, CodeResponse, CodePair, CodePairMessage, AnalysisSessionSummary
from app.core.tools import analysis_function_dictionary
from magenta.routes.chats import create_chat, delete_chat, send_chat, get_chat_message_status, get_chat_status
from magenta.core.config import tenant_collections, logger
from magenta.core.models import ChatMessage, Task
from magenta.services.chat_service import process_chat
from datetime import datetime
import uuid
from pydantic import BaseModel


analysis_router = APIRouter(prefix="/analysis", tags=["analysis"])


@analysis_router.get("/", response_model=List[AnalysisSessionSummary])
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
  sysprompt_id: str = "radian0",
  title: Optional[str] = None,
  description: Optional[str] = None
):
  analysis_collection = tenant_collections.get_collection(tenant_id, "analysis")

  session_id = str(uuid.uuid4())
  logger.info(f"Creating analysis session {session_id}")

  # create a chat
  chat = await create_chat(
    chat_id=session_id,
    context_id=context_id,
    tenant_id=tenant_id,
    sysprompt_id=sysprompt_id
  )
  logger.info(f"Created chat {chat}")

  analysis_session = AnalysisSession(
    context_id=context_id,
    session_id=session_id,
    tenant_id=tenant_id,
    sysprompt_id=sysprompt_id,
    chat_id=chat["chat_id"],
    title=title,
    description=description
  )
  
  analysis_collection.insert_one(analysis_session.model_dump(exclude_none=True))
  logger.info(f"Inserted analysis session {analysis_session}")
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


@analysis_router.get("/{session_id}/messages", response_model=List[ChatMessage])
async def get_messages_from_analysis_session(
	session_id: str,
	since_timestamp: Optional[datetime] = Query(None, description="Filter messages after this timestamp"),
	since_message_id: Optional[str] = Query(None, description="Filter messages after this message ID"),
	tenant_id: str = "default"
):
	analysis_collection = tenant_collections.get_collection(tenant_id, "analysis")

	messages = analysis_collection.find_one({"session_id": session_id}, {"messages": 1, "_id": 0})
	if not messages or "messages" not in messages:
		raise HTTPException(status_code=404, detail="No messages found")
	
	filtered_messages = messages["messages"]
	
	if since_timestamp:
		filtered_messages = [m for m in filtered_messages if m["timestamp"] > since_timestamp]
	
	if since_message_id:
		try:
			message_index = next(i for i, m in enumerate(messages["messages"]) if m["message_id"] == since_message_id)
			filtered_messages = messages["messages"][message_index + 1:]
		except StopIteration:
			raise HTTPException(status_code=404, detail=f"Message with ID {since_message_id} not found")
	
	return [ChatMessage(**message) for message in filtered_messages]


@analysis_router.post("/{session_id}/messages", response_model=Dict[str, str])
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
    context_arguments={"session_id": session_id, "tenant_id": tenant_id},
    json_mode=False,
    tool_choice="auto",
    function_dictionary=analysis_function_dictionary,
    chats_collection=tenant_collections.get_collection(tenant_id, "chats"),
    prompts_collection=tenant_collections.get_collection(tenant_id, "prompts"),
    documents_collection=tenant_collections.get_collection(tenant_id, "documents"),
    tools_collection=tenant_collections.get_collection(tenant_id, "tools")
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

  return {"task_id": message_id, "status": "success"}


@analysis_router.get("/{session_id}/messages/status", response_model=Dict[str, Task])
async def get_analysis_session_message_statuses(
    session_id: str,
    message_ids: Optional[List[str]] = Query(None),
    status: Optional[str] = Query(None, description="Filter by status (e.g., 'pending', 'completed')"),
    tenant_id: str = "default"
):
  if not message_ids:
    # If no message IDs provided, return only the latest status
    latest_status = await get_chat_status(session_id, tenant_id)
    if status is None or latest_status["status"] == status:
      return {latest_status["task_id"]: latest_status}
    return {}

  # Get status for each message ID
  result = {}
  for message_id in message_ids:
    try:
      message_status = await get_chat_message_status(session_id, message_id, tenant_id)
      if status is None or message_status["status"] == status:
        result[message_id] = message_status
    except HTTPException:
      continue
    
  return result


@analysis_router.get("/{session_id}/messages/{message_id}", response_model=ChatMessage)
async def get_message_from_analysis_session(session_id: str, message_id: str, tenant_id: str = "default"):
  analysis_collection = tenant_collections.get_collection(tenant_id, "analysis")
  if not analysis_collection.count_documents({"session_id": session_id}):
    raise HTTPException(status_code=404, detail="Analysis session not found")

  message = analysis_collection.find_one({"session_id": session_id, "messages.message_id": message_id}, {"_id": 0})
  if not message:
    raise HTTPException(status_code=404, detail="Message not found")
  
  message_object = ChatMessage(**message["messages"][0])
  return message_object


@analysis_router.get("/{session_id}/code", response_model=List[CodePairMessage])
async def get_code_from_analysis_session(session_id: str, tenant_id: str = "default"):
  analysis_collection = tenant_collections.get_collection(tenant_id, "analysis")

  code_snippets = analysis_collection.find_one({"session_id": session_id}, {"code_snippets": 1, "_id": 0})
  if not code_snippets:
    raise HTTPException(status_code=404, detail="No code snippets found")
  
  return [CodePairMessage(**code_snippet) for code_snippet in code_snippets["code_snippets"]]


@analysis_router.post("/{session_id}/code", response_model=Dict[str, str])
async def add_code_to_analysis_session(
  session_id: str,
  code: CodePair,
  background_tasks: BackgroundTasks,
  tenant_id: str = "default",
  dry_run: bool = False
):
  analysis_collection = tenant_collections.get_collection(tenant_id, "analysis")

  message_to_process = "[CODE]\n\n[INPUT]\n\n```" + code.input.code_snippet + "```\n\n"

  if code.output:
    message_to_process += "[OUTPUT]\n\n```" + code.output.response + "```\n\n"

  code_message_id = str(uuid.uuid4())

  background_tasks.add_task(
    process_chat,
    chat_id=session_id,
    message_id=code_message_id,
    new_message=message_to_process,
    dry_run=dry_run,
    context_arguments={"session_id": session_id, "tenant_id": tenant_id},
    json_mode=False,
    tool_choice="auto",
    function_dictionary=analysis_function_dictionary,
    chats_collection=tenant_collections.get_collection(tenant_id, "chats"),
    prompts_collection=tenant_collections.get_collection(tenant_id, "prompts"),
    documents_collection=tenant_collections.get_collection(tenant_id, "documents"),
    tools_collection=tenant_collections.get_collection(tenant_id, "tools")
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

  return {"task_id": code_message_id, "status": "success"}


@analysis_router.get("/{session_id}/code/{message_id}", response_model=CodePairMessage)
async def get_code_from_analysis_session(session_id: str, message_id: str, tenant_id: str = "default"):
  analysis_collection = tenant_collections.get_collection(tenant_id, "analysis")
  if not analysis_collection.count_documents({"session_id": session_id}):
    raise HTTPException(status_code=404, detail="Analysis session not found")

  code_message = analysis_collection.find_one({"session_id": session_id, "code_snippets.message_id": message_id}, {"_id": 0})
  if not code_message:
    raise HTTPException(status_code=404, detail="Code message not found")
  
  code_message_object = CodePairMessage(**code_message["code_snippets"][0])
  return code_message_object


@analysis_router.put("/{session_id}", response_model=AnalysisSession)
async def update_analysis_session(
    session_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    tenant_id: str = "default"
):
  analysis_collection = tenant_collections.get_collection(tenant_id, "analysis")
  
  # Build update dictionary with only provided fields
  update_fields = {}
  if title is not None:
    update_fields["title"] = title
  if description is not None:
    update_fields["description"] = description
      
  if not update_fields:
    raise HTTPException(status_code=400, detail="No fields to update provided")

  result = analysis_collection.find_one_and_update(
    {"session_id": session_id},
    {"$set": update_fields},
    return_document=True,
    projection={"_id": 0}
  )
  
  if not result:
    raise HTTPException(status_code=404, detail="Analysis session not found")
  
  return AnalysisSession(**result)
