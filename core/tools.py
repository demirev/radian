import random
import inspect
import httpx
import uuid
from datetime import datetime
from typing import Callable, Dict, List, Any
from .models import Tool, ToolWithContext, HttpMethod
from .config import logger, tenant_collections

# helpers for validating definitions --------------------------------------------
def validate_function_args(func: Callable, func_def: Dict[str, Any]) -> List[str]:
	errors = []
	
	# Get the function's signature
	sig = inspect.signature(func)
	func_params = sig.parameters
	
	# Get the parameters from the function definition
	def_params = func_def['function']['parameters']['properties']
	required_params = func_def['function']['parameters'].get('required', [])
	
	# Get context parameters
	context_params = [param['name'] for param in func_def.get('context_parameters', [])]
	
	# Check if all defined parameters exist in the function
	for param_name in def_params:
		if param_name not in func_params and param_name not in context_params:
			errors.append(f"Parameter '{param_name}' is defined but missing.")
	
	# Check if all function parameters are defined
	for param_name, param in func_params.items():
		if param_name not in def_params and param_name not in context_params:
			errors.append(f"Function parameter '{param_name}' is not defined.")
		else:
			# Check if the parameter type matches
			param_type = def_params.get(param_name, {}).get('type')
			if param_type == 'integer' and param.annotation != int:
				errors.append(f"Parameter '{param_name}' is defined as 'integer' but isn't.")
			elif param_type == 'string' and param.annotation != str:
				errors.append(f"Parameter '{param_name}' is defined as 'string' but isn't.")
			elif param_type == 'array':
				# Check if the parameter is a List[str]
				if not (param.annotation == List[str] or 
						(hasattr(param.annotation, '__origin__') and 
						param.annotation.__origin__ == list and 
						param.annotation.__args__[0] == str)):
					errors.append(f"Parameter '{param_name}' is defined as 'array' but isn't List[str].")
			
			# Check if required parameters are correctly marked
			if param.default == inspect.Parameter.empty and param_name not in required_params and param_name not in context_params:
				errors.append(f"Required parameter '{param_name}' is not marked as required.")
			elif param.default != inspect.Parameter.empty and param_name in required_params:
				errors.append(f"Optional parameter '{param_name}' is marked as required.")
	
	return errors


def validate_all_functions(
    functions: Dict[str, Callable], 
    all_function_tool_definitions: List[Dict[str, Any]]
  ) -> Dict[str, List[str]]:
  validation_results = {}
  
  for func_def in all_function_tool_definitions:
    func_name = func_def['function']['name']
    if func_name not in functions:
      validation_results[func_name] = [f"Function '{func_name}' is defined but not implemented."]
    else:
      # Validate the function definition using ToolWithContext
      try:
        ToolWithContext(**func_def)
      except Exception as e:
        validation_results[func_name] = [f"Invalid tool definition: {str(e)}"]
        continue
      
      errors = validate_function_args(functions[func_name], func_def)
      validation_results[func_name] = errors if errors else ["No errors found."]
  
  return validation_results


# function definitions ----------------------------------------------------------
def roll_dice(d: int) -> int:
  return random.randint(1, d)


def get_current_utc_datetime() -> str:
  return datetime.utcnow().isoformat()


# json objects to describe functions --------------------------------------------
default_function_tool_definitions = [
	{
		"tool_id": "getcurrentutcdatetime",
		"type": "function",
		"function": {
			"name": "get_current_utc_datetime",
			"description": "Get the current UTC datetime",
			"parameters": {
				"type": "object",
				"properties": {},
				"required": []
			},
    },
    "context_parameters": []
	},
	{
		"tool_id": "rolldice",
		"type": "function",
		"function": {
			"name": "roll_dice",
			"description": "Roll a dice with d sides",
			"parameters": {
				"type": "object",
				"properties": {
					"d": {
						"type": "integer",
						"description": "Number of sides on the dice"
					}
				},
				"required": ["d"]
			}
		}
	}
]


