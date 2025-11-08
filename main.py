# Top-level wrapper so `uvicorn main:app` works from project root.
# This imports the FastAPI `app` instance defined in `app/main.py`.
from app.main import app

# Optionally, you could add a simple guard to run with `python main.py`,
# but uvicorn will import `app` from this module directly.
if __name__ == "__main__":
    # Keep this minimal - uvicorn is preferred for serving.
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
