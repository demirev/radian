from fastapi.testclient import TestClient
from main import app

# client = ExternalClient("http://localhost:8000") # for local testing
client = TestClient(app)

# analysis endpoints -----------------------------------------------
def test_create_get_and_delete_analysis_session():
	# Create analysis session
	create_response = client.post("/analysis/", params={
		"context_id": "test_context",
		"tenant_id": "test_tenant",
		"sysprompt_id": "test_prompt"
	})
	assert create_response.status_code == 200
	
	session_id = create_response.json()["session_id"]
	assert create_response.json()["context_id"] == "test_context"
	assert create_response.json()["tenant_id"] == "test_tenant"
	assert create_response.json()["sysprompt_id"] == "test_prompt"
	
	# List analysis sessions
	list_response = client.get("/analysis/")
	assert list_response.status_code == 200
	assert isinstance(list_response.json(), list)
	
	# List with filters
	filtered_response = client.get("/analysis/", params={
		"context_id": "test_context",
		"tenant_id": "test_tenant"
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
		"context_id": "test_context"
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
	
	# Clean up
	client.delete(f"/analysis/{session_id}")


def test_analysis_session_code():
	# Create session first
	session = client.post("/analysis/", params={
		"context_id": "test_context"
	}).json()
	session_id = session["session_id"]
	
	# Add code snippet
	code_pair = {
		"input": {
			"code_snippet": "def test(): pass",
			"language": "python",
			"file_path": "test.py"
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
