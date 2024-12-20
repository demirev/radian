import os
import json
import requests
import time
from datetime import datetime
from fpdf import FPDF
from fastapi.testclient import TestClient
from main import app
from core.security import create_access_token
from datetime import datetime, timedelta
from core.utils import send_slack_message_sync
from core.config import SLACK_WEBHOOK_URL
import pytest


env = os.getenv('ENV', 'DEV')


if env not in ['DEV', 'TEST', 'STAGING', 'PROD']:
  raise ValueError("Invalid environment. Please set ENV to DEV, TEST, STAGING, or PROD")


# Add delay to allow for db cleanup tasks to complete
print("Waiting for 10 seconds before starting tests...")
time.sleep(10)
print("Starting tests now.")


class ExternalClient:
  def __init__(self, base_url):
    self.base_url = base_url

  def get(self, url, **kwargs):
    return requests.get(self.base_url + url, **kwargs)

  def post(self, url, **kwargs):
    if 'json' in kwargs:
      kwargs['data'] = json.dumps(kwargs.pop('json'))
      kwargs['headers'] = kwargs.get('headers', {})
      kwargs['headers']['Content-Type'] = 'application/json'
    return requests.post(self.base_url + url, **kwargs)

  def put(self, url, **kwargs):
    if 'json' in kwargs:
      kwargs['data'] = json.dumps(kwargs.pop('json'))
      kwargs['headers'] = kwargs.get('headers', {})
      kwargs['headers']['Content-Type'] = 'application/json'
    return requests.put(self.base_url + url, **kwargs)

  def delete(self, url, **kwargs):
    return requests.delete(self.base_url + url, **kwargs)


def get_test_token(username: str = "test_user"):
  # Create a test token
  access_token = create_access_token(data={"sub": username})
  return access_token


def create_simple_pdf(filename, text = "This is a simple test PDF"):
  pdf = FPDF()
  pdf.add_page()
  pdf.set_font("Arial", size=12)
  pdf.cell(200, 10, txt=text, ln=1, align="C")
  pdf.output(filename)


# client = ExternalClient("http://localhost:8000") # for local testing
client = TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def send_test_summary(request):
  yield
  # This code will run after all tests have completed and send a summary to Slack (if not in DEV)
  terminalreporter = request.config.pluginmanager.get_plugin("terminalreporter")
  passed = len([rep for rep in terminalreporter.stats.get('passed', []) if rep.when == 'call'])
  failed = len([rep for rep in terminalreporter.stats.get('failed', []) if rep.when == 'call'])
  skipped = len([rep for rep in terminalreporter.stats.get('skipped', []) if rep.when == 'call'])
  total = passed + failed + skipped

  summary = f"""
  Test Summary:
  Total tests: {total}
  Passed: {passed}
  Failed: {failed}
  Skipped: {skipped}
  """

  env = os.getenv('ENV', 'DEV')
  message = f"Test results for environment: {env}\n{summary}"

  # Send the message to Slack
  if env != "DEV":
    success = send_slack_message_sync(SLACK_WEBHOOK_URL, message)
    if success:
      print("Test summary sent to Slack successfully.")
    else:
      print("Failed to send test summary to Slack.")


# security endpoints -----------------------------------------------
def test_read_users_me_authenticated():
  token = get_test_token()
  headers = {"Authorization": f"Bearer {token}"}
  response = client.get("/users/me/", headers=headers)
  assert response.status_code == 200
  data = response.json()
  assert data["username"] == "test_user"


def test_read_users_me_unauthorized():
  response = client.get("/users/me/")
  assert response.status_code == 401
  assert response.json() == {"detail": "Not authenticated"}


def test_read_users_me_invalid_token():
  headers = {"Authorization": "Bearer invalid_token"}
  response = client.get("/users/me/", headers=headers)
  assert response.status_code == 401
  assert response.json() == {"detail": "Could not validate credentials"}


# general endpoints -----------------------------------------------
def test_postgres_healthcheck():
  response = client.get("/postgres_status")
  assert response.status_code == 200
  json_response = response.json()
  assert json_response["postgres"] == "healthy"


def test_mongo_healthcheck():
  response = client.get("/mongo_status")
  assert response.status_code == 200
  json_response = response.json()
  assert json_response["mongo"] == "healthy"


def test_healthcheck():
  response = client.get("/healthcheck")
  assert response.status_code == 200
  json_response = response.json()
  assert json_response["status"] == "ok"


