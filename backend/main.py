from fastapi import FastAPI

app = FastAPI(title="ReadingTutor PH")


@app.get("/api/health")
def health():
    return {"status": "ok"}
