# stub.py
import modal

app = modal.App("patent-harvester")

# 1) Build from Dockerfile
image = modal.Image.from_dockerfile("Dockerfile")
# 2) Copy in your local code so every build has your latest changes:
image = (
    image
    .add_local_dir("patents",  "/app/patents")   # your XMLs
    .add_local_dir("frontend","/app/frontend")   # your HTML/CSS/JS
    .add_local_dir("backend", "/app/backend")    # your FastAPI code
)

@app.function(
    image=image,
    secrets=[modal.Secret.from_name("openai-secret")],
)
@modal.asgi_app()
def fastapi_app():
    # import inside the container so all deps are present
    from backend.app import app as existing_app
    return existing_app