# dictionary of function names --------------------------------------------------
default_function_dictionary = {
  "get_current_utc_datetime": get_current_utc_datetime,
  "roll_dice": roll_dice
}


# functions to be imported from other scripts ------------------------------------
def validate_function_dictionary(
		function_dictionary: dict, 
		all_function_tool_definitions: List[Dict[str, Any]]
	):
  result = validate_all_functions(function_dictionary, all_function_tool_definitions)
  # check if any errors were found
  all_errors = []
  for item in result:
    if result[item][0] != "No errors found.":
      all_errors.append({item: result[item]})
  if all_errors:
    logger.error(f"Errors found in function dictionary: {all_errors}")
    raise ValueError(f"Errors found in function dictionary: {all_errors}")


async def load_all_functions_in_db(
  mongo_connections, 
  overwrite=True,
  function_dictionary: dict = default_function_dictionary,
	all_function_tool_definitions: List[Dict[str, Any]] = default_function_tool_definitions
):
  # validate function dictionary
  validate_function_dictionary(function_dictionary, all_function_tool_definitions)

  # insert all functions into the database
  for mongo_connection in mongo_connections:
    for func_name in function_dictionary:
      # get function definition
      func_def = next((x for x in all_function_tool_definitions if x['function']['name'] == func_name), None)
      if func_def:
      
        # check if function already exists in the database
        if not overwrite:
          existing_func = mongo_connection.find_one({"function.name": func_name}, {"_id": 0})
          if existing_func:
            logger.info(f"Function '{func_name}' already exists in the database.")
            continue
        else:
          # remove existing function
          mongo_connection.delete_many({"function.name": func_name})

        # insert function definition into the database
        tool = ToolWithContext(**func_def) if 'context_parameters' in func_def else Tool(**func_def)
        mongo_connection.insert_one(tool.model_dump(exclude_none=True))
        logger.info(f"Function '{func_name}' inserted into the database.")
      else:
        logger.error(f"Function '{func_name}' not found in all_function_tool_definitions.")
        raise ValueError(f"Function '{func_name}' not found in all_function_tool_definitions.")


def tool_handler(
		name: str, 
		arguments: dict,
		tools_collection,
		function_dictionary: dict = default_function_dictionary,
		context_arguments: dict = None
	):
	# find tool in database
	tool = tools_collection.find_one({"function.name": name})
	if not tool:
		raise ValueError(f"Tool '{name}' not found in the database.")

	tool = ToolWithContext(**tool)

	# Prepare the arguments
	combined_arguments = arguments.copy()
	if context_arguments and tool.context_parameters:
		# Add context arguments that match the tool's context parameters
		for param in tool.context_parameters:
			if param.name in context_arguments:
				combined_arguments[param.name] = context_arguments[param.name]

	if tool.type == "external":
		# Handle external tool
		with httpx.Client() as client:
			if tool.function.method == HttpMethod.GET:
				response = client.get(str(tool.function.url), params=combined_arguments)
			elif tool.function.method == HttpMethod.POST:
				response = client.post(str(tool.function.url), json=combined_arguments)
			elif tool.function.method == HttpMethod.PUT:
				response = client.put(str(tool.function.url), json=combined_arguments)
			elif tool.function.method == HttpMethod.DELETE:
				response = client.delete(str(tool.function.url), params=combined_arguments)
			else:
				raise ValueError(f"Unsupported HTTP method: {tool.function.method}")
			response.raise_for_status()
			return response.json()
        
	else:
		# Handle function tool (existing logic)
		if name not in function_dictionary:
			raise ValueError(f"Tool '{name}' not found in function_dictionary.")
		function = function_dictionary[name]

		try:
			result = function(**combined_arguments)
		except Exception as e:
			logger.error(f"Error executing tool '{name}': {e}")
			result = f"ERROR when executing tool '{name}': {e}" # return str error to LLM which can potentially make another call to try and correct it
		
		return result
