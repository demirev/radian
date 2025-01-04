from fastapi.testclient import TestClient
from app.main import app
import requests
import json
import os
import time


env = os.getenv('ENV', 'DEV')


if env not in ['DEV', 'TEST', 'STAGING', 'PROD']:
  raise ValueError("Invalid environment. Please set ENV to DEV, TEST, STAGING, or PROD")


# Add delay to allow for db cleanup tasks to complete
print("Waiting for 5 seconds before starting tests...")
time.sleep(5)
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


# client = ExternalClient("http://localhost:8000") # for local testing
# client = TestClient(app)
client = ExternalClient("http://radian:8000")  # Use the service name from docker-compose.yml

# analysis endpoints -----------------------------------------------
def test_create_get_and_delete_analysis_session():
	# Create analysis session
	create_response = client.post("/analysis/", params={
		"context_id": "test_context",
		"tenant_id": "default",
		"sysprompt_id": "radian0",
		"title": "Test Session",
		"description": "Test Description"
	})
	assert create_response.status_code == 200
	
	session_id = create_response.json()["session_id"]
	assert create_response.json()["context_id"] == "test_context"
	assert create_response.json()["title"] == "Test Session"
	assert create_response.json()["description"] == "Test Description"
	
	# Test PUT endpoint to update title and description
	update_response = client.put(f"/analysis/{session_id}", params={
		"title": "Updated Title",
		"description": "Updated Description"
	})
	assert update_response.status_code == 200
	assert update_response.json()["title"] == "Updated Title"
	assert update_response.json()["description"] == "Updated Description"
	
	# List analysis sessions
	list_response = client.get("/analysis/")
	assert list_response.status_code == 200
	assert isinstance(list_response.json(), list)
	
	# List with filters
	filtered_response = client.get("/analysis/", params={
		"context_id": "test_context",
		"tenant_id": "default"
	})
	assert filtered_response.status_code == 200
	assert all([session["context_id"] == "test_context" for session in filtered_response.json()])
	
	# Get specific session
	get_response = client.get(f"/analysis/{session_id}")
	assert get_response.status_code == 200
	assert get_response.json()["session_id"] == session_id
	
	# Delete session
	delete_response = client.delete(f"/analysis/{session_id}")
	assert delete_response.status_code == 200
	assert delete_response.json()["status"] == "success"
	
	# Verify deletion
	get_deleted_response = client.get(f"/analysis/{session_id}")
	assert get_deleted_response.status_code == 404


def test_analysis_session_messages():
	# Create session first
	session = client.post("/analysis/", params={
		"context_id": "test_context",
		"tenant_id": "default",
		"sysprompt_id": "radian0"
	}).json()
	session_id = session["session_id"]
	
	# Add message
	message = "Test analysis message"
	send_response = client.post(
		f"/analysis/{session_id}/messages",
		params={
			"message": message,
			"dry_run": True
		}
	)
	assert send_response.status_code == 200
	message_id = send_response.json()["task_id"]
	
	# Add a second message
	second_message = "Second test message"
	second_response = client.post(
		f"/analysis/{session_id}/messages",
		params={
			"message": second_message,
			"dry_run": True
		}
	)
	assert second_response.status_code == 200
	second_message_id = second_response.json()["task_id"]
	
	# List messages
	list_response = client.get(f"/analysis/{session_id}/messages")
	assert list_response.status_code == 200
	assert isinstance(list_response.json(), list)
	assert len(list_response.json()) > 0
	
	# Get specific message
	get_response = client.get(f"/analysis/{session_id}/messages/{message_id}")
	assert get_response.status_code == 200
	assert get_response.json()["message_id"] == message_id
	assert get_response.json()["content"] == message
	
	# Test message status endpoints
	# Get single message status
	status_response = client.get(f"/analysis/{session_id}/messages/status", params={
		"message_ids": [message_id]
	})
	assert status_response.status_code == 200
	assert message_id in status_response.json()
	assert "status" in status_response.json()[message_id]
	
	# Get latest message status (no message_ids parameter)
	latest_status_response = client.get(f"/analysis/{session_id}/messages/status")
	assert latest_status_response.status_code == 200
	assert len(latest_status_response.json()) == 1
	assert "status" in list(latest_status_response.json().values())[0]
	
	# Test filtering by message_id
	filtered_by_id_response = client.get(
		f"/analysis/{session_id}/messages",
		params={"since_message_id": message_id}
	)
	assert filtered_by_id_response.status_code == 200
	filtered_messages = filtered_by_id_response.json()
	assert len(filtered_messages) == 1
	assert filtered_messages[0]["message_id"] == second_message_id
	
	# Test filtering with non-existent message_id
	non_existent_response = client.get(
		f"/analysis/{session_id}/messages",
		params={"since_message_id": "non_existent_id"}
	)
	assert non_existent_response.status_code == 404
	
	# Test filtering by timestamp
	first_message_timestamp = client.get(f"/analysis/{session_id}/messages/{message_id}").json()["timestamp"]
	filtered_by_time_response = client.get(
		f"/analysis/{session_id}/messages",
		params={"since_timestamp": first_message_timestamp}
	)
	assert filtered_by_time_response.status_code == 200
	time_filtered_messages = filtered_by_time_response.json()
	assert len(time_filtered_messages) == 1
	assert time_filtered_messages[0]["message_id"] == second_message_id
	
	# Clean up
	client.delete(f"/analysis/{session_id}")


