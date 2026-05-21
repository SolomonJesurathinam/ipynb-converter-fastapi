from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import nbformat
from nbconvert import HTMLExporter, SlidesExporter
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

VALID_TEMPLATES = {"lab", "classic", "basic", "reveal"}

def auto_assign_slide_types(notebook, logger):
    # Check if the notebook already has any slide metadata configured
    has_slide_metadata = False
    for cell in notebook.cells:
        if "slideshow" in cell.metadata and cell.metadata.slideshow.get("slide_type"):
            if cell.metadata.slideshow["slide_type"] not in ("-", ""):
                has_slide_metadata = True
                break
                
    if has_slide_metadata:
        logger.info("Notebook already contains slideshow metadata. Respecting existing slide settings.")
        return notebook

    logger.info("Notebook lacks slideshow metadata. Dynamically assigning slide structure...")
    
    new_cells = []
    first_slide_created = False
    current_slide_weight = 0
    WEIGHT_LIMIT = 20  # Content weight threshold for splitting slides
    last_header_text = "Continuation"
    
    for cell in notebook.cells:
        # Extract heading text if this is a header markdown cell
        if cell.cell_type == "markdown":
            lines = cell.source.strip().splitlines()
            first_line = lines[0].strip() if lines else ""
            if first_line.startswith("# ") or first_line.startswith("## ") or first_line.startswith("### "):
                last_header_text = first_line.lstrip("#").strip()
                
        # Split slide if cumulative weight limit is exceeded and we have already created the first slide
        if first_slide_created and current_slide_weight >= WEIGHT_LIMIT:
            continuation_cell = nbformat.v4.new_markdown_cell(
                source=f"### {last_header_text} (Continued)"
            )
            continuation_cell.metadata.slideshow = {"slide_type": "slide"}
            new_cells.append(continuation_cell)
            current_slide_weight = 0

        slide_type = "-"
        if cell.cell_type == "markdown":
            lines = cell.source.strip().splitlines()
            first_line = lines[0].strip() if lines else ""
            
            if first_line.startswith("# ") or first_line.startswith("## "):
                slide_type = "slide"
            elif first_line.startswith("### "):
                slide_type = "subslide" if first_slide_created else "slide"
            else:
                if not first_slide_created:
                    slide_type = "slide"
                else:
                    slide_type = "fragment"
        elif cell.cell_type == "code":
            if not first_slide_created:
                slide_type = "slide"
            else:
                slide_type = "-"
                
        cell.metadata.slideshow = {"slide_type": slide_type}
        
        # If this cell starts a new slide/subslide, reset the weight counter
        if slide_type in ("slide", "subslide"):
            first_slide_created = True
            current_slide_weight = 0
            
        new_cells.append(cell)
        
        # Calculate cell weight
        cell_weight = 0
        if cell.cell_type == "markdown":
            # 1 weight per non-empty line of markdown content
            cell_weight += sum(1 for line in cell.source.splitlines() if line.strip())
        elif cell.cell_type == "code":
            # 1 weight per line of code input + 2 base padding
            cell_weight += sum(1 for line in cell.source.splitlines() if line.strip()) + 2
            # Handle code outputs
            if "outputs" in cell:
                for output in cell.outputs:
                    if output.get("output_type") == "stream" and "text" in output:
                        cell_weight += sum(1 for line in output["text"].splitlines() if line.strip())
                    elif output.get("output_type") in ("display_data", "execute_result"):
                        data = output.get("data", {})
                        if any(mime.startswith("image/") for mime in data.keys()):
                            cell_weight += 15  # Heavy weight for images/plots
                        elif "text/plain" in data:
                            cell_weight += sum(1 for line in data["text/plain"].splitlines() if line.strip())
                            
        current_slide_weight += cell_weight

    notebook.cells = new_cells
    return notebook

@app.post("/convert", response_class=HTMLResponse, tags=["Conversion"])
def convert_notebook(
    file: UploadFile = File(..., description="The .ipynb file to convert to HTML"),
    template: str = Query("lab", description="The template to use: 'lab', 'classic', 'basic', or 'reveal'"),
    theme: str = Query("simple", description="The reveal theme to use (e.g., simple, black, blood)"),
    transition: str = Query("slide", description="The reveal transition to use (e.g., slide, fade, zoom)"),
    auto_slides: bool = Query(True, description="Auto-structure slides based on markdown headers if notebook lacks slide metadata")
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

    if template not in VALID_TEMPLATES:
        logger.warning(f"Conversion failed: Invalid template requested ({template})")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid template style. Must be one of: {', '.join(VALID_TEMPLATES)}"
        )

    logger.info(f"Received notebook conversion request for file: {file.filename} using template: {template}")

    # Read uploaded file bytes
    try:
        file_bytes = file.file.read()
        notebook_content = file_bytes.decode('utf-8')
        
        # Parse the JSON string as a notebook node
        notebook = nbformat.reads(notebook_content, as_version=4)
        
        # Auto-structure slideshow if requested and template is reveal
        if template == "reveal" and auto_slides:
            notebook = auto_assign_slide_types(notebook, logger)
        
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
        logger.info(f"Executing in-memory HTML conversion with template '{template}' (theme: {theme}, transition: {transition})...")
        if template == "reveal":
            html_exporter = SlidesExporter(reveal_theme=theme, reveal_transition=transition, reveal_scroll=False)
        else:
            html_exporter = HTMLExporter(template_name=template)
        
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
