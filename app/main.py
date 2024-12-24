from fastapi import FastAPI
import os
import uvicorn
from contextlib import asynccontextmanager
from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from magenta.core.security import (
  authenticate_user, get_current_active_user, create_access_token, 
  create_initial_users, users_collection, 
  Token, User, ACCESS_TOKEN_EXPIRE_MINUTES
)
from magenta.core import (
    logger, mongo_client, engine,
    tenant_collections, get_db,
    create_postgres_extensions, load_all_functions_in_db, cleanup_mongo
)
from magenta.services import load_prompts_from_files
from magenta.routes.chats import chats_router
from app.routes.analysis import analysis_router
from app.core.tools import analysis_function_dictionary, analysis_function_tool_definitions


ENV = os.getenv('ENV', 'DEV')


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application server started.")
    
    # Startup logic
    tenant_collections.add_collection_type("analysis")
    await create_postgres_extensions(get_db)
    await load_prompts_from_files(tenant_collections.get_collections_list("prompts"), dir="data/prompts")
    await create_initial_users(users_collection, dir="data/users")
    await load_all_functions_in_db(
        tenant_collections.get_collections_list("tools"),
        overwrite=True,
        function_dictionary=analysis_function_dictionary,
        all_function_tool_definitions=analysis_function_tool_definitions
    )
    await cleanup_mongo(tenant_collections.get_collections_list("analysis"),[{"context_id":"test_context"}])

    yield
    
    # Shutdown logic
    mongo_client.close()
    engine.dispose()
    logger.info("Application server stopped.")


app = FastAPI(lifespan=lifespan)

# Include magenta routers
app.include_router(analysis_router)
app.include_router(chats_router)

@app.get("/")
async def read_root():
    return {"message": "Radian agent for data analysis"}


@app.get("/healthcheck")
async def healthcheck():
    return {"status": "ok"}


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