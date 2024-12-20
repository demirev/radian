from typing import Literal
from magenta.core.config import tenant_collections, logger
from magenta.core.models import ChatMessage
from magenta.services.chat_service import process_chat

async def process_analysis_message(
    message: str, 
    message_id: str,
		session_id: str,
    tenant_id: str = "default", 
    dry_run: bool = False,
		type: Literal["code", "message"] = "message"
):
  pass

  try:
    analysis_collection = tenant_collections.get_collection(tenant_id, "analysis")
    chat_collection = tenant_collections.get_collection(tenant_id, "chats")
		
    if not analysis_collection.count_documents({"session_id": session_id}):
      raise ValueError(f"Analysis object not found for session {session_id}")
    if not chat_collection.count_documents({"chat_id": session_id}):
      raise ValueError(f"Chat object not found for session {session_id}")
		
    await process_chat(
      chat_id=session_id,
      message_id=message_id,
      new_message=message,
      dry_run=dry_run,
      context_arguments={"session_id": session_id},
      json_mode=False,
      tool_choice="auto"
    )
		
    # re-fetch analysis object to see if agent made any changes
    analysis_object = analysis_collection.find_one({"session_id": session_id}, {"_id": 0})
		
    if not analysis_object:
      raise ValueError(f"Analysis object not found for session {session_id}")

  except Exception as e:
    logger.error(f"Error processing message {message_id}: {e}")
