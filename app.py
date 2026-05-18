from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import nbformat
from nbconvert import HTMLExporter
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize FastAPI App
app = FastAPI(
    title="Jupyter Notebook to HTML Converter API",
    description="A high-performance, pure-Python API to convert Jupyter Notebooks (.ipynb) to HTML completely in-memory.",
    version="1.0.0"
)

# Enable CORS (Allows cross-origin access from any mobile app, web app, or frontend client)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", tags=["Health"])
@app.get("/health", tags=["Health"])
def health_check():
    """
    Health check endpoint for monitoring and cloud hosting platforms.
    """
    return {
        "status": "healthy",
        "service": "Jupyter Notebook to HTML API (Pure Python)",
        "docs_url": "/docs"
    }

@app.post("/convert", response_class=HTMLResponse, tags=["Conversion"])
def convert_notebook(
    file: UploadFile = File(..., description="The .ipynb file to convert to HTML")
):
    """
    Convert an uploaded Jupyter Notebook (.ipynb) to a standalone HTML page completely in-memory.
    No browser binaries required! Works in ultra-lightweight hosting containers.
    """
    # 1. Validation
    if not file.filename.endswith('.ipynb'):
        logger.warning(f"Conversion failed: Invalid file extension ({file.filename})")
        raise HTTPException(
            status_code=400, 
            detail="Invalid file extension. Only '.ipynb' files are supported."
        )

    logger.info(f"Received notebook conversion request for file: {file.filename}")

    # Read uploaded file bytes
    try:
        file_bytes = file.file.read()
        notebook_content = file_bytes.decode('utf-8')
        
        # Parse the JSON string as a notebook node
        notebook = nbformat.reads(notebook_content, as_version=4)
    except UnicodeDecodeError:
        logger.exception("Encoding error while reading notebook file.")
        raise HTTPException(
            status_code=400,
            detail="Could not decode file as UTF-8. Please verify it is a valid text file."
        )
    except Exception as e:
        logger.exception("Jupyter Notebook parsing error.")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to parse notebook JSON: {str(e)}"
        )

    # 2. Conversion Pipeline (Runs in background thread pool to prevent event loop block)
    try:
        logger.info("Executing in-memory HTML conversion...")
        html_exporter = HTMLExporter()
        html_exporter.template_name = 'classic'
        
        # Export completely in-memory without touching disk or launching a browser!
        html_data, _ = html_exporter.from_notebook_node(notebook)
        
        logger.info("HTML conversion complete!")
        return HTMLResponse(content=html_data)
    except Exception as e:
        logger.exception("Error converting notebook to HTML.")
        raise HTTPException(status_code=500, detail=f"HTML Conversion error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Starting server on port {port}...")
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
