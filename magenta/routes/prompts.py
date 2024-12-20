from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from core.config import tenant_collections, logger
from core.models import Prompt, RagSpec, Task


prompts_router = APIRouter(prefix="/prompts", tags=["prompts"])


@prompts_router.post("/create", response_model=Task)
async def create_prompt(
	name: str, 
	type: str, 
	prompt: str, 
	prompt_id: Optional[str] = None,
	description: Optional[str] = None,
	toolset: Optional[List[str]] = None,
	documents: Optional[RagSpec] = None,
	tenant_id: str = "default"
):
	prompts_collection = tenant_collections.get_collection(tenant_id, "prompts")
	
	# If prompt_id is provided, check if it already exists
	if prompt_id:
		existing_prompt = prompts_collection.find_one({"prompt_id": prompt_id})
		if existing_prompt:
			raise HTTPException(status_code=400, detail=f"Prompt ID {prompt_id} already exists")
	else:
		# If prompt_id is not provided, generate one from the name
		prompt_id = name.replace(" ", "").lower()

	# Check if prompt name already exists
	while prompts_collection.find_one({"name": name}):
		raise HTTPException(status_code=400, detail=f"Prompt name {name} already exists")
	
	# validate prompt
	try:
		prompt_obj = Prompt(
			prompt_id=prompt_id,
			name=name,
			type=type,
			prompt=prompt,
			description=description,
			toolset=toolset,
			documents=documents
		)
	except Exception as e:
		logger.error(f"Error creating prompt: {e}")
		raise HTTPException(status_code=400, detail="Error creating prompt")

	# Insert new prompt
	try:
		prompts_collection.insert_one(prompt_obj.model_dump())
	except Exception as e:
		logger.error(f"Error inserting prompt into database: {e}")
		raise HTTPException(status_code=500, detail="Error saving prompt to database")

	logger.info(f"Created new prompt {name}, ID {prompt_id}.")
	return {"task_id": prompt_id, "status":"created", "type":"prompt creation"}


@prompts_router.get("/", response_model=List[Prompt])
async def list_prompts(
	prompt_id: Optional[str] = Query(None, title="Prompt ID", description="Filter by prompt ID"),
	name: Optional[str] = Query(None, title="Prompt name", description="Filter by prompt name"),
	type: Optional[str] = Query(None, title="Prompt type", description="Filter by prompt type"),
	tenant_id: str = "default"
):
	prompts_collection = tenant_collections.get_collection(tenant_id, "prompts")
	
	query = {}
	if prompt_id:
		query["prompt_id"] = prompt_id
	if name:
		query["name"] = name
	if type:
		query["type"] = type
	
	prompts = prompts_collection.find(query, {"_id": 0})

	return list(prompts)


@prompts_router.get("/{prompt_id}", response_model=Prompt)
async def get_prompt(
	prompt_id: str,
	tenant_id: str = "default"
):
	prompts_collection = tenant_collections.get_collection(tenant_id, "prompts")
	prompt = prompts_collection.find_one({"prompt_id": prompt_id}, {"_id": 0})
	if not prompt:
		logger.warning(f"Prompt {prompt_id} not found.")
		raise HTTPException(status_code=404, detail="Prompt not found")
	return prompt


@prompts_router.delete("/{prompt_id}")
async def delete_prompt(
	prompt_id: str,
	tenant_id: str = "default"
):
	prompts_collection = tenant_collections.get_collection(tenant_id, "prompts")
	result = prompts_collection.delete_one({"prompt_id": prompt_id})
	if result.deleted_count == 0:
		logger.warning(f"Prompt {prompt_id} not found.")
		raise HTTPException(status_code=404, detail="Prompt not found")
	logger.info(f"Deleted prompt {prompt_id}.")
	return {"message": "Prompt deleted successfully"}


@prompts_router.put("/{prompt_id}", response_model=Prompt)
async def update_prompt(
	prompt_id: str,
	name: Optional[str] = None,
	type: Optional[str] = None,
	prompt: Optional[str] = None,
	description: Optional[str] = None,
	toolset: Optional[List[str]] = None,
	documents: Optional[RagSpec] = None,
	tenant_id: str = "default"
):
	prompts_collection = tenant_collections.get_collection(tenant_id, "prompts")
	
	# Check if prompt exists
	existing_prompt = prompts_collection.find_one({"prompt_id": prompt_id})
	if not existing_prompt:
		raise HTTPException(status_code=404, detail=f"Prompt ID {prompt_id} not found")
	
	# Prepare update data
	update_data = {}
	if name is not None:
		update_data["name"] = name
	if type is not None:
		update_data["type"] = type
	if prompt is not None:
		update_data["prompt"] = prompt
	if description is not None:
		update_data["description"] = description
	if toolset is not None:
		update_data["toolset"] = toolset
	if documents is not None:
		update_data["documents"] = documents.model_dump()
	
	if not update_data:
		raise HTTPException(status_code=400, detail="No update data provided")
	
	# Update prompt
	try:
		result = prompts_collection.update_one({"prompt_id": prompt_id}, {"$set": update_data})
		if result.modified_count == 0:
			logger.warning(f"No changes made when updating prompt {prompt_id}")
	except Exception as e:
		logger.error(f"Error updating prompt: {e}")
		raise HTTPException(status_code=500, detail="Error updating prompt in database")
	
	# Fetch and return updated prompt
	updated_prompt = prompts_collection.find_one({"prompt_id": prompt_id}, {"_id": 0})
	if not updated_prompt:
		raise HTTPException(status_code=404, detail="Updated prompt not found")
	logger.info(f"Updated prompt {prompt_id}. Changes: {update_data}")
	return Prompt(**updated_prompt)

