import json
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from fastapi import Depends
from core.config import logger, openai_client, spacy_model, get_db
from core.models import ToolWithContext
from core.tools import tool_handler, default_function_dictionary
from .document_service import perform_postgre_search, add_rag_results_to_message, add_documents_to_sysprompt


def call_gpt(
    messages, sysprompt=None, client=openai_client, 
    json_mode=False, model = "gpt-4o", tools=None
  ):
  logger.info(f"Calling GPT")
  if sysprompt is not None:
    # add {role: "system", content: sysprompt} to the beginning of the messages list
    messages.insert(0, {"role": "system", "content": sysprompt})

  # make sure messages don't include message_id and timestamp
  messages = [{k: v for k, v in d.items() if k != "message_id" and k != "timestamp"} for d in messages]

  if not tools:
    logger.info(f"No tools found.")
    tools = []
  else:
    # remove tool_id from each tool
    tools = [{k: v for k, v in d.items() if k != "tool_id"} for d in tools]
    logger.info(f"Tools found: {tools}")

  if json_mode:
    if len(tools):
      completion = client.chat.completions.create(
        model=model,
        response_format={ "type": "json_object" },
        messages=messages,
        tools=tools,
        tool_choice="auto"
      )
    else:
      completion = client.chat.completions.create(
        model=model,
        response_format={ "type": "json_object" },
        messages=messages
      )
    
    result = {
      "message":json.loads(result.choices[0].message.content)
    }
  else:
    if len(tools):
      completion = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=tools,
        tool_choice="auto" if len(tools) else "none"
      )
    else:
      completion = client.chat.completions.create(
        model=model,
        messages=messages
      )
    
    result = {
      "message":completion.choices[0].message.content
    }

  logger.info(f"Completion received: {completion.choices[0].message}")

  if completion.choices[0].message.tool_calls:
    logger.info(f"Tool calls detected.")
    logger.info(f"Tool calls: {completion.choices[0].message.tool_calls}")
    result["tool_calls"] = completion.choices[0].message.tool_calls
  else:
    logger.info(f"No tool calls detected.")
    result["tool_calls"] = None

  return result


def call_gpt_single(
    prompt, sysprompt=None, client=openai_client, 
    json_mode=False, model="gpt-4o",
    tools=[] # this is added for signature consistency with call_gpt
  ):
  # same as call_gpt but takes single prompt as input, no tools
  logger.info(f"Calling GPT")
  messages = [{"role": "user", "content": prompt}]
  
  result = call_gpt(
    messages=messages, sysprompt=sysprompt, client=client, json_mode=json_mode, model=model
  )

  return result


def get_tools(sysprompt, tools_collection):
  if "toolset" in sysprompt:
    logger.info(f"Toolset found in sysprompt: {sysprompt['toolset']}")
    tools = []
    tools_names = sysprompt["toolset"]
    for tool_name in tools_names:
      tool = tools_collection.find_one({"function.name": tool_name}, {"_id": 0})
      if not tool:
        raise ValueError(f"Tool {tool_name} not found.")      
      # Validate the tool using the ToolWithContext model
      validated_tool = ToolWithContext(**tool)
      tool_dict = validated_tool.model_dump(exclude_none=True)
      # Remove context parameters before appending to tools list
      if validated_tool.context_parameters:
        tool_dict.pop('context_parameters')
      tools.append(tool_dict)
  else:
    tools = None
  logger.info(f"Tools found in db: {tools}") 
  return tools


def call_llm_and_process_tools(
    new_messages, sysprompt, tools, call_llm_func, 
    tool_handler, tools_collection, 
    function_dictionary,
    json_mode=False,
    context_arguments=None,
    max_chained_tool_calls=10
):
  logger.info("Calling LLM")
      
  llm_result = call_llm_func(
    messages=new_messages, 
    sysprompt=sysprompt["prompt"],
    tools=tools,
    json_mode=json_mode
  )
  logger.info(f"LLM response received: {llm_result['message']}")
  
  n_tries = 0
  while llm_result["tool_calls"] is not None:
    new_messages.append(
      {
        "role":"assistant", 
        "tool_calls":[tool_call.model_dump() for tool_call in llm_result["tool_calls"]]
      }
    ) 
    
    n_tool_calls = len(llm_result["tool_calls"])
    logger.info(f"{n_tool_calls} tool calls detected. Iteration {n_tries}")

    # make sure we don't get stuck in an infinite loop
    if n_tries > max_chained_tool_calls:
      raise ValueError("Too many chained tool calls.")
    n_tries += 1
    
    # iterate over tool calls and append it openai format
    for tool_call in llm_result["tool_calls"]:
      logger.info(f"Calling tool {tool_call.function.name}")
      tool_result = tool_handler(
        name = tool_call.function.name,
        arguments = json.loads(tool_call.function.arguments),
        tools_collection=tools_collection,
        function_dictionary=function_dictionary,
        context_arguments = context_arguments
      )
      logger.info(f"Tool {tool_call.function.name} returned: {tool_result}")
      new_messages.append(
        {
          "tool_call_id": tool_call.id,
          "role":"tool",
          "name": tool_call.function.name,
          "content": str(tool_result),
        }
      )

    # new call with tool results
    logger.info("Calling LLM with tool results.")
    llm_result = call_llm_func(
      messages=new_messages, 
      sysprompt=sysprompt["prompt"],
      tools=tools,
      json_mode=json_mode
    )

  result = {"message":llm_result["message"]}
  return result