# chat endpoints -----------------------------------------------
def test_create_get_and_delete_chat():
  # create
  create_response = client.post("/chats/create", params={
    "chat_id": "test_user",
    "context_id": "test_context",
    "agent": "borrower_assistant",
    "description": "Test description"
  })
  assert create_response.status_code == 200
  
  chat_id = create_response.json()["chat_id"]
  assert create_response.json()["context_id"] == "test_context"
  assert create_response.json()["agent"] == "borrower_assistant"
  
  # list
  list_response = client.get("/chats/")
  assert list_response.status_code == 200
  assert isinstance(list_response.json(), list)

  # list with agent filter
  list_response = client.get("/chats/?agent=borrower_assistant")
  assert list_response.status_code == 200
  assert isinstance(list_response.json(), list)
  assert all([chat["agent"] == "borrower_assistant" for chat in list_response.json()])

  # get
  get_response = client.get(f"/chats/{chat_id}")
  assert get_response.status_code == 200
  assert get_response.json()["chat_id"] == chat_id

  # delete
  delete_response = client.delete(f"/chats/{chat_id}")
  assert delete_response.status_code == 200
  assert delete_response.json()["message"] == "Chat deleted successfully"


def test_message_sending_endpoints():
  # First create a chat to send a message to
  create_chat_response = client.post("/chats/create", params={
    "chat_id": "test_user",
    "context_id": "test_context"
  })
  chat_id = create_chat_response.json()["chat_id"]

  # send a message
  send_response = client.post(f"/chats/{chat_id}/send", params={
    "chat_id": chat_id,
    "message": "Test message",
    "dry_run": True # always dry run this test
  })
  message_id = send_response.json()["task_id"]
  assert send_response.status_code == 200
  assert send_response.json()["status"] == "pending"

  # list all messages
  list_messages_response = client.get(f"/chats/{chat_id}/messages")
  assert list_messages_response.status_code == 200
  assert isinstance(list_messages_response.json(), list)

  # get chat status
  get_chat_status_response = client.get(f"/chats/{chat_id}/status")
  assert get_chat_status_response.status_code == 200
  assert "task_id" in get_chat_status_response.json()
  assert "status" in get_chat_status_response.json()

  # get message status
  get_message_status_response = client.get(f"/chats/{chat_id}/messages/{message_id}/status")
  assert get_message_status_response.status_code == 200
  assert get_message_status_response.json()["task_id"] == message_id

  # get a message
  get_message_response = client.get(f"/chats/{chat_id}/messages/{message_id}")
  assert get_message_response.status_code == 200
  assert get_message_response.json()["message_id"] == message_id
  
  # delete a message
  delete_message_response = client.delete(f"/chats/{chat_id}/messages/{message_id}")
  assert delete_message_response.status_code == 200
  assert delete_message_response.json()["message"] == "Message deleted successfully"

  # delete the chat to clean up
  delete_chat_response = client.delete(f"/chats/{chat_id}")
  assert delete_chat_response.status_code == 200
  assert delete_chat_response.json()["message"] == "Chat deleted successfully"


def test_tool_calling():
  # check that the tool is available
  roll_dice_tool = client.get("/tools/?name=roll_dice")
  assert roll_dice_tool.status_code == 200
  assert "tool_id" in roll_dice_tool.json()[0]
  assert "function" in roll_dice_tool.json()[0]
  assert "name" in roll_dice_tool.json()[0]["function"]
  assert roll_dice_tool.json()[0]["function"]["name"] == "roll_dice"

  # check that agent has access to tool
  dice_roller_agent = client.get("/prompts/?prompt_id=diceroller")
  assert dice_roller_agent.status_code == 200
  assert "toolset" in dice_roller_agent.json()[0]
  assert len(dice_roller_agent.json()[0]["toolset"]) > 0
  assert any([tool == "roll_dice" for tool in dice_roller_agent.json()[0]["toolset"]])

  # create chat
  create_chat_response = client.post("/chats/create", params={
    "chat_id": "test_user",
    "context_id": "test_context",
    "agent": "test_agent" # this agent has access to roll_dice tool
  })
  assert create_chat_response.status_code == 200
  chat_id = create_chat_response.json()["chat_id"]

  # send message to call tool
  if env != 'DEV':
    send_response = client.post(f"/chats/{chat_id}/send", params={
      "chat_id": chat_id,
      "message": "roll_dice 2d6",
      "dry_run": False
    })
    assert send_response.status_code == 200
    assert send_response.json()["status"] == "pending"

    # wait for status to change to finished
    get_chat_status_response = client.get(f"/chats/{chat_id}/status")
    max_retries = 10
    retries = 0
    while get_chat_status_response.json()["status"] != "completed" and retries < max_retries:
      time.sleep(0.5)
      retries += 1
      get_chat_status_response = client.get(f"/chats/{chat_id}/status") 
      assert get_chat_status_response.status_code == 200
    if retries == max_retries:
      raise TimeoutError("Task did not finish in time")
    assert get_chat_status_response.json()["status"] == "completed"

    # get chat result
    messages_response = client.get(f"/chats/{chat_id}/messages", params={"no_internal": False})
    assert messages_response.status_code == 200
    assert any([message["role"] == "tool" for message in messages_response.json()])


