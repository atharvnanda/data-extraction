import uvicorn
from api.app import create_app
from api.config import get_settings

app = create_app()

if __name__ == "__main__":
    s = get_settings()
    uvicorn.run("server:app", host=s.API_HOST, port=s.API_PORT, reload=False)
