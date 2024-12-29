from typing import Dict, Optional
from fastapi import APIRouter, HTTPException
from app.core.models import SessionEnvFile
from magenta.core.config import tenant_collections
from base64 import b64decode
import re


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
  
  # Ensure context_id and tenant_id match the session
  env_file.context_id = analysis_session["context_id"]
  env_file.tenant_id = tenant_id
  
  env_data = env_file.model_dump()
  env_collection.insert_one(env_data)
  
  return SessionEnvFile(**env_data)


@environments_router.put("/{session_id}", response_model=SessionEnvFile)
async def update_environment(
  session_id: str,
  env_file: SessionEnvFile,
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
  
  # Ensure context_id and tenant_id match the session
  env_file.context_id = analysis_session["context_id"]
  env_file.tenant_id = tenant_id
  
  result = env_collection.find_one_and_update(
    {"session_id": session_id},
    {"$set": {
      "env_file": env_file.env_file,
      "context_id": env_file.context_id,
      "tenant_id": env_file.tenant_id
    }},
    return_document=True,
    projection={"_id": 0}
  )
  
  if not result:
    raise HTTPException(status_code=404, detail="Environment file not found")
  
  return SessionEnvFile(**result)


@environments_router.delete("/{session_id}", response_model=Dict[str, str])
async def delete_environment(session_id: str, tenant_id: str = "default"):
  env_collection = tenant_collections.get_collection(tenant_id, "environments")
  
  result = env_collection.delete_one({"session_id": session_id})
  
  if result.deleted_count == 0:
    raise HTTPException(status_code=404, detail="Environment file not found")
  
  return {"status": "success"}
