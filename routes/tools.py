import uuid
from typing import List, Dict, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import HttpUrl
from core.config import logger, tenant_collections
from core.models import ToolWithContext, ToolParameter, ContextParameter, ToolParameters, ExternalToolBody, ToolBody, HttpMethod

tools_router = APIRouter(prefix="/tools", tags=["tools"])


@tools_router.get("/", response_model=List[ToolWithContext])
async def list_tools(
	name: Optional[str] = Query(None, title="Tool name", description="Filter by tool name"),
	tenant_id: str = "default"
):
	tools_collection = tenant_collections.get_collection(tenant_id, "tools")
	query = {}
	
	if name:
		query["function.name"] = name
	
	tool_documents = tools_collection.find(query, {"_id": 0})

	tools = [ToolWithContext(**tool) for tool in tool_documents]

	return list(tools)


@tools_router.get("/ids", response_model=List[Dict[str, str]])
async def list_tool_ids(
	tenant_id: str = "default",
	name: Optional[str] = Query(None, title="Tool name", description="Filter by tool name")
):
	tools_collection = tenant_collections.get_collection(tenant_id, "tools")
	query = {}
	
	if name:
		query["function.name"] = name
	
	# Only retrieve tool_id and function.name fields
	tools = tools_collection.find(
		query, 
		{"_id": 0, "tool_id": 1, "function.name": 1, "function.description": 1}
	)
	
	# Reshape the nested structure to flat {tool_id, name} format
	tool_ids = [
		{
			"tool_id": tool["tool_id"],
			"name": tool["function"]["name"],
			"description": tool["function"]["description"]
		} 
		for tool in tools
	]
	
	return tool_ids


@tools_router.post("/create", response_model=ToolWithContext)
async def create_tool(
	name: str, 
	description: str, 
	parameters: dict[str, ToolParameter],
	required: list[str],
	url: Optional[HttpUrl] = None,
	method: Optional[HttpMethod] = None,
	context_parameters: Optional[list[ContextParameter]] = None,
	tenant_id: str = "default"
):
	try:
		tools_collection = tenant_collections.get_collection(tenant_id, "tools")
		# check if name already exists
		if tools_collection.find_one({"function.name": name}, {"_id": 0}):
			raise HTTPException(status_code=400, detail="Tool name already exists")
		
		# check if required parameters are provided
		provided_parameters = set(parameters.keys())
		if not set(required).issubset(provided_parameters):
			raise HTTPException(status_code=400, detail="Required parameters not provided")
		
		# check that at least one parameter is required
		if len(required) == 0:
			raise HTTPException(status_code=400, detail="At least one parameter must be required")

		# create tool
		tool_id = str(uuid.uuid4())

		logger.info(f"Creating new tool {name}, ID {tool_id}.")

		function_body = ExternalToolBody(
			name=name,
			description=description,
			parameters=ToolParameters(
				type="object",
				properties=parameters,
				required=required
			),
			url=url,
			method=method
		) if url and method else ToolBody(
			name=name,
			description=description,
			parameters=ToolParameters(
				type="object",
				properties=parameters,
				required=required
			)
		)

		tool = ToolWithContext(
			tool_id=tool_id,
			type="external" if url and method else "function",
			function=function_body,
			context_parameters=context_parameters
		)

		# Insert new tool
		logger.info(f"Inserting new tool {name}, ID {tool_id}.")
		tools_collection.insert_one(tool.model_dump(exclude_none=True))
		logger.info(f"Created new tool {name}, ID {tool_id}.")
		return tool
	
	except Exception as e:
		logger.error(f"Error creating tool: {e}")
		raise HTTPException(status_code=400, detail="Error creating tool")
	

@tools_router.get("/{tool_id}", response_model=ToolWithContext)
async def get_tool(
	tool_id: str,
	tenant_id: str = "default"
):
	tools_collection = tenant_collections.get_collection(tenant_id, "tools")
	tool_document = tools_collection.find_one({"tool_id": tool_id}, {"_id": 0})
	if not tool_document:
		logger.warning(f"Tool {tool_id} not found.")
		raise HTTPException(status_code=404, detail="Tool not found")
	tool = ToolWithContext(**tool_document)
	return tool


@tools_router.put("/{tool_id}", response_model=ToolWithContext)
async def update_tool(
	tool_id: str,
	name: Optional[str] = None,
	description: Optional[str] = None,
	parameters: Optional[dict[str, ToolParameter]] = None,
	required: Optional[list[str]] = None,
	url: Optional[HttpUrl] = None,
	method: Optional[HttpMethod] = None,
	context_parameters: Optional[list[ContextParameter]] = None,
	tenant_id: str = "default"
):
	try:
		tools_collection = tenant_collections.get_collection(tenant_id, "tools")
		tool = tools_collection.find_one({"tool_id": tool_id})
		if not tool:
			logger.warning(f"Tool {tool_id} not found.")
			raise HTTPException(status_code=404, detail="Tool not found")
		
		update_data = {}
		if name:
			update_data["function.name"] = name
		if description:
			update_data["function.description"] = description
		if parameters:
			update_data["function.parameters.properties"] = {
				key: value.model_dump(exclude_none=True) for key, value in parameters.items()
			}
		if required:
			update_data["function.parameters.required"] = required
		if url:
			update_data["function.url"] = str(url)
			update_data["type"] = "external"
		if method:
			update_data["function.method"] = method.value
			update_data["type"] = "external"
		if context_parameters is not None:
			update_data["context_parameters"] = [cp.model_dump(exclude_none=True) for cp in context_parameters]

		tools_collection.update_one({"tool_id": tool_id}, {"$set": update_data})

		updated_tool = tools_collection.find_one({"tool_id": tool_id}, {"_id": 0})
		logger.info(f"Updated tool {tool_id}.")
		return ToolWithContext(**updated_tool).model_dump(exclude_none=True)
	
	except Exception as e:
		logger.error(f"Error updating tool: {e}")
		raise HTTPException(status_code=400, detail="Error updating tool")


@tools_router.delete("/{tool_id}")
async def delete_tool(
	tool_id: str,
	tenant_id: str = "default"
):
	tools_collection = tenant_collections.get_collection(tenant_id, "tools")
	result = tools_collection.delete_one({"tool_id": tool_id})
	if result.deleted_count == 0:
		logger.warning(f"Tool {tool_id} not found.")
		raise HTTPException(status_code=404, detail="Tool not found")
	logger.info(f"Deleted tool {tool_id}.")
	return {"message": "Tool deleted successfully"}