from app.core.models import CodeSnippet, CodePair, CodePairMessage
from magenta.core.config import logger, tenant_collections
from magenta.core.models import ChatMessage
from datetime import datetime
import uuid
from typing import Literal

# functions ------------------------------------------
def suggest_code(tenant_id: str, session_id: str, code: str, language: str):
  analysis_collection = tenant_collections.get_collection(tenant_id, "analysis")
  analysis_object = analysis_collection.find_one({"session_id": session_id}, {"_id": 0})
  
  if not analysis_object:
    raise ValueError(f"Analysis object not found for session {session_id}")
  
  new_code_suggestion = CodePairMessage(
    message_id=uuid.uuid4(),
    content=code,
    role="assistant",
    timestamp=datetime.now(),
    type="code_pair",
    code_pair=CodePair(
      input=CodeSnippet(
        message_id=uuid.uuid4(),
        role="assistant",
        type="suggestion",
        language=language,
        code_snippet=code
      )
    )
  )
  
  analysis_collection.update_one(
    {"session_id": session_id},
    {"$push": {"code_snippets": new_code_suggestion.model_dump(exclude_none=True)}}
  )


def run_code(tenant_id: str, session_id: str, code: str, language: str):
  analysis_collection = tenant_collections.get_collection(tenant_id, "analysis")
  analysis_object = analysis_collection.find_one({"session_id": session_id}, {"_id": 0})
  
  if not analysis_object:
    raise ValueError(f"Analysis object not found for session {session_id}")
  
  new_code_execution = CodePairMessage(
    message_id=uuid.uuid4(),
    content=code,
    role="assistant",
    timestamp=datetime.now(),
    type="code_pair",
    code_pair=CodePair(
      input=CodeSnippet(
        message_id=uuid.uuid4(),
        role="assistant",
        type="execution",
        language=language,
        code_snippet=code
      )
    )
  )
  
  analysis_collection.update_one(
    {"session_id": session_id},
    {"$push": {"code_snippets": new_code_execution.model_dump(exclude_none=True)}}
  )


def send_user_message(tenant_id: str, session_id: str, message: str):
  analysis_collection = tenant_collections.get_collection(tenant_id, "analysis")
  analysis_object = analysis_collection.find_one({"session_id": session_id}, {"_id": 0})
  
  if not analysis_object:
    raise ValueError(f"Analysis object not found for session {session_id}")
  
  new_user_message = ChatMessage(
    message_id=uuid.uuid4(),
    content=message,
    role="assistant",
    timestamp=datetime.now()
  )

  analysis_collection.update_one(
    {"session_id": session_id},
    {"$push": {"messages": new_user_message.model_dump(exclude_none=True)}}
  )

# function schemas -----------------------------------
analysis_function_tool_definitions = [
 {
   "tool_id": "suggest_code",
   "type": "function",
   "function": {
     "name": "suggest_code",
     "description": "Store a code suggestion in the analysis session",
     "parameters": {
       "type": "object",
       "properties": {
         "code": {
           "type": "string",
           "description": "The code suggestion to store"
         },
         "language": {
           "type": "string",
           "description": "Programming language of the code (R or py)",
           "enum": ["R", "py"]
         }
       },
       "required": ["code", "language"]
     }
   },
   "context_parameters": [
     {"name": "tenant_id", "type": "string", "description": "ID of the tenant"},
     {"name": "session_id", "type": "string", "description": "ID of the analysis session"}
   ]
 },
 {
   "tool_id": "run_code",
   "type": "function",
   "function": {
     "name": "run_code",
     "description": "Store a code execution in the analysis session",
     "parameters": {
       "type": "object",
       "properties": {
         "code": {
           "type": "string",
           "description": "The code to execute"
         },
         "language": {
           "type": "string",
           "description": "Programming language of the code (R or py)",
           "enum": ["R", "py"]
         }
       },
       "required": ["code", "language"]
     }
   },
   "context_parameters": [
     {"name": "tenant_id", "type": "string", "description": "ID of the tenant"},
     {"name": "session_id", "type": "string", "description": "ID of the analysis session"}
   ]
 },
 {
   "tool_id": "send_user_message",
   "type": "function",
   "function": {
     "name": "send_user_message",
     "description": "Store a user message in the analysis session",
     "parameters": {
       "type": "object",
       "properties": {
         "message": {
           "type": "string",
           "description": "The message to store"
         }
       },
       "required": ["message"]
     }
   },
   "context_parameters": [
     {"name": "tenant_id", "type": "string", "description": "ID of the tenant"},
     {"name": "session_id", "type": "string", "description": "ID of the analysis session"}
   ]
 }
]

# function dictionary --------------------------------
analysis_function_dictionary = {
  "suggest_code": suggest_code,
  "run_code": run_code,
  "send_user_message": send_user_message
}