def test_augmented_retrieval():
  # check that the documents are available
  blue_team_doc = client.get("/documents/?name=test_blue_team_password.pdf")
  assert blue_team_doc.status_code == 200
  assert blue_team_doc.json()[0]["status"] == "completed"
  
  red_team_doc = client.get("/documents/?name=test_red_team_password.pdf")
  assert red_team_doc.status_code == 200
  assert red_team_doc.json()[0]["status"] == "completed"

  # check that agent has access to documents
  password_teller_agent = client.get("/prompts/?prompt_id=passwordteller")
  assert password_teller_agent.status_code == 200
  assert "documents" in password_teller_agent.json()[0]
  assert "rag_documents" in password_teller_agent.json()[0]["documents"]
  assert len(password_teller_agent.json()[0]["documents"]["rag_documents"]) > 0
  assert any([doc["document_id"] == "test_blue_team" or doc["document_id"] == "test_red_team" for doc in password_teller_agent.json()[0]["documents"]["rag_documents"]])
  assert "context_documents" in password_teller_agent.json()[0]["documents"]
  assert len(password_teller_agent.json()[0]["documents"]["context_documents"]) > 0
  assert any([doc["document_id"] == "test_blue_team" or doc["document_id"] == "test_red_team" for doc in password_teller_agent.json()[0]["documents"]["context_documents"]])

  # create chat
  create_chat_response = client.post("/chats/create", params={
    "chat_id": "test_rag_chat",
    "context_id": "test_context",
    "agent": "test_rag_agent" # this agent has access to test_blue_team and test_red_team documents
  })
  assert create_chat_response.status_code == 200
  chat_id = create_chat_response.json()["chat_id"]

  # send message to query blue team's password
  if env != 'DEV':
    send_response = client.post(f"/chats/{chat_id}/send", params={
      "chat_id": chat_id,
      "message": "What is the password of the BLUE team?",
      "dry_run": False
    })
    assert send_response.status_code == 200
    assert send_response.json()["status"] == "pending"
    message_id = send_response.json()["task_id"]

    # wait for status to change to finished
    get_chat_status_response = client.get(f"/chats/{chat_id}/status")
    max_retries = 10
    retries = 0
    while get_chat_status_response.json()["status"] != "completed" and retries < max_retries:
      time.sleep(0.5)
      retries += 1
      get_chat_status_response = client.get(f"/chats/{chat_id}/status")
      assert get_chat_status_response.status_code == 200
    if retries == max_retries:
      raise TimeoutError("Task did not finish in time")
    assert get_chat_status_response.json()["status"] == "completed"

    # get chat result
    messages_response = client.get(f"/chats/{chat_id}/messages/{message_id}")
    assert messages_response.status_code == 200
    assert "ILikeMuffins" in messages_response.json()["content"]

  # send message to query red team's password
  if env != 'DEV':
    send_response = client.post(f"/chats/{chat_id}/send", params={
      "chat_id": chat_id,
      "message": "What is the RED team password? Is it 133gggA#?",
      "dry_run": False
    })
    assert send_response.status_code == 200
    assert send_response.json()["status"] == "pending"
    message_id = send_response.json()["task_id"]

    # wait for status to change to finished
    get_chat_status_response = client.get(f"/chats/{chat_id}/status")
    max_retries = 10
    retries = 0
    while get_chat_status_response.json()["status"] != "completed" and retries < max_retries:
      time.sleep(0.5)
      retries += 1
      get_chat_status_response = client.get(f"/chats/{chat_id}/status")
      assert get_chat_status_response.status_code == 200
    if retries == max_retries:
      raise TimeoutError("Task did not finish in time")
    assert get_chat_status_response.json()["status"] == "completed"

    # get chat result
    messages_response = client.get(f"/chats/{chat_id}/messages/{message_id}")
    assert messages_response.status_code == 200
    assert "133gggA#" in messages_response.json()["content"]
  
  # delete the chat to clean up
  delete_chat_response = client.delete(f"/chats/{chat_id}")
  assert delete_chat_response.status_code == 200


