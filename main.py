from fastapi import FastAPI
import os
import uvicorn
from contextlib import asynccontextmanager

# Import from magenta bundle
from magenta.core import (
    logger, mongo_client, spacy_model, engine,
    tenant_collections, get_db, SLACK_WEBHOOK_URL,
    create_postgres_extensions, send_slack_message
)
from magenta.routes import (
    prompts_router, documents_router, chats_router,
    tools_router, tenants_router
)
from magenta.services import load_prompts_from_files, load_documents_from_files

# Import your custom routes
from app.routes import analysis_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application server started.")
    
    # Reuse magenta's startup logic
    await create_postgres_extensions(get_db)
    await load_prompts_from_files(tenant_collections.get_collections_list("prompts"), dir="data/prompts")
    await load_documents_from_files(
        documents_collections=tenant_collections.collections["documents"],
        dir="data/documents/instructions",
        model=spacy_model
    )
    
    # Add your custom startup logic here if needed
    
    yield
    
    # Cleanup from magenta
    mongo_client.close()
    engine.dispose()
    logger.info("Application server stopped.")


app = FastAPI(lifespan=lifespan)

# Include magenta routers
app.include_router(chats_router)
app.include_router(prompts_router)
app.include_router(tools_router)
app.include_router(documents_router)
app.include_router(tenants_router)

# Include project routers
app.include_router(analysis_router, prefix="/analysis", tags=["analysis"])


@app.get("/")
async def read_root():
    return {"message": "My Custom Project using Magenta Framework"}


@app.get("/healthcheck")
async def healthcheck():
    return {"status": "ok"}


# Reuse other key routes from magenta if needed
# You can either import them directly or reimplement them here


if __name__ == "__main__":
    logger.info("Starting application server.")
    uvicorn.run(app, host="0.0.0.0", port=8000)