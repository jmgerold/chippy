"""
Simple Modal deployment that reuses your existing FastAPI app
Place this file in the ROOT of your repo
"""
import modal

# Create Modal app with "patent-harvester" name in compmotifs workspace
app = modal.App("patent-harvester", workspace="compmotifs")

# Docker image with dependencies
image = modal.Image.debian_slim(python_version="3.11").pip_install([
    "fastapi==0.111.0",
    "uvicorn[standard]==0.29.0", 
    "python-multipart==0.0.9",
    "lxml==5.2.1",
    "python-dotenv==1.0.1",
    "openai"  # For future OpenAI integration
])

# Persistent volume for patents (scales to 1TB+) in compmotifs workspace
patents_volume = modal.Volume.from_name("patent-harvester-data", create_if_missing=True, workspace="compmotifs")

# Mount your existing code
backend_mount = modal.Mount.from_local_dir("backend", remote_path="/app/backend")
frontend_mount = modal.Mount.from_local_dir("frontend", remote_path="/app/frontend")

@app.function(
    image=image,
    volumes={"/app/patents": patents_volume},  # Patent files storage
    mounts=[backend_mount, frontend_mount],     # Your existing code
    secrets=[modal.Secret.from_name("openai-secret", workspace="compmotifs")],  # OpenAI API key
    allow_concurrent_inputs=10,
    timeout=300,  # 5 minute timeout
    keep_warm=1   # Keep 1 instance warm to avoid cold starts
)
@modal.asgi_app()
def fastapi_app():
    """Your existing FastAPI app, unchanged"""
    import sys
    sys.path.append("/app")
    
    # Import your existing FastAPI app
    from backend.app import app as existing_app
    return existing_app


# Utility function to upload test data
@app.function(
    image=image,
    volumes={"/app/patents": patents_volume}
)
def upload_test_patent():
    """Upload your test.xml to Modal volume"""
    import shutil
    from pathlib import Path
    
    # Your test.xml content (copy from your local file)
    test_xml_content = Path("/app/backend/../patents/test.xml").read_text()
    
    # Write to Modal volume
    patents_dir = Path("/app/patents")
    patents_dir.mkdir(exist_ok=True)
    (patents_dir / "test.xml").write_text(test_xml_content)
    
    print("✅ Test patent uploaded to Modal volume!")


# Function to upload large patent datasets
@app.function(
    image=image,
    volumes={"/app/patents": patents_volume},
    cpu=2,  # More CPU for large uploads
    timeout=3600  # 1 hour for large uploads
)
def upload_patents_batch(batch_name: str):
    """Upload a batch of patents to Modal volume"""
    import os
    from pathlib import Path
    
    print(f"Ready to upload {batch_name} to Modal volume...")
    print("Use: modal volume put patents-data /local/path/to/patents/ /")
    
    # Check what's already uploaded
    patents_dir = Path("/app/patents")
    existing_files = list(patents_dir.glob("*.xml"))
    total_size = sum(f.stat().st_size for f in existing_files) / (1024**3)
    
    return {
        "files_uploaded": len(existing_files),
        "total_size_gb": round(total_size, 2),
        "sample_files": [f.name for f in existing_files[:5]]
    }


if __name__ == "__main__":
    # For local development, you can test the Modal app
    pass