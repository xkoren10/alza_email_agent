"""Step 1 of the knowledge base build: turns the raw PDF / Excel / image into chunks (JSON).

Run from anywhere:  python scripts/preprocess_files.py
Then run:           python scripts/create_indices.py
"""
import os
import re
import json
import pandas as pd
from pathlib import Path
from pypdf import PdfReader
from google import genai
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent / "knowledge_base"
KNOWLEDGE_DIR = BASE_DIR / "raw_files"
OUTPUT_FILE = BASE_DIR / "knowledge_chunks.json"

printGreen = printYellow = printRed = print

def preprocess_pdf_semantic(pdf_filename):
    """Semantically chunks the Pulsar-1 manual by sections and individual error codes."""
    chunks = []
    reader = PdfReader(os.path.join(KNOWLEDGE_DIR, pdf_filename))
    full_text = ""
    for page in reader.pages:
        t = page.extract_text()
        if t:
            full_text += "\n" + t

    # 1. Split by major section headings (e.g., "1. Product Overview", "2. Technical Specifications")
    sections = re.split(r'\n(?=\d\.\s+[A-Z])', full_text)
    
    for section in sections:
        section = section.strip()
        if not section:
            continue
            
        # Check if this section contains the error code table
        if "Diagnostic Matrix" in section or "ERR-" in section:
            # Further split individual error codes so each code is its own precise chunk
            error_blocks = re.split(r'\n(?=ERR-\d{3})', section)
            for block in error_blocks:
                block = block.strip()
                if block.startswith("ERR-"):
                    chunks.append({
                        "source": pdf_filename,
                        "type": "error_code_definition",
                        "content": f"AeroSpace Pulsar-1 Diagnostic Error Code Record -> {block}"
                    })
                elif len(block) > 15:
                    chunks.append({
                        "source": pdf_filename,
                        "type": "manual_section",
                        "content": block
                    })
        else:
            # Standard section chunk
            chunks.append({
                "source": pdf_filename,
                "type": "manual_section",
                "content": section
            })
            
    printGreen(f"Semantically extracted {len(chunks)} precise chunks from PDF.")
    return chunks

def preprocess_excel(excel_filename):
    excel_path = os.path.join(KNOWLEDGE_DIR, excel_filename)
    chunks = []
    if not os.path.exists(excel_path):
        print(f"⚠️ Warning: Excel not found at {excel_path}")
        return chunks
        
    print(f"Processing Excel catalog: {excel_filename}...")
    xls = pd.ExcelFile(excel_path)
    for sheet_name in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name)
        header_idx = None
        for idx, row in df.iterrows():
            if "Part ID" in str(row.values) or "Part Name" in str(row.values):
                header_idx = idx
                break
                
        if header_idx is not None:
            df.columns = df.iloc[header_idx]
            df = df.iloc[header_idx + 1:].dropna(subset=[df.columns[0]])
            
            for _, row in df.iterrows():
                row_data = [f"{col}: {val}" for col, val in row.items() if pd.notna(val) and col]
                row_sentence = " | ".join(row_data)
                chunks.append({
                    "source": excel_filename,
                    "type": "spare_part_record",
                    "content": f"AeroSpace Pulsar-1 Spare Part Record -> {row_sentence}"
                })
    printGreen(f"Extracted {len(chunks)} structured part records from Excel.")
    return chunks

def process_image_with_gemini(image_filename):
    image_path = os.path.join(KNOWLEDGE_DIR, image_filename)
    if not os.path.exists(image_path):
        printYellow(f"Warning: Image not found at {image_path}")
        return []
        
    print(f"Uploading cockpit control panel image to Gemini for analysis...")
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    
    uploaded_file = client.files.upload(file=image_path)
    
    prompt = (
        "Analyze this cockpit control panel image for the AeroSpace Pulsar-1 shuttle. "
        "Provide a detailed technical description of all visible warning lights, button grids, "
        "error code indicators (such as E-101, E-401, E-201, E-301, E-501), system status displays (SYS OK), "
        "and physical toggle switches. Format this clearly as a technical manifest so it can be indexed in a RAG knowledge base."
    )
    
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        contents=[uploaded_file, prompt]
    )
    
    image_description = response.text
    print(f"Gemini successfully generated control panel transcription.")
    
    client.files.delete(name=uploaded_file.name)
    
    return [{
        "source": image_filename,
        "type": "visual_schematic_metadata",
        "content": f"Cockpit Control Panel & Warning Light Schematic Description: {image_description}"
    }]

def main():
    print("Starting standalone knowledge base preprocessor...")
    all_chunks = []
    
    # 1. Process files
    all_chunks.extend(preprocess_pdf_semantic("Pulsar-1 User & Diagnostic Manual.pdf"))
    all_chunks.extend(preprocess_excel("Pulsar-1_Spare_Parts_Inventory.xlsx"))
    all_chunks.extend(process_image_with_gemini("Pulsar-1 Control Panel View.jpg"))
    
    # 2. Save into a single consolidated file
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)
        
    printGreen(f"Compiled {len(all_chunks)} total chunks and saved to '{OUTPUT_FILE}'.")

if __name__ == "__main__":
    main()