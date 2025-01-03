from typing import Dict, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.core.models import SessionEnvFile
from app.services.analysis_services import upload_file_to_gridfs, get_file_from_gridfs
from magenta.core.config import tenant_collections
from base64 import b64decode
import re
from gridfs import GridFS
from magenta.core.config import logger


environments_router = APIRouter(prefix="/environments", tags=["environments"])


@environments_router.get("/{session_id}", response_model=SessionEnvFile)
async def get_environment(session_id: str, tenant_id: str = "default"):
  # First verify the analysis session exists and get its context_id
  analysis_collection = tenant_collections.get_collection(tenant_id, "analysis")
  analysis_session = analysis_collection.find_one({"session_id": session_id})
  if not analysis_session:
    raise HTTPException(status_code=404, detail="Analysis session not found")
  
  env_collection = tenant_collections.get_collection(tenant_id, "environments")
  env_file = env_collection.find_one({"session_id": session_id}, {"_id": 0})
  
  if not env_file:
    raise HTTPException(status_code=404, detail="Environment file not found")
  
  # Convert ObjectId to string if file_id exists
  if "file_id" in env_file:
    env_file["file_id"] = str(env_file["file_id"])
  
  # Get file content from GridFS if it exists
  file_content = await get_file_from_gridfs(session_id, tenant_id)
  if file_content:
    env_file["env_file"] = file_content
  
  return SessionEnvFile(**env_file)


def is_valid_base64(s: str) -> bool:
    # Check if string is valid base64 format
    pattern = r'^[A-Za-z0-9+/]*={0,2}$'
    if not re.match(pattern, s):
        return False
    
    # Check if padding is correct
    if len(s) % 4:
        return False
    
    try:
        b64decode(s)
        return True
    except Exception:
        return False


@environments_router.post("/{session_id}", response_model=SessionEnvFile)
async def create_environment(
  session_id: str,
  env_file: SessionEnvFile,
  background_tasks: BackgroundTasks,
  tenant_id: str = "default"
):
  # Verify the analysis session exists and get its context_id
  analysis_collection = tenant_collections.get_collection(tenant_id, "analysis")
  analysis_session = analysis_collection.find_one({"session_id": session_id})
  if not analysis_session:
    raise HTTPException(status_code=404, detail="Analysis session not found")
  
  # Verify the base64 encoding
  if env_file.env_file and not is_valid_base64(env_file.env_file):
    raise HTTPException(status_code=400, detail="Invalid base64 encoding")
  
  env_collection = tenant_collections.get_collection(tenant_id, "environments")
  
  # Check if environment already exists
  if env_collection.find_one({"session_id": session_id}):
    raise HTTPException(status_code=400, detail="Environment file already exists for this session")
  
  # Create initial document without the file content
  env_data = {
    "session_id": session_id,
    "context_id": analysis_session["context_id"],
    "tenant_id": tenant_id
  }
  env_collection.insert_one(env_data)
  
  # Schedule file upload in background if file content exists
  if env_file.env_file:
    background_tasks.add_task(
      upload_file_to_gridfs,
      session_id,
      env_file.env_file,
      tenant_id
    )
  
  return SessionEnvFile(**env_data)


@environments_router.put("/{session_id}", response_model=SessionEnvFile)
async def update_environment(
  session_id: str,
  env_file: SessionEnvFile,
  background_tasks: BackgroundTasks,
  tenant_id: str = "default"
):
  # Verify the analysis session exists and get its context_id
  analysis_collection = tenant_collections.get_collection(tenant_id, "analysis")
  analysis_session = analysis_collection.find_one({"session_id": session_id})
  if not analysis_session:
    raise HTTPException(status_code=404, detail="Analysis session not found")
  
  # Verify the base64 encoding
  if env_file.env_file and not is_valid_base64(env_file.env_file):
    raise HTTPException(status_code=400, detail="Invalid base64 encoding")
  
  env_collection = tenant_collections.get_collection(tenant_id, "environments")
  
  # Update metadata
  update_fields = {
    "context_id": analysis_session["context_id"],
    "tenant_id": tenant_id
  }
  
  result = env_collection.find_one_and_update(
    {"session_id": session_id},
    {"$set": update_fields},
    return_document=True,
    projection={"_id": 0}
  )
  
  if "file_id" in result:
    result["file_id"] = str(result["file_id"])

  if not result:
    raise HTTPException(status_code=404, detail="Environment file not found")
  
  # Schedule file upload in background if file content exists
  if env_file.env_file:
    background_tasks.add_task(
      upload_file_to_gridfs,
      session_id,
      env_file.env_file,
      tenant_id
    )
  
  return SessionEnvFile(**result)


@environments_router.delete("/{session_id}", response_model=Dict[str, str])
async def delete_environment(session_id: str, tenant_id: str = "default"):
  env_collection = tenant_collections.get_collection(tenant_id, "environments")
  
  # First get the environment to check for file_id
  env = env_collection.find_one({"session_id": session_id})
  if not env:
    raise HTTPException(status_code=404, detail="Environment file not found")
  
  # Delete GridFS file if it exists
  if "file_id" in env:
    db = tenant_collections.mongo_client[tenant_id]
    fs = GridFS(db)
    try:
      fs.delete(env["file_id"])
    except Exception as e:
      logger.error(f"Error deleting GridFS file for session {session_id}: {e}")
    
  # Delete the environment document
  env_collection.delete_one({"session_id": session_id})
    
  return {"status": "success"}
