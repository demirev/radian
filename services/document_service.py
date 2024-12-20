import os
import uuid
from typing import List
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from core.config import logger, get_db
from core.utils import embed_text_spacy, get_vector_table, read_pdf_text, chunk_text_paragraphs, create_postgres_table

def add_documents_to_sysprompt(sysprompt, documents_collection):
  if "documents" in sysprompt and "context_documents" in sysprompt["documents"]:
    logger.info(f"Context documents found in sysprompt.")
    
    # read the full text of all documents
    context_docs = []
    for doc in sysprompt["documents"]["context_documents"]:
      context_doc = documents_collection.find_one({"document_id": doc["document_id"]})
      if not context_doc:
        raise ValueError(f"Document {doc['document_id']} not found.")
      context_docs.append(context_doc)
      
    # add a short connecting prompt to the system prompt
    if "context_connecting_prompt" in sysprompt["documents"]:
      context_connecting_prompt = sysprompt["documents"]["context_connecting_prompt"]
    else:
      context_connecting_prompt = ""

    # append the full text of the document to the system prompt
    sysprompt["prompt"] = sysprompt["prompt"] + "\n\n" + context_connecting_prompt + "\n\n" + "\n\n".join([doc["text"] for doc in context_docs])
  else:
    logger.info("No context documents found in sysprompt.")
  return sysprompt


def add_rag_results_to_message(
    sysprompt, 
    new_message, 
    rag_func, 
    db: Session,
    spacy_model,
    table_name,
    persist_rag_results=False
):
  if "documents" in sysprompt and "rag_documents" in sysprompt["documents"] and rag_func is not None:
    logger.info(f"RAG documents found in sysprompt.")

    if table_name is None:
      raise ValueError("Table name is required for RAG.")

    if "rag_connecting_prompt" in sysprompt["documents"]:
      rag_connecting_prompt = sysprompt["documents"]["rag_connecting_prompt"]
    else:
      rag_connecting_prompt = ""

    rag_documents = [doc["document_id"] for doc in sysprompt["documents"]["rag_documents"]]
    rag_result = rag_func(
      new_message=new_message, 
      rag_documents=rag_documents, 
      db=db,
      spacy_model=spacy_model,
      table_name=table_name
    )
    
    # Format the RAG results
    formatted_rag_result = "\n\n".join([f"Document: {r['name']}\nPotentially Relevant Text Excerpt: {r['text']}" for r in rag_result])
    
    if persist_rag_results:
      new_message = new_message + "\n\n" + rag_connecting_prompt + "\n" + formatted_rag_result
  else:
    logger.info("No RAG documents found in sysprompt.")
    rag_result = None
    formatted_rag_result = None

  return new_message, formatted_rag_result



async def insert_into_postgres(
	db: Session,
	document_id: str,
	name: str,
	chunks: list,
	embeddings: list,
	metadata: dict,
	table_name: str = "default"
):
	logger.info(f"Inserting into PostgreSQL table {table_name}")
	VectorModel = create_postgres_table(table_name, db.bind)
   
	inserted_count = 0
	logger.info(f"{len(chunks)} chunks to insert")
	for chunk, embedding in zip(chunks, embeddings):
		vector_id = uuid.uuid4().hex
		vector = VectorModel(
			id=vector_id,
			document_id=document_id,
			name=name,
			text=chunk,
			embedding=embedding
			#**metadata  # TODO learn how to insert metadata
		)
		try:
			db.add(vector)
			db.flush()  # This will assign the ID if it's auto-generated
			inserted_count += 1
		except IntegrityError:
			db.rollback()  # Roll back the failed insertion
			logger.warning(f"Duplicate vector ID {vector_id} encountered. Skipping.")
		except Exception as e:
			db.rollback()
			logger.error(f"Error inserting vector: {str(e)}")
	
	db.commit()
	logger.info(f"Inserted {inserted_count} vectors into PostgreSQL table {table_name}")
	return inserted_count


def perform_postgre_search(
    new_message: str,
    rag_documents: List[str],
    db: Session,
    spacy_model,
    table_name: str = "default",
    top_n: int = 5,
    similarity_threshold: float = 0.7
):
  try:
    # Embed the query text
    query_vector = embed_text_spacy(new_message, spacy_model)
    logger.info(f"Embedded query text.")

    # Get the VectorModel for the specified collection
    logger.info(f"Searching PostgreSQL table {table_name}.")
    VectorModel = get_vector_table(table_name, db.bind)

    # Construct the query
    stmt = (
      select(
          VectorModel.id,
          VectorModel.name,
          VectorModel.document_id,
          VectorModel.text,
          VectorModel.embedding.cosine_distance(query_vector).label("distance")
        )
    )

    if len(rag_documents):
      stmt = stmt.filter(VectorModel.name.in_(rag_documents))

    stmt = stmt.filter(VectorModel.embedding.cosine_distance(query_vector) <= (1-similarity_threshold))

    stmt = stmt.order_by(VectorModel.embedding.cosine_distance(query_vector))

    stmt = stmt.limit(top_n)

    # Execute the query
    results = db.execute(stmt).all()

    # Format the results
    search_results = [
      {
        "id": result.id,
				"name": result.name,
				"document_id": result.document_id,
				"text": result.text,
				"similarity": 1-result.distance
      }
      for result in results
    ]

    logger.info(f"Found {len(search_results)} relevant chunks from {len(set(r['name'] for r in search_results))} documents.")

    return search_results

  except Exception as e:
    logger.error(f"Error performing PostgreSQL search: {str(e)}")
    raise


async def process_document(
	document_id: str,
	file_location: str,
	content_type: str,
	name: str,
	type: str,
	metadata: dict,
	spacy_model,
	documents_collection,
	db: Session = next(get_db()),
	table_name: str = "default",
	chunk_size: int = 1000,
  cleanup_file: bool = True
):
	try:
		# Check file type
		if content_type == "application/pdf":
			# Read the text from the pdf
			text = read_pdf_text(file_location)
		else:
			raise ValueError("Unsupported file type.")

		# Chunk the text
		chunks = chunk_text_paragraphs(text, chunk_size=chunk_size)
		logger.info(f"Document {name} chunked into {len(chunks)} parts.")
		
		# Embed each chunk
		embeddings = []
		for chunk in chunks:
			embeddings.append(embed_text_spacy(chunk, spacy_model))
		logger.info(f"Document {name} embedded into {len(embeddings)} parts, each of dimension {len(embeddings[0])}")

		# Insert each part into the database
		documents_collection.update_one(
			{"document_id": document_id},
			{"$set": {
				"text": text,
				"chunks": len(chunks),
				"chunks_text": chunks,
				"status": "submitted"
			}}
		)
		
		inserted_count = await insert_into_postgres(
			db=db,
			document_id=document_id,
			name=name,
			chunks=chunks,
			embeddings=embeddings,
			metadata=metadata,
			table_name=table_name
		)
		
		documents_collection.update_one(
			{"document_id": document_id},
			{"$set": {
				"status": "completed",
				"vectors_inserted": inserted_count
			}}
		)

	except Exception as e:
		logger.error(f"Error processing document {document_id}: {e}")
		documents_collection.update_one(
			{"document_id": document_id},
			{"$set": {"status": "failed", "error": str(e)}}
		) 
	finally:
		if cleanup_file:
			os.remove(file_location)