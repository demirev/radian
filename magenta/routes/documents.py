import uuid
from typing import List, Dict, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, File, UploadFile
from sqlalchemy import delete
from core.config import logger, tenant_collections, get_db
from core.models import Document, Task
from services.document_service import process_document, create_postgres_table, perform_postgre_search
from sqlalchemy.orm import Session


documents_router = APIRouter(prefix="/documents", tags=["documents"])


@documents_router.get("/", response_model=List[Document])
async def list_documents(
	tenant_id: str = "default",
  document_id: Optional[str] = Query(None, title="Document ID", description="Filter by document ID"),
  name: Optional[str] = Query(None, title="Document name", description="Filter by document name"),
  type: Optional[str] = Query(None, title="Document type", description="Filter by document type"),
):
  documents_collection = tenant_collections.get_collection(tenant_id, "documents")

  query = {}
  if document_id:
    query["document_id"] = document_id
  if name:
    query["name"] = name
  if type:
    query["type"] = type
  
  documents = documents_collection.find(query, {"_id": 0})
  
  return list(documents)


@documents_router.get("/ids", response_model=List[Dict[str, str]])
async def list_document_ids(
	tenant_id: str = "default",
	document_id: Optional[str] = Query(None, title="Document ID", description="Filter by document ID"),
	name: Optional[str] = Query(None, title="Document name", description="Filter by document name"),
	type: Optional[str] = Query(None, title="Document type", description="Filter by document type"),
):
	documents_collection = tenant_collections.get_collection(tenant_id, "documents")

	query = {}
	if document_id:
		query["document_id"] = document_id
	if name:
		query["name"] = name
	if type:
		query["type"] = type
	
	documents = documents_collection.find(query, {"_id": 0, "document_id": 1, "name": 1, "description": 1})
	
	return list(documents)


@documents_router.post("/upload", response_model=Task)
async def upload_document(
	name: str, 
	type: str, 
	background_tasks: BackgroundTasks, 
	tenant_id: str = "default",
	document_id: Optional[str] = None,
	description: Optional[str] = None,
	file: UploadFile = File(...), 
	chunk_size: int = 1000,
	metadata: dict = None,
	db: Session = Depends(get_db)
):
	try:
		documents_collection = tenant_collections.get_collection(tenant_id, "documents")
		
		# check if file is pdf
		if file.content_type != "application/pdf":
			raise HTTPException(status_code=400, detail="Only PDF files are supported")

		if not document_id:
			document_id = str(uuid.uuid4())
		else:
			if documents_collection.find_one({"document_id": document_id}):
				raise HTTPException(status_code=400, detail="Document ID already exists")

		file_location = f"temp/{file.filename}"
		with open(file_location, "wb") as f:
			f.write(file.file.read())
		
		documents_collection.insert_one(
			{
				"document_id": document_id,
				"name": name,
				"type": type,
				"description": description,
				"metadata": metadata,
				"status": "pending"
			}
		)

		# Schedule the document processing task
		logger.info(f"Uploading document {name}, ID {document_id} into table {tenant_id}.")
		background_tasks.add_task(
			process_document,
			document_id = document_id,
			file_location = file_location,
			content_type = file.content_type,
			chunk_size = chunk_size,
			name = name,
			type = type,
			metadata = metadata,
			spacy_model = None,
			documents_collection = documents_collection,
			table_name = tenant_id, # using tenant_id as table_name for now, later we might have separate schemas for different tenants
			db = db
		)
		return {"task_id": document_id, "status":"pending", "type":"document upload"}  
		
	except Exception as e:
		logger.error(f"Error uploading document: {e}")
		raise HTTPException(status_code=400, detail="Error uploading document")


@documents_router.post("/search", response_model=List[dict])
async def search_documents(
	query: str,
	tenant_id: str = "default",
	min_cosine_similarity: Optional[float] = -1,
	limit: Optional[int] = 10,
	db: Session = Depends(get_db)
):  
	try:
		
		search_results = perform_postgre_search(
			new_message=query,
			rag_documents=[],
			db=db,
			spacy_model=None,
			table_name=tenant_id,
			top_n=limit,
			similarity_threshold=min_cosine_similarity
		)

		return search_results

	except Exception as e:
		logger.error(f"Error searching PostgreSQL collection: {str(e)}")
		raise HTTPException(status_code=500, detail=f"Error searching PostgreSQL: {str(e)}")


@documents_router.delete("/{document_id}")
async def delete_document(document_id: str, tenant_id: str = "default", db: Session = Depends(get_db)):
	# First, get the document to find out which collection it's in
	documents_collection = tenant_collections.get_collection(tenant_id, "documents")
	document = documents_collection.find_one({"document_id": document_id})
	if not document:
		logger.warning(f"Document {document_id} not found.")
		raise HTTPException(status_code=404, detail="Document not found")
	
	table_name = tenant_id # for now using tenant_id as table_name
	
	try:
		# Delete from PostgreSQL
		VectorModel = create_postgres_table(table_name, db.bind)
		deleted = db.execute(delete(VectorModel).where(VectorModel.document_id == document_id))
		db.commit()

		if deleted.rowcount == 0:
			logger.warning(f"No vectors found for document {document_id} in PostgreSQL.")
		else:
			logger.info(f"Deleted {deleted.rowcount} vectors for document {document_id} from PostgreSQL table {table_name}")

		# Delete from MongoDB
		result = documents_collection.delete_one({"document_id": document_id})
		if result.deleted_count == 0:
			logger.warning(f"Document {document_id} not found in MongoDB when deleting.")
		else:
			logger.info(f"Deleted document {document_id} from MongoDB.")

		return {"message": "Document deleted successfully"}

	except Exception as e:
		logger.error(f"Error deleting document: {str(e)}")
		raise HTTPException(status_code=500, detail=f"Error deleting document: {str(e)}")


@documents_router.get("/{document_id}/status", response_model=Task)
async def get_document_upload_status(document_id: str, tenant_id: str = "default"):
	documents_collection = tenant_collections.get_collection(tenant_id, "documents")
	document = documents_collection.find_one({"document_id": document_id}, {"_id": 0, "status": 1})
	if not document:
		logger.warning(f"Document {document_id} not found.")
		raise HTTPException(status_code=404, detail="Document not found")
	return {"task_id": document_id, "status": document["status"]}


@documents_router.get("/{document_id}", response_model=Document)
async def get_document(document_id: str, tenant_id: str = "default"):
	documents_collection = tenant_collections.get_collection(tenant_id, "documents")
	document = documents_collection.find_one({"document_id": document_id}, {"_id": 0})
	if not document:
		logger.warning(f"Document {document_id} not found.")
		raise HTTPException(status_code=404, detail="Document not found")
	return document


@documents_router.get("/{document_id}/text", response_model=dict)
async def get_document_chunks(document_id: str, tenant_id: str = "default"):
	documents_collection = tenant_collections.get_collection(tenant_id, "documents")
	document = documents_collection.find_one({"document_id": document_id})
	if not document:
		logger.warning(f"Document {document_id} not found.")
		raise HTTPException(status_code=404, detail="Document not found")
	
	if document["status"] != "completed":
		logger.warning(f"Vectorizing document {document_id} not yet completed.")
		raise HTTPException(status_code=400, detail="Document vectorization  not completed")
	
	return {"text": document["text"], "metadata": document["metadata"], "chunks": document["chunks"]}
	