def process_chat(
    chat_id: str,
    message_id: str,
    new_message: str,
    chats_collection,
    prompts_collection,
    documents_collection,
    tools_collection,
    sysprompt_id: Optional[str] = None, # used to overwrite the sysprompt id saved in the chat object
    callback_func=None,
    dry_run=False,
    json_mode=False,
    call_llm_func=call_gpt,
    rag_func=perform_postgre_search,
    rag_table_name: str = None,
    persist_rag_results=False,
    context_arguments=None,
    db: Session = Depends(get_db),
    spacy_model=spacy_model,
    function_dictionary=default_function_dictionary,
    skip_word=None, # e.g. "PASS" might mean "don't send message" depending on the prompt
    sysprompt_suffix: Optional[str] = None # this will be added to the end of the sysprompt. Usefull for runtime modifications of the sysprompt
):
  try:

    # Get the chat history
    chat = chats_collection.find_one({"chat_id": chat_id})
    if not chat:
      raise ValueError(f"Chat {chat_id} not found.")

    # Update chat status to in_progress
    old_statuses = chat["statuses"]
    new_statuses = old_statuses + [{"message_id": message_id, "status": "in_progress"}]
    chats_collection.update_one(
      {"chat_id": chat_id}, {"$set": {"statuses": new_statuses}}
    )

    # Find the sysprompt
    if sysprompt_id is None:
      sysprompt_id = chat["sysprompt_id"] # get saved sysprompt id from chat
      if not sysprompt_id:
        logger.error(f"System prompt for chat {chat_id} not found.")
        raise ValueError(f"System prompt for chat {chat_id} not found.")
    
    sysprompt = prompts_collection.find_one({"prompt_id": sysprompt_id})
    if not sysprompt:
      raise ValueError(f"Prompt {sysprompt_id} not found.")
    
    if sysprompt_suffix is not None:
      sysprompt["prompt"] = sysprompt["prompt"] + "\n\n" + sysprompt_suffix

    # check if prompt object includes "toolset"
    tools = get_tools(sysprompt, tools_collection)
    
    # check if the prompt object includes documents that need to be injected to the system prompt
    sysprompt = add_documents_to_sysprompt(sysprompt, documents_collection)
    
    # Perform RAG
    new_message, rag_result = add_rag_results_to_message(
      sysprompt=sysprompt, 
      new_message=new_message, 
      rag_func=rag_func, 
      db=db,
      spacy_model=spacy_model,
      persist_rag_results=persist_rag_results,
      table_name=rag_table_name
    )

    # add new message and update collection
    old_messages = chat["messages"]
    new_messages = old_messages + [{"message_id":"q-"+message_id, "role": "user", "content": new_message, "timestamp": datetime.now()}]
    # note: we add 'q-' to the message_id to differentiate between user and assistant messages part of the same exchange
    
    chats_collection.update_one(
      {"chat_id": chat_id}, {"$set": {"messages": new_messages}}
    )

    if rag_result is not None and not persist_rag_results:
      rag_connecting_prompt = sysprompt.get("documents", {}).get("rag_connecting_prompt", "Related information:")
      new_messages[-1]["content"] = (
        new_messages[-1]["content"] + 
        "\n\n" + 
        rag_connecting_prompt + 
        "\n" + 
        rag_result
      )  # only add rag result after the message has been added to the db

    # call LLM
    if dry_run:
      logger.info("Dry run enabled. Skipping LLM calls.")
      result = {
        "message": "This is a test message."
      }
    else:
      result = call_llm_and_process_tools(
        new_messages=new_messages, 
        sysprompt=sysprompt, 
        tools=tools, 
        call_llm_func=call_llm_func, 
        json_mode=json_mode,
        tool_handler=tool_handler,
        tools_collection=tools_collection,
        context_arguments=context_arguments,
        function_dictionary=function_dictionary
      )

    if skip_word is not None: 
      # check if message is special value meaning "don't send message" was returned
      if result["message"] == skip_word:
        result.pop("message")
    
    # update mongo
    new_statuses = old_statuses + [{"message_id": message_id, "status": "completed"}]
    new_messages = [dict(item) for item in new_messages]
    if new_messages[0]["role"] == "system":
      new_messages.pop(0) # don't save system prompt
    new_messages = new_messages + [{"message_id": message_id, "role": "assistant", "content": result["message"], "timestamp": datetime.now()}]
    chats_collection.update_one(
      {"chat_id": chat_id}, 
      {"$set": {"statuses": new_statuses, "messages": new_messages}}
    )
    logger.info(f"Chat {chat_id} completed successfully.")

    # send messages
    if callback_func is not None:
      logger.info(f"Sending messages for chat {chat_id}.")
      
      session_id = chats_collection.find_one(
        {"chat_id": chat_id}
      )["context_id"]
      
      callback_func(
        result["message"], 
        session_id
      )

      logger.info(f"Message callback sent successfully: {result['message']}")

    return result

  except Exception as e:
    logger.error(f"Error processing chat {chat_id}: {e}")  # TODO update status

