# Use official lightweight Python image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=7860

# Set working directory inside the container
WORKDIR /code

# Copy requirements file first to leverage Docker cache build step
COPY ./requirements.txt /code/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Copy all project files to the container working directory
COPY . /code

# Expose the default Hugging Face Spaces port
EXPOSE 7860

# Start the FastAPI application
CMD ["python", "app.py"]
