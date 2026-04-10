from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import json
import os
import uuid
import subprocess

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_FILE = "db.json"

# --- Models ---
class Project(BaseModel):
    id: str
    name: str
    stages: list[str]

class Batch(BaseModel):
    id: str
    name: str
    quantity: int
    stage: str
    project_id: str

class MergeRequest(BaseModel):
    source_id: str
    target_id: str
    new_name: str

# --- DB Helpers ---
def init_db():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w") as f:
            json.dump({"projects": [], "batches": []}, f)

def read_db() -> dict:
    init_db()
    with open(DB_FILE, "r") as f:
        return json.load(f)

def write_db(data: dict):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

# --- Endpoints ---
@app.get("/data")
def get_data():
    return read_db()

# --- Project Endpoints ---
@app.post("/projects")
def add_project(project: Project):
    db = read_db()
    project.id = str(uuid.uuid4())
    db["projects"].append(project.dict())
    write_db(db)
    return project

@app.put("/projects/{proj_id}")
def update_project(proj_id: str, project: Project):
    db = read_db()
    for i, p in enumerate(db["projects"]):
        if p["id"] == proj_id:
            project.id = proj_id
            db["projects"][i] = project.dict()
            write_db(db)
            return project
    raise HTTPException(status_code=404, detail="Project not found")

@app.delete("/projects/{proj_id}")
def delete_project(proj_id: str):
    db = read_db()
    db["projects"] = [p for p in db["projects"] if p["id"] != proj_id]
    # Cascade delete batches belonging to this project
    db["batches"] = [b for b in db["batches"] if b["project_id"] != proj_id]
    write_db(db)
    return {"status": "deleted"}

# --- Batch Endpoints ---
@app.post("/batches")
def add_batch(batch: Batch):
    db = read_db()
    batch.id = str(uuid.uuid4())
    db["batches"].append(batch.dict())
    write_db(db)
    return batch

@app.put("/batches/{batch_id}")
def update_batch(batch_id: str, updated: dict):
    db = read_db()
    for i, b in enumerate(db["batches"]):
        if b["id"] == batch_id:
            db["batches"][i].update(updated)
            write_db(db)
            return db["batches"][i]
    raise HTTPException(status_code=404, detail="Batch not found")

@app.post("/batches/{batch_id}/split")
def split_batch(batch_id: str, split_qty: int):
    db = read_db()
    for b in db["batches"]:
        if b["id"] == batch_id:
            if b["quantity"] <= split_qty:
                raise HTTPException(status_code=400, detail="Invalid quantity")
            b["quantity"] -= split_qty
            new_batch = b.copy()
            new_batch["id"] = str(uuid.uuid4())
            new_batch["quantity"] = split_qty
            new_batch["name"] = f"{b['name']} (Split)"
            db["batches"].append(new_batch)
            write_db(db)
            return {"status": "split success"}
    raise HTTPException(status_code=404)

@app.post("/batches/merge")
def merge_batches(req: MergeRequest):
    db = read_db()
    source_idx, target_idx = None, None
    for i, b in enumerate(db["batches"]):
        if b["id"] == req.source_id: source_idx = i
        if b["id"] == req.target_id: target_idx = i
    source = db["batches"][source_idx]
    target = db["batches"][target_idx]
    if source["project_id"] != target["project_id"]:
        raise HTTPException(status_code=400, detail="Projects must match")
        
    target["quantity"] += source["quantity"]
    target["name"] = req.new_name
    db["batches"].pop(source_idx)
    write_db(db)
    return {"status": "merged"}

@app.post("/sync")
def sync_to_github():
    try:
        subprocess.run(["git", "add", "db.json"], check=True)
        subprocess.run(["git", "commit", "-m", "Manual sync update"], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        return {"status": "Successfully synced"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Serve the Frontend ---
@app.get("/")
def serve_app():
    return FileResponse('static/index.html')

app.mount("/", StaticFiles(directory="static"), name="static")


# Init with 
# uvicorn main:app --reload --host 0.0.0.0 --port 8000