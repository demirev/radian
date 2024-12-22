# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt ./

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Download spacy model
# RUN python -m spacy download en_core_web_lg

# Copy the rest of the application code into the container
COPY magenta/ ./magenta
COPY app/ ./app
COPY data/ ./data
COPY logs/ ./logs
COPY tests/ ./tests
COPY __init__.py ./__init__.py

# Set pythonpath
ENV PYTHONPATH=/app

# Command to run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
