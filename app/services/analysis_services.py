from typing import Literal
from magenta.core.config import tenant_collections, logger
from magenta.core.models import ChatMessage
from magenta.services.chat_service import process_chat
from app.core.tools import analysis_function_dictionary
from gridfs import GridFS
from base64 import b64decode, b64encode
from fastapi import HTTPException

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

async def upload_file_to_gridfs(
  session_id: str,
  file_content: str,
  tenant_id: str = "default"
) -> str:
  """
  Upload a base64 encoded file to GridFS
  Returns: The GridFS file ID as a string
  """
  try:
    # Get database and GridFS instance
    db = tenant_collections.mongo_client[tenant_id]
    fs = GridFS(db)
    env_collection = tenant_collections.get_collection(tenant_id, "environments")

    # Decode base64 content
    file_content_bytes = b64decode(file_content)
    
    # Remove old file if exists
    existing = env_collection.find_one({"session_id": session_id})
    if existing and "file_id" in existing:
      fs.delete(existing["file_id"])
    
    # Store new file
    file_id = fs.put(
      file_content_bytes,
      filename=f"env_{session_id}",
      session_id=session_id
    )
    
    # Update the environment document with the new file_id
    env_collection.update_one(
      {"session_id": session_id},
      {"$set": {"file_id": file_id}},
      upsert=True
    )
    
    return str(file_id)
    
  except Exception as e:
    logger.error(f"Error uploading file to GridFS for session {session_id}: {e}")
    raise HTTPException(status_code=500, detail=f"Error uploading file: {str(e)}")


async def get_file_from_gridfs(
  session_id: str,
  tenant_id: str = "default"
) -> str:
  """
  Retrieve a file from GridFS and return it as base64
  Returns: The file content as a base64 encoded string
  """
  try:
    db = tenant_collections.mongo_client[tenant_id]
    fs = GridFS(db)
    env_collection = tenant_collections.get_collection(tenant_id, "environments")
    
    env_file = env_collection.find_one({"session_id": session_id})
    if not env_file or "file_id" not in env_file:
      return None
      
    grid_out = fs.get(env_file["file_id"])
    content = grid_out.read()
    return b64encode(content).decode()
    
  except Exception as e:
    logger.error(f"Error retrieving file from GridFS for session {session_id}: {e}")
    raise HTTPException(status_code=500, detail=f"Error retrieving file: {str(e)}")