# prompt endpoints -----------------------------------------------
def test_create_get_update_and_delete_prompt():
	# create a prompt
	create_response = client.post("/prompts/create", params={
		"name": "test_prompt",
		"type": "system",
		"prompt": "This is a test prompt."
	})
	assert create_response.status_code == 200

	prompt_id = create_response.json()["task_id"]
	assert create_response.json()["status"] == "created"
	assert create_response.json()["type"] == "prompt creation"
	
	# list prompts
	list_response = client.get("/prompts/")
	assert list_response.status_code == 200
	assert isinstance(list_response.json(), list)

	# list prompts with name filter
	list_response = client.get("/prompts/?name=test_prompt")
	assert list_response.status_code == 200
	assert isinstance(list_response.json(), list)
	assert all([prompt["name"] == "test_prompt" for prompt in list_response.json()])

	# get the created prompt
	get_response = client.get(f"/prompts/{prompt_id}")
	assert get_response.status_code == 200
	assert get_response.json()["prompt_id"] == prompt_id

	# update part of the prompt
	update_response = client.put(
    f"/prompts/{prompt_id}", 
    params={
      "description": "This is an updated description"
    }, 
    json={
      "toolset": ["tool1", "tool2"]
    }
  )
	assert update_response.status_code == 200
	assert update_response.json()["prompt_id"] == prompt_id
	assert update_response.json()["description"] == "This is an updated description"
	assert update_response.json()["toolset"] == ["tool1", "tool2"]
	assert update_response.json()["name"] == "test_prompt"  # Ensure other fields remain unchanged
	assert update_response.json()["type"] == "system"
	assert update_response.json()["prompt"] == "This is a test prompt."

	# get the updated prompt to verify changes
	get_updated_response = client.get(f"/prompts/{prompt_id}")
	assert get_updated_response.status_code == 200
	assert get_updated_response.json()["description"] == "This is an updated description"
	assert get_updated_response.json()["toolset"] == ["tool1", "tool2"]

	# try to create a duplicate prompt
	create_response_duplicate = client.post("/prompts/create", params={
		"name": "test_prompt",
		"type": "system",
		"prompt": "This is another test prompt."
	})
	assert create_response_duplicate.status_code == 400
	assert create_response_duplicate.json()["detail"] == "Prompt name test_prompt already exists"

	# delete the created prompt
	delete_response = client.delete(f"/prompts/{prompt_id}")
	assert delete_response.status_code == 200
	assert delete_response.json()["message"] == "Prompt deleted successfully"

	# try to get the deleted prompt
	get_response = client.get(f"/prompts/{prompt_id}")
	assert get_response.status_code == 404
	assert get_response.json()["detail"] == "Prompt not found"


# document endpoints -----------------------------------------------
def test_list_documents():
  response = client.get("/documents/")
  assert response.status_code == 200
  assert isinstance(response.json(), list)


def test_upload_get_and_delete_document():
  # create a temporary PDF file for the upload test
  file_path = "test.pdf"
  create_simple_pdf(file_path)
  
  with open(file_path, "rb") as f:
    files = {"file": ("test.pdf", f, "application/pdf")}
    response = client.post("/documents/upload", params={
      "name": "test_document",
      "type": "report",
      "metadata": json.dumps({"author": "test_author"})
    }, files=files)

  os.remove(file_path)

  assert response.status_code == 200
  document_id = response.json()["task_id"]
  assert response.json()["status"] == "pending"
  assert response.json()["type"] == "document upload"

  # get document upload status
  status_response = client.get(f"/documents/{document_id}/status")
  assert status_response.status_code == 200
  assert status_response.json()["task_id"] == document_id

  # Wait for the task to complete
  max_retries = 10
  for _ in range(max_retries):
    status_response = client.get(f"/documents/{document_id}/status")
    if status_response.json()["status"] == "completed":
        break
    time.sleep(1)
  else:
    assert False, "Task did not complete in time"

  # get the uploaded document
  get_response = client.get(f"/documents/{document_id}")
  assert get_response.status_code == 200
  assert get_response.json()["document_id"] == document_id
  assert get_response.json()["name"] == "test_document"

  # perform semantic search
  semantic_response = client.post("/documents/search", params={
    "query": "test query",
    "limit": 1
  })

  assert semantic_response.status_code == 200
  results = semantic_response.json()
  assert isinstance(results, list)
  assert len(results) > 0
  assert "text" in results[0]
  assert "similarity" in results[0]
  assert "name" in results[0]

  # delete the uploaded document (clean up)
  delete_response = client.delete(f"/documents/{document_id}")
  assert delete_response.status_code == 200
  assert delete_response.json()["message"] == "Document deleted successfully"

  # try to get the deleted document
  get_response = client.get(f"/documents/{document_id}")
  assert get_response.status_code == 404
  assert get_response.json()["detail"] == "Document not found"


