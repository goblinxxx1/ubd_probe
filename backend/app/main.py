from fastapi import FastAPI

app = FastAPI(title="UBD Discounts API")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
