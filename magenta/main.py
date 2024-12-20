from fastapi import FastAPI, HTTPException, status, Depends
import os
import uvicorn
import json
from typing import Annotated
from datetime import timedelta
from contextlib import asynccontextmanager
from sqlalchemy import text
from sqlalchemy.orm import Session

from core import (
    logger, mongo_client, spacy_model, engine,
    tenant_collections, get_db, SLACK_WEBHOOK_URL,
    Token, OAuth2PasswordRequestForm, ACCESS_TOKEN_EXPIRE_MINUTES,
    User, users_collection, authenticate_user, create_access_token,
    get_current_active_user, create_initial_users,
    load_all_functions_in_db, cleanup_mongo,
    create_postgres_extensions, send_slack_message
)
from routes import (
    prompts_router, documents_router, chats_router,
    tools_router, tenants_router
)
from services import load_prompts_from_files, load_documents_from_files

os.makedirs("temp", exist_ok=True) # create temp directory for file uploads

ENV = os.getenv('ENV', 'DEV')

# startup and shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
	logger.info("Application server started.")
	# load default data from files
	await create_postgres_extensions(get_db)
	await load_prompts_from_files(tenant_collections.get_collections_list("prompts"), dir="data/prompts")
	await create_initial_users(users_collection, dir="data/users")
	await load_all_functions_in_db(tenant_collections.get_collections_list("tools"))
	await load_documents_from_files(
		documents_collections=tenant_collections.collections["documents"], # dict tenant_id:collection_object
		dir="data/documents/instructions",
		model=spacy_model
	)
	# remove possible dangling data from previous test runs
	await cleanup_mongo(tenant_collections.get_collections_list("tools"),[{"function.name":{"$in":["test_tool", "duplicate_tool", "updated_test_tool"]}}])
	await cleanup_mongo(tenant_collections.get_collections_list("documents"),[{"name":{"$in":["test_document", "test-document"]}}])
	await cleanup_mongo(tenant_collections.get_collections_list("chats"),[{"chat_id":{"$in":["test_rag_chat", "test_user"]}}])
	await cleanup_mongo(tenant_collections.get_collections_list("chats"),[{"context_id":{"$in":["test_session_id"]}}])
	await cleanup_mongo(tenant_collections.get_collections_list("prompts"),[{"name":"test_prompt"}])
	await cleanup_mongo([tenant_collections.tenants_collection], [{"tenant_id":"test_tenant"}])
	if ENV != "DEV":
		await send_slack_message(SLACK_WEBHOOK_URL, "Application server started.")
	yield
	# close all mongo connections
	mongo_client.close()
	# close SQLAlchemy engine
	engine.dispose()
	logger.info("Application server stopped.")
	if ENV != "DEV":
		await send_slack_message(SLACK_WEBHOOK_URL, "Application server stopped.")


app = FastAPI(lifespan=lifespan)
app.include_router(chats_router)
app.include_router(prompts_router)
app.include_router(tools_router)
app.include_router(documents_router)
app.include_router(tenants_router)


# some key routes
@app.get("/")
async def read_root():
	return {"message": "Magenta LLM agent framework"}


@app.get("/healthcheck")
async def healthcheck():
	return {"status": "ok"}


@app.get("/postgres_status")
async def postgres_status(db: Session = Depends(get_db)):
	try:
		db.execute(text("SELECT 1"))
		return {"postgres": "healthy"}
	except Exception as e:
		logger.error(f"Error connecting to PostgreSQL: {e}")
		return {"postgres": "unhealthy", "error": str(e)}


@app.get("/mongo_status")
async def mongo_status():
	try:
		health = mongo_client.server_info()
		return {"mongo": "healthy" if health else "unhealthy"}
	except Exception as e:
		logger.error(f"Error connecting to MongoDB: {e}")
		return {"mongo": "unhealthy", "error": str(e)}


# token and user endpoints
@app.post("/token")
async def login_for_access_token(
	form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
	user = authenticate_user(users_collection, form_data.username, form_data.password)
	if not user:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Incorrect username or password",
			headers={"WWW-Authenticate": "Bearer"}
		)
	access_token = create_access_token(
		data={"sub": user.username}, expires_delta=ACCESS_TOKEN_EXPIRE_MINUTES
	)
	return Token(access_token=access_token, token_type="bearer")


@app.get("/users/me/", response_model=User)
async def read_users_me(
	current_user: Annotated[User, Depends(get_current_active_user)],
):
	return current_user


if __name__ == "__main__":
	logger.info("Starting application server.")
	uvicorn.run(app, host="0.0.0.0", port=8000)
