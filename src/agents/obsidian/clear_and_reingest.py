"""
Clear Weaviate collections and re-ingest all data from Obsidian vault
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import weaviate
from .atomic_document_ingestion import AtomicObsidianIngestion

def clear_and_reingest():
    """Delete existing collections and re-ingest everything"""
    load_dotenv()
    
    print("=" * 60)
    print("WEAVIATE CLEAR AND RE-INGEST")
    print("=" * 60)
    
    # Connect to Weaviate
    print("\n[1] Connecting to Weaviate...")
    try:
        # Try local connection
        client = weaviate.connect_to_local(
            host="localhost",
            port=8080,
            headers={"X-OpenAI-Api-Key": os.getenv("OPENAI_API_KEY")}
        )
        print("Connected to local Weaviate")
    except Exception as e:
        print(f"Failed to connect: {e}")
        return
    
    # Delete existing collections
    print("\n[2] Deleting existing collections...")
    try:
        if client.collections.exists("Company"):
            client.collections.delete("Company")
            print("   Deleted Company collection")
        else:
            print("   Company collection doesn't exist")
            
        if client.collections.exists("WorkLog"):
            client.collections.delete("WorkLog")
            print("   Deleted WorkLog collection")
        else:
            print("   WorkLog collection doesn't exist")
    except Exception as e:
        print(f"   Warning: Error deleting collections: {e}")
    
    # Close the client used for deletion
    client.close()
    
    # Now re-ingest with the new schema
    print("\n[3] Starting fresh ingestion with new schema...")
    ingestion = AtomicObsidianIngestion()
    
    # Connect (this will create the new schema)
    ingestion.connect()
    
    # Get vault path
    vault_path = os.getenv('OBSIDIAN_VAULT_PATH')
    if not vault_path:
        print("ERROR: No OBSIDIAN_VAULT_PATH in .env file")
        return
    
    print(f"\n[4] Ingesting from vault: {vault_path}")

    # Get index folder path from environment or use default
    # Format: "Company Name/Main Files/3 - Index" or just "3 - Index" if vault root
    index_folder = os.getenv('OBSIDIAN_INDEX_FOLDER', '3 - Index')
    index_path = Path(vault_path) / index_folder
    if not index_path.exists():
        print(f"ERROR: Index folder not found at: {index_path}")
        print(f"Hint: Set OBSIDIAN_INDEX_FOLDER in .env to match your vault structure")
        return
    
    # Find all markdown files
    md_files = list(index_path.rglob("*.md"))
    print(f"   Found {len(md_files)} markdown files in Index folder")
    
    # Ingest each file
    success = 0
    failed = 0
    
    for i, filepath in enumerate(md_files, 1):
        print(f"   [{i}/{len(md_files)}] Processing: {filepath.name}", end="")
        if ingestion.ingest_file(filepath):
            print(" [OK]")
            success += 1
        else:
            print(" [FAILED]")
            failed += 1
    
    print("\n[5] Ingestion Complete!")
    print(f"   Success: {success} files")
    if failed > 0:
        print(f"   Failed: {failed} files")
    
    # Verify the ingestion
    print("\n[6] Verification:")
    ingestion.verify_ingestion()
    
    # Cleanup
    ingestion.client.close()
    
    print("\nClear and re-ingest complete!")
    print("=" * 60)

if __name__ == "__main__":
    clear_and_reingest()