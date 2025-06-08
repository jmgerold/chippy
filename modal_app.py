"""
Simple Modal deployment that reuses your existing FastAPI app
Place this file in the ROOT of your repo

To create the OpenAI secret (if needed):
1. Go to https://modal.com/secrets
2. Click "Create Secret"
3. Name it "openai-secret"
4. Add key "OPENAI_API_KEY" with your API key value
"""
import modal

# Create Modal app with workspace specified
app = modal.App("patent-harvester")

# Docker image with all dependencies, including your local files
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install([
        "fastapi==0.111.0",
        "uvicorn[standard]==0.29.0", 
        "python-multipart==0.0.9",
        "lxml==5.2.1",
        "python-dotenv==1.0.1",
        "openai",  # For future OpenAI integration
        "duckdb",
        "pandas"
    ])
    # Create patents directory in the image BEFORE adding local files
    .run_commands("mkdir -p /app/patents")
    # Add local directories last (Modal optimization)
    .add_local_dir("backend", "/app/backend")
    .add_local_dir("frontend", "/app/frontend")
)

# Persistent volume for patents (scales to 1TB+)
patents_volume = modal.Volume.from_name("patent-harvester-data", create_if_missing=True)

# Note: If you need concurrent request handling, you can either:
# 1. Let Modal auto-scale (default behavior)
# 2. Use @modal.concurrent decorator for explicit control
# 3. Set container_idle_timeout for instance lifecycle control

@app.function(
    image=image,
    volumes={"/app/patents": patents_volume},  # Patent files storage
    # Commenting out secret for now - uncomment when you create it
    secrets=[modal.Secret.from_name("openai-secret")],  # OpenAI API key
    timeout=300,  # 5 minute timeout
    min_containers=0,   # Keep 1 instance warm to avoid cold starts
    max_containers=2,
)
@modal.asgi_app()
def fastapi_app():
    import sys, os
    sys.path.append("/app")
    os.environ["XML_STORE_DIR"] = "/app/patents"
    from backend.app import app as existing_app
    return existing_app
# Utility function to upload test data
@app.function(
    image=image,
    volumes={"/app/patents": patents_volume}
)
def upload_test_patent():
    """Upload test.xml to Modal volume - call this after deployment"""
    from pathlib import Path
    
    # Test XML content from the image
    test_xml_path = Path("/app/patents/test.xml")
    
    if test_xml_path.exists():
        print(f"✅ Test patent already exists at {test_xml_path}")
        return
    
    # Create a simple test XML if none exists
    test_xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<patent>
    <tables>
        <table>
            <title>Battery Separator Materials</title>
            <row><cell>Material</cell><cell>Thickness</cell><cell>Temperature</cell></row>
            <row><cell>Polyethylene</cell><cell>25 μm</cell><cell>130°C</cell></row>
            <row><cell>Polypropylene</cell><cell>20 μm</cell><cell>165°C</cell></row>
        </table>
    </tables>
</patent>"""
    
    # Write to Modal volume
    patents_dir = Path("/app/patents")
    patents_dir.mkdir(exist_ok=True)
    (patents_dir / "test.xml").write_text(test_xml_content)
    
    print("✅ Test patent uploaded to Modal volume!")


# Function to check volume contents
@app.function(
    image=image,
    volumes={"/app/patents": patents_volume}
)
def check_patents():
    """Check what patents are in the Modal volume"""
    from pathlib import Path
    
    patents_dir = Path("/app/patents")
    if not patents_dir.exists():
        return {"status": "Patents directory doesn't exist yet", "files": []}
    
    xml_files = list(patents_dir.glob("*.xml"))
    
    return {
        "status": f"Found {len(xml_files)} patent files",
        "files": [f.name for f in xml_files[:10]],  # First 10 files
        "total_size_mb": sum(f.stat().st_size for f in xml_files) / (1024**2)
    }


# Function to upload patents from local directory
@app.local_entrypoint()
def upload_local_patents(local_dir: str = "./patents"):
    """Upload patents from local directory to Modal volume"""
    import modal
    from pathlib import Path
    
    local_path = Path(local_dir)
    if not local_path.exists():
        print(f"❌ Directory {local_dir} doesn't exist")
        return
    
    xml_files = list(local_path.glob("*.xml"))
    print(f"Found {len(xml_files)} XML files to upload")
    
    # Upload using Modal CLI (more efficient for bulk uploads)
    print(f"\nTo upload all patents, run:")
    print(f"modal volume put patent-harvester-data {local_dir} /")
    
    # Or upload individually
    if len(xml_files) < 10:
        with app.run():
            for xml_file in xml_files:
                print(f"Uploading {xml_file.name}...")
                # This would require a function to handle individual uploads
                # For now, use the CLI command above


if __name__ == "__main__":
    print("Deploy with: modal deploy modal_app.py")
    print("\nAfter deployment:")
    print("1. Your app URL will be shown (save it!)")
    print("2. The app may show as 'inactive' - this is normal")
    print("3. It will activate when you visit the URL")
    print("\nNote: The OpenAI secret is currently commented out.")
    print("If you need it, create it at: https://modal.com/secrets")
    print("Then uncomment the secrets line in the @app.function decorator")