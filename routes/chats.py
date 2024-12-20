import uuid
from fastapi import APIRouter, Depends, BackgroundTasks, UploadFile, File, Query
from fastapi.exceptions import HTTPException
from typing import Optional, List, Any, Dict
from core.config import logger, tenant_collections, get_db
from core.models import Task, Chat, ChatInternalMessage, ChatMessage, AgentType
from services.chat_service import process_chat, call_gpt
from services.document_service import perform_postgre_search
from sqlalchemy.orm import Session

# chats router --------------------------------------------------------
chats_router = APIRouter(prefix="/chats", tags=["chats"])


@chats_router.post("/create", response_model=Chat)
async def create_chat(
	chat_id: str, 
	context_id: str,
	tenant_id: str = "default",
	sysprompt_id: Optional[str] = None,
	agent: AgentType = AgentType.borrower_assistant,
	description: Optional[str] = None
):
	try:
		chats_collection = tenant_collections.get_collection(tenant_id, "chats")
		prompts_collection = tenant_collections.get_collection(tenant_id, "prompts")

		if sysprompt_id is not None and not prompts_collection.find_one({"prompt_id": sysprompt_id}): 
			raise HTTPException(status_code=400, detail="System prompt not found")

		if chats_collection.count_documents({"chat_id": chat_id}) > 0:
			raise HTTPException(status_code=400, detail="Chat already exists")

		# assign system prompt
		if sysprompt_id is None:
			if agent == AgentType.borrower_assistant:
				sysprompt_id = "demoassistant0"
			elif agent == AgentType.loan_officer_assistant:
				sysprompt_id = "demoloassistant0"
			elif agent == AgentType.setup_wizard:
				sysprompt_id = "setupwizard0" # TODO
			elif agent == AgentType.test_agent:
				sysprompt_id = "diceroller"  # so we test with a simple dummy agent
			elif agent == AgentType.test_rag_agent:
				sysprompt_id = "passwordteller"  # so we test with a simple dummy agent with document access
			else:
				raise HTTPException(status_code=400, detail="Invalid agent id") # unreachable but just in case
		else:
			logger.info(f"Using provided system prompt {sysprompt_id} for chat {chat_id}.")
		
		chat = {
			"chat_id": chat_id,
			"context_id": context_id,
			"agent": agent.value,
			"sysprompt_id": sysprompt_id,
			"messages": [],
			"statuses": []
		}

		if description is not None:
			chat["description"] = description

		chats_collection.insert_one(chat)
		logger.info(f"Created new chat {chat_id}, context {context_id}.")

		return chat

	except Exception as e:
		logger.error(f"Error creating chat: {e}")
		raise HTTPException(status_code=400, detail="Error creating chat")  


@chats_router.post("/{chat_id}/send", response_model=Task)
async def send_chat(
	chat_id: str,
	message: str,
	background_tasks: BackgroundTasks,
	tenant_id: str = "default",
	dry_run: Optional[bool] = False,
	db: Session = Depends(get_db)
):
	try:
		chats_collection = tenant_collections.get_collection(tenant_id, "chats")
		prompts_collection = tenant_collections.get_collection(tenant_id, "prompts")
		documents_collection = tenant_collections.get_collection(tenant_id, "documents")
		tools_collection = tenant_collections.get_collection(tenant_id, "tools")
		
		# find chat in db
		chat = chats_collection.count_documents({"chat_id": chat_id})
		if chat == 0:
			raise HTTPException(status_code=404, detail="Chat not found")

		# create a message_id for the response
		message_id = str(uuid.uuid4())

		background_tasks.add_task(
			process_chat,
			chat_id=chat_id,
			message_id=message_id,
			new_message=message,
			sysprompt_id=None,  # will use the one whose id is saved in the chat document in db
			chats_collection=chats_collection,
			prompts_collection=prompts_collection,
			documents_collection=documents_collection,
			tools_collection=tools_collection,
			dry_run=dry_run,
			call_llm_func=call_gpt,
			rag_func=perform_postgre_search,
			rag_table_name=tenant_id, # using tenant_id as table_name for now, later we might have separate schemas for different tenants
			persist_rag_results=False,
			db=db,
			spacy_model=None
		)

		return {"task_id": message_id, "status":"pending"}
	
	except Exception as e:
		logger.error(f"Error sending chat: {e}")
		raise HTTPException(status_code=400, detail="Error sending chat")


@chats_router.get("/", response_model=List[Chat])
async def list_chats(
	tenant_id: str = "default",
	agent: Optional[AgentType] = Query(None, title="Type of chat", description="Filter by chat type"),
	context_id: Optional[str] = Query(None, title="context identifier", description="Filter by context_id"),
	user_id: Optional[str] = Query(None, title="user identifier", description="Filter by user_id")
):
	chats_collection = tenant_collections.get_collection(tenant_id, "chats")
	query = {}
	
	if agent:
		query["agent"] = agent.value
	if context_id:
		query["context_id"] = context_id
	if user_id:
		query["user_id"] = user_id

	chats = list(chats_collection.find(query, {"_id": 0}))
	logger.info(f"Found {len(chats)} chats.")

	# remove internal messages from the response
	processed_chats = []
	for chat in chats:
		chat["messages"] = [m for m in chat["messages"] if "message_id" in m] # internal messages have no message_id
		processed_chats.append(chat)

	return processed_chats


@chats_router.get("/{chat_id}", response_model=Chat)
async def get_chat(
	chat_id: str,
	tenant_id: str = "default"
):
	chats_collection = tenant_collections.get_collection(tenant_id, "chats")
	chat = chats_collection.find_one({"chat_id": chat_id}, {"_id": 0})
	if not chat:
		raise HTTPException(status_code=404, detail="Chat not found")
	chat["messages"] = [m for m in chat["messages"] if "message_id" in m] # internal messages have no message_id
	return chat


@chats_router.get("/{chat_id}/messages", response_model=List[ChatInternalMessage])
async def list_chat_messages(
	chat_id: str,
	tenant_id: str = "default",
	no_internal: Optional[bool] = True
):
	chats_collection = tenant_collections.get_collection(tenant_id, "chats")
	chat = chats_collection.find_one({"chat_id": chat_id}, {"_id": 0})
	
	if not chat:
		raise HTTPException(status_code=404, detail="Chat not found")
	
	messages = chat["messages"]

	if no_internal:
		messages = [m for m in messages if "message_id" in m] # internal messages have no message_id
	
	messages = [
		{
			"message_id": message.get("message_id", None), # internal messages such as tool calls may not have message_id
			"role": message["role"],
			"content": message.get("content", "--INTERNAL--"),
			"timestamp": message.get("timestamp", None) # internal messages may not have timestamp
		} for message in messages
	]

	return messages


@chats_router.get("/{chat_id}/messages/{message_id}", response_model=ChatMessage)
async def get_chat_message(
	chat_id: str,
	message_id: str,
	tenant_id: str = "default"
):
	chats_collection = tenant_collections.get_collection(tenant_id, "chats")
	chat = chats_collection.find_one({"chat_id": chat_id}, {"_id": 0})
	if not chat:
		raise HTTPException(status_code=404, detail="Chat not found")
	messages = chat["messages"]
	message = next((m for m in messages if m.get("message_id", False) == message_id), None)
	if not message:
		raise HTTPException(status_code=404, detail="Message not found")
	return message

@chats_router.get("/{chat_id}/messages/{message_id}/status", response_model=Task)
async def get_chat_message_status(
	chat_id: str,
	message_id: str,
	tenant_id: str = "default"
):
	chats_collection = tenant_collections.get_collection(tenant_id, "chats")
	chat = chats_collection.find_one({"chat_id": chat_id}, {"_id": 0})
	if not chat:
		raise HTTPException(status_code=404, detail="Chat not found")
	statuses = chat["statuses"]
	status = next((s for s in statuses if s["message_id"] == message_id), None)
	if not status:
		raise HTTPException(status_code=404, detail="Message not found")
	return {"task_id": message_id, "status": status["status"]}


@chats_router.get("/{chat_id}/status", response_model=Task)
async def get_chat_status(
	chat_id: str,
	tenant_id: str = "default"
):
	# status of latest message
	chats_collection = tenant_collections.get_collection(tenant_id, "chats")
	chat = chats_collection.find_one({"chat_id": chat_id}, {"_id": 0})
	if not chat:
		raise HTTPException(status_code=404, detail="Chat not found")
	statuses = chat["statuses"]
	if len(statuses) == 0:
		raise HTTPException(status_code=404, detail="No messages found")
	latest_status = statuses[-1]
	return {"task_id": latest_status["message_id"], "status": latest_status["status"]}


@chats_router.delete("/{chat_id}")
async def delete_chat(
	chat_id: str,
	tenant_id: str = "default"
):
	chats_collection = tenant_collections.get_collection(tenant_id, "chats")
	result = chats_collection.delete_one({"chat_id": chat_id})
	if result.deleted_count == 0:
		raise HTTPException(status_code=404, detail="Chat not found")
	return {"message": "Chat deleted successfully"}


@chats_router.delete("/{chat_id}/messages/{message_id}")
async def delete_chat_message(
	chat_id: str,
	message_id: str,
	tenant_id: str = "default"
):
	chats_collection = tenant_collections.get_collection(tenant_id, "chats")
	result = chats_collection.update_one(
		{"chat_id": chat_id},
		{"$pull": {"messages": {"message_id": message_id}}}
	)
	if result.modified_count == 0:
		raise HTTPException(status_code=404, detail="Message not found")
	return {"message": "Message deleted successfully"}

