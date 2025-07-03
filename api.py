# api.py

import io
import pandas as pd
import pdfplumber
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Import the main logic functions from our core.py file
from core import extract_financial_data_with_ai, process_financial_document

# Initialize the FastAPI application, which creates our backend server
app = FastAPI(
    title="VPB Tax Computation API",
    description="An API to extract financial data and compute Dutch Corporate Tax.",
)

# --- CORS Middleware ---
# This allows our Streamlit frontend (running on a different port/address)
# to make requests to this backend API. It's a security requirement for web browsers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development, allows all origins. For production, restrict to your frontend's URL.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def parse_file(file: UploadFile, content: bytes) -> (str, str):
    """
    A helper function to read the content of uploaded files.
    It checks the file extension and uses the appropriate library (pdfplumber or pandas) to parse it.
    """
    full_text, tables_text = "", ""
    filename = file.filename.lower()
    
    # --- PDF Handling ---
    if filename.endswith(".pdf"):
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                full_text += page.extract_text(x_tolerance=1) or ""
                for table in page.extract_tables():
                    if table: tables_text += pd.DataFrame(table).to_string() + "\n\n"
    
    # --- CSV, XLS, and XLSX Handling ---
    elif filename.endswith((".csv", ".xls", ".xlsx")):
        try:
            # pandas can read all these spreadsheet formats. 'openpyxl' is needed for .xlsx.
            df = pd.read_excel(io.BytesIO(content)) if 'xls' in filename else pd.read_csv(io.BytesIO(content))
            # For spreadsheets, we convert the entire DataFrame to a string for the AI to analyze
            full_text = df.to_string()
            tables_text = df.to_string()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error reading spreadsheet file: {e}")
    else:
        raise HTTPException(status_code=415, detail="Unsupported file type. Please use PDF, CSV, XLS, or XLSX.")
    
    return full_text, tables_text

# --- API Endpoint ---
@app.post("/process-document", summary="Extract and Compute Quarterly & Annual Tax")
async def process_document_endpoint(file: UploadFile = File(...)):
    """
    This is the main API endpoint. It receives the file from the frontend,
    uses the helper to parse it, then calls the core logic functions to do the heavy lifting.
    """
    content = await file.read()
    
    # Step 1: Parse the file content into text and table strings
    text_data, table_data = parse_file(file, content)

    if not text_data and not table_data:
        raise HTTPException(status_code=400, detail="Could not extract any text or tables from the document.")

    # Step 2: Call the AI via our core function to extract the raw figures into a structured JSON
    ai_extraction_result = extract_financial_data_with_ai(text_data, table_data)
    if "error" in ai_extraction_result:
        raise HTTPException(status_code=500, detail=ai_extraction_result["error"])
        
    # Step 3: Call the main processing function to perform all calculations and get the final report
    final_computation = process_financial_document(ai_extraction_result)
    if "error" in final_computation:
        raise HTTPException(status_code=500, detail=final_computation["error"])
        
    # Step 4: Return the final report as a JSON response to the frontend
    return final_computation


# --- This block is for deployment ---
# It allows us to run the app directly for development
# and tells a production server like Render how to run it.
if __name__ == "__main__":
    import uvicorn
    # The host '0.0.0.0' makes the app accessible from outside the container.
    # The port is read from an environment variable provided by Render.
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api:app", host="0.0.0.0", port=port)