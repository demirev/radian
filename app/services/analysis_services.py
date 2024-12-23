from typing import Literal
from magenta.core.config import tenant_collections, logger
from magenta.core.models import ChatMessage
from magenta.services.chat_service import process_chat
from core.tools import analysis_function_dictionary

async def process_analysis_message(
    message: str, 
    message_id: str,
		session_id: str,
    tenant_id: str = "default", 
    dry_run: bool = False,
		type: Literal["code", "message"] = "message"
):
  pass # not currently used, intead calling process_chat directly. May be used in the future.

  try:
    analysis_collection = tenant_collections.get_collection(tenant_id, "analysis")
    chat_collection = tenant_collections.get_collection(tenant_id, "chats")
		
    if not analysis_collection.count_documents({"session_id": session_id}):
      raise ValueError(f"Analysis object not found for session {session_id}")
    if not chat_collection.count_documents({"chat_id": session_id}):
      raise ValueError(f"Chat object not found for session {session_id}")
		
    response = await process_chat(
      chat_id=session_id,
      message_id=message_id,
      new_message=message,
      dry_run=dry_run,
      context_arguments={"session_id": session_id},
      json_mode=False,
      tool_choice="auto",
      function_dictionary=analysis_function_dictionary,
      chats_collection=tenant_collections.get_collection(tenant_id, "chats"),
      prompts_collection=tenant_collections.get_collection(tenant_id, "prompts"),
      documents_collection=tenant_collections.get_collection(tenant_id, "documents"),
      tools_collection=tenant_collections.get_collection(tenant_id, "tools")
    )
		
    # re-fetch analysis object to see if agent made any changes
    analysis_object = analysis_collection.find_one({"session_id": session_id}, {"_id": 0})
		
    if not analysis_object:
      raise ValueError(f"Analysis object not found for session {session_id}")
    
  except Exception as e:
    logger.error(f"Error processing message {message_id}: {e}")