def test_analysis_session_code():
	# Create session first
	session = client.post("/analysis/", params={
		"context_id": "test_context",
		"tenant_id": "default",
		"sysprompt_id": "radian0"
	}).json()
	session_id = session["session_id"]
	
	# Add code snippet
	code_pair = {
		"input": {
			"type": "execution",
			"code_snippet": "def test(): pass",
			"language": "py"
		},
		"output": {
			"response": "Test passed",
			"status": "success"
		}
	}
	
	send_response = client.post(
		f"/analysis/{session_id}/code",
		params={"dry_run": True},
		json=code_pair
	)
	assert send_response.status_code == 200
	code_message_id = send_response.json()["task_id"]
	
	# List code snippets
	list_response = client.get(f"/analysis/{session_id}/code")
	assert list_response.status_code == 200
	assert isinstance(list_response.json(), list)
	assert len(list_response.json()) > 0
	
	# Get specific code snippet
	get_response = client.get(f"/analysis/{session_id}/code/{code_message_id}")
	assert get_response.status_code == 200
	assert get_response.json()["message_id"] == code_message_id
	assert get_response.json()["code_pair"] == code_pair
	
	# Clean up
	client.delete(f"/analysis/{session_id}")


def test_analysis_session_not_found():
	non_existent_id = "non_existent_session"
	
	# Try to get non-existent session
	get_response = client.get(f"/analysis/{non_existent_id}")
	assert get_response.status_code == 404
	
	# Try to get messages from non-existent session
	messages_response = client.get(f"/analysis/{non_existent_id}/messages")
	assert messages_response.status_code == 404
	
	# Try to get code from non-existent session
	code_response = client.get(f"/analysis/{non_existent_id}/code")
	assert code_response.status_code == 404


def test_environment_file_operations():
	# Create analysis session first
	session = client.post("/analysis/", params={
		"context_id": "test_context",
		"tenant_id": "default",
		"sysprompt_id": "radian0"
	}).json()
	session_id = session["session_id"]
	
	# Test creating environment file
	env_data = {
		"session_id": session_id,
		"context_id": session["context_id"],
		"tenant_id": "default",
		"env_file": "SGVsbG8gV29ybGQ="  # base64 encoded "Hello World"
	}
	
	# no need to directly create environment file as it's done in analysis.py
	update_response = client.put(
		f"/environments/{session_id}",
		json=env_data
	)
	assert update_response.status_code == 200

	# Test getting environment file
	get_response = client.get(f"/environments/{session_id}")
	assert get_response.status_code == 200
	assert get_response.json()["env_file"] == "SGVsbG8gV29ybGQ="
	assert get_response.json()["context_id"] == session["context_id"]
	assert get_response.json()["tenant_id"] == "default"
	
	# Test updating environment file
	updated_env_data = {
		"session_id": session_id,
		"context_id": session["context_id"],
		"tenant_id": "default",
		"env_file": "VXBkYXRlZCBFbnZpcm9ubWVudA=="  # base64 encoded "Updated Environment"
	}
	
	update_response = client.put(
		f"/environments/{session_id}",
		json=updated_env_data
	)
	assert update_response.status_code == 200
	assert update_response.json()["context_id"] == session["context_id"]
	assert update_response.json()["tenant_id"] == "default"
	# Don't check env_file immediately as it's processed in background
	
	# Add small delay to allow background task to complete
	time.sleep(1)
	
	# Verify update
	get_updated_response = client.get(f"/environments/{session_id}")
	assert get_updated_response.status_code == 200
	assert get_updated_response.json()["env_file"] == "VXBkYXRlZCBFbnZpcm9ubWVudA=="
	
	# Test deleting environment file
	delete_response = client.delete(f"/environments/{session_id}")
	assert delete_response.status_code == 200
	assert delete_response.json()["status"] == "success"
	
	# Verify deletion
	get_deleted_response = client.get(f"/environments/{session_id}")
	assert get_deleted_response.status_code == 404
	
	# Clean up analysis session
	client.delete(f"/analysis/{session_id}")


def test_environment_error_cases():
	# Test with non-existent session
	non_existent_id = "non_existent_session"
	env_data = {
		"session_id": non_existent_id,
		"context_id": "test_context",
		"tenant_id": "default",
		"env_file": "SGVsbG8gV29ybGQ="
	}
	
	# Try to create environment for non-existent session
	create_response = client.post(
		f"/environments/{non_existent_id}",
		json=env_data
	)
	assert create_response.status_code == 404
	
	# Create a valid session for remaining tests
	session = client.post("/analysis/", params={
		"context_id": "test_context",
		"tenant_id": "default",
		"sysprompt_id": "radian0"
	}).json()
	session_id = session["session_id"]
	
	# Test invalid base64 encoding
	invalid_env_data = {
		"session_id": session_id,
		"context_id": session["context_id"],
		"tenant_id": "default",
		"env_file": "This is not base64!!@#$"  # Invalid base64 string
	}
	
	invalid_response = client.post(
		f"/environments/{session_id}",
		json=invalid_env_data
	)
	assert invalid_response.status_code == 400
	
	# Test duplicate creation
	# First create a valid environment
	client.post(
		f"/environments/{session_id}",
		json={
			"session_id": session_id,
			"context_id": session["context_id"],
			"tenant_id": "default",
			"env_file": "SGVsbG8gV29ybGQ="
		}
	)
	
	# Try to create another one
	duplicate_response = client.post(
		f"/environments/{session_id}",
		json={
			"session_id": session_id,
			"context_id": session["context_id"],
			"tenant_id": "default",
			"env_file": "SGVsbG8gV29ybGQ="
		}
	)
	assert duplicate_response.status_code == 400
	
	# Clean up
	client.delete(f"/environments/{session_id}")
	client.delete(f"/analysis/{session_id}")