def test_upload_non_pdf_document():
  # create a temporary non-PDF file for the upload test
  file_path = "test.txt"
  with open(file_path, "w") as f:
    f.write("test text content")

  with open(file_path, "rb") as f:
    files = {"file": ("test.txt", f, "text/plain")}
    response = client.post("/documents/upload", params={
      "name": "test_document",
      "type": "report",
      "metadata": json.dumps({"author": "test_author"})
    }, files=files)

  os.remove(file_path)

  assert response.status_code == 400
  #assert response.json()["detail"] == "Only PDF files are supported"


# tools endpoints -----------------------------------------------
def test_create_get_update_and_delete_tool():
  # Create a tool
  create_response = client.post(
    "/tools/create", 
    params={
      "name": "test_tool",
      "description": "This is a test tool"
    },
    json={
      "parameters": {
        "param1": {"type": "string", "description": "A test parameter"},
        "param2": {"type": "integer", "description": "Another test parameter"}
      },
      "required": ["param1"]
    }
  )
  assert create_response.status_code == 200

  tool_id = create_response.json()["tool_id"]
  
  # List tools
  list_response = client.get("/tools/")
  assert list_response.status_code == 200
  assert isinstance(list_response.json(), list)

  # Get the created tool
  get_response = client.get(f"/tools/{tool_id}")
  assert get_response.status_code == 200
  assert get_response.json()["tool_id"] == tool_id

  # Update the created tool
  update_response = client.put(
    f"/tools/{tool_id}", 
    params={
      "name": "updated_test_tool",
      "description": "This is an updated test tool"
    },
    json={
      "parameters": {
        "param1": {"type": "string", "description": "Updated parameter"},
        "param2": {"type": "integer", "description": "Updated parameter"},
        "param3": {"type": "string", "description": "New parameter"}
      },
      "required": ["param1", "param3"]
    }
  )
  assert update_response.status_code == 200

  # Verify the update
  get_updated_response = client.get(f"/tools/{tool_id}")
  assert get_updated_response.status_code == 200
  assert get_updated_response.json()["tool_id"] == tool_id
  assert get_updated_response.json()["function"]["name"] == "updated_test_tool"
  assert get_updated_response.json()["function"]["description"] == "This is an updated test tool"
  assert "param3" in get_updated_response.json()["function"]["parameters"]["properties"]

  # Delete the created tool
  delete_response = client.delete(f"/tools/{tool_id}")
  assert delete_response.status_code == 200
  assert delete_response.json()["message"] == "Tool deleted successfully"

  # Try to get the deleted tool
  get_deleted_response = client.get(f"/tools/{tool_id}")
  assert get_deleted_response.status_code == 404
  assert get_deleted_response.json()["detail"] == "Tool not found"


def test_tool_name_exists():
  # Create a tool
  create_response = client.post(
    "/tools/create", 
    params={
      "name": "duplicate_tool",
      "description": "This is a duplicate test tool"
    },
    json={
      "parameters": {
        "param1": {"type": "string", "description": "A test parameter"}
      },
      "required": ["param1"]
    }
  )
  assert create_response.status_code == 200
  
  # Create another tool with the same name
  create_response_duplicate = client.post(
    "/tools/create", 
    params={
      "name": "duplicate_tool",
      "description": "This is another test tool"
    },
    json={
      "parameters": {
        "param1": {"type": "string", "description": "A test parameter"}
      },
      "required": ["param1"]
    }
  )
  assert create_response_duplicate.status_code == 400

  # Clean up
  tool_id = create_response.json()["tool_id"]
  delete_response = client.delete(f"/tools/{tool_id}")
  assert delete_response.status_code == 200


def test_tool_required_parameters():
  # Try to create a tool without required parameters
  create_response = client.post(
    "/tools/create", 
    params={
      "name": "incomplete_tool",
      "description": "This is an incomplete test tool"
    },
    json={
      "parameters": {
        "param1": {"type": "string", "description": "A test parameter"}
      },
      "required": []
    })
  assert create_response.status_code == 400
