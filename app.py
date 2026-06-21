import os
import uuid
import asyncio
from datetime import datetime
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from scraper import scrape_itemscout_rankings

app = FastAPI(title="ItemScout Scraper API Portal")

# Active task tracking database (in-memory)
class TaskTracker:
    def __init__(self):
        self.status = "running"
        self.logs = []
        self.queues = []
        self.csv_path = None
        self.error = None
        self.complete_event = None

    async def log(self, message: str):
        self.logs.append(message)
        for q in list(self.queues):
            await q.put({"type": "log", "message": message})

    async def complete(self, download_url: str, csv_path: str):
        self.status = "completed"
        self.csv_path = csv_path
        self.complete_event = {"type": "complete", "download_url": download_url}
        for q in list(self.queues):
            await q.put(self.complete_event)

    async def fail(self, error_message: str):
        self.status = "failed"
        self.error = error_message
        self.complete_event = {"type": "error", "message": error_message}
        for q in list(self.queues):
            await q.put(self.complete_event)

tasks = {}

class ScrapeRequest(BaseModel):
    username: str
    password: str
    access_key: str

async def run_scraper_task(task_id: str, username: str, password: str):
    tracker = tasks[task_id]
    
    async def progress_callback(message: str):
        await tracker.log(message)
        
    try:
        await tracker.log("Initializing scraper engine...")
        # 1. Scrape ItemScout
        rows = await scrape_itemscout_rankings(username, password, progress_callback)
        
        if not rows:
            await tracker.log("No items found. Ensure you have active keywords registered in your Daily Tracker.")
            raise ValueError("No scraper items returned.")
            
        await tracker.log("Compiling results to CSV format...")
        
        # 2. Process and save to rankings.csv using the logic from main.py
        today_str = datetime.now().strftime("%Y-%m-%d")
        new_df = pd.DataFrame(rows)
        new_df["product_id"] = new_df["product_id"].astype(str)
        new_df.insert(0, "date", today_str)
        
        output_dir = "data"
        os.makedirs(output_dir, exist_ok=True)
        csv_path = os.path.join(output_dir, "rankings.csv")
        
        if os.path.exists(csv_path):
            await tracker.log(f"Reading existing rankings log from {csv_path}...")
            existing_df = pd.read_csv(csv_path, dtype={"product_id": str})
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            combined_df.drop_duplicates(subset=["date", "product_id", "keyword"], keep="last", inplace=True)
        else:
            await tracker.log("Creating new rankings log...")
            combined_df = new_df
            
        combined_df.sort_values(by=["date", "product_name", "keyword"], ascending=[True, True, True], inplace=True)
        combined_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        
        await tracker.log(f"Process complete. Exported {len(new_df)} keyword ranking lines to CSV.")
        
        # 3. Finalize task success
        download_url = f"/api/tasks/{task_id}/download"
        await tracker.log("Ready for download!")
        await tracker.complete(download_url, csv_path)
        
    except Exception as e:
        error_msg = str(e)
        await tracker.log(f"Scraper task failed: {error_msg}")
        await tracker.fail(error_msg)

@app.get("/")
async def serve_index():
    """Serves the front-end user interface."""
    index_path = os.path.join("templates", "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="index.html template not found")
    return FileResponse(index_path)

@app.post("/api/scrape")
async def start_scrape(req: ScrapeRequest):
    """Enqueues and starts a background scraping process."""
    correct_key = os.getenv("SCRAPER_ACCESS_KEY", "Coozin123##")
    if req.access_key != correct_key:
        raise HTTPException(status_code=403, detail="유효하지 않은 액세스 키입니다.")
        
    if not req.username or not req.password:
        raise HTTPException(status_code=400, detail="Username and password are required")
        
    task_id = str(uuid.uuid4())
    tasks[task_id] = TaskTracker()
    
    # Run the background task without blocking the request
    asyncio.create_task(run_scraper_task(task_id, req.username, req.password))
    
    return {"task_id": task_id}

@app.get("/api/tasks/{task_id}/progress")
async def get_progress(task_id: str):
    """Streams the logs and status updates of the task via Server-Sent Events."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
        
    tracker = tasks[task_id]
    
    async def event_generator():
        # Send historical logs first
        for log_msg in tracker.logs:
            yield f"data: {log_msg}\n\n"
            
        # Check if already finished
        if tracker.status == "completed" and tracker.complete_event:
            yield f"event: complete\ndata: {{\"download_url\": \"{tracker.complete_event['download_url']}\"}}\n\n"
            return
        elif tracker.status == "failed" and tracker.complete_event:
            yield f"event: error\ndata: {{\"message\": \"{tracker.complete_event['message']}\"}}\n\n"
            return
            
        # Subscribe to new logs
        q = asyncio.Queue()
        tracker.queues.append(q)
        
        try:
            while True:
                event = await q.get()
                if event["type"] == "log":
                    yield f"data: {event['message']}\n\n"
                elif event["type"] == "complete":
                    yield f"event: complete\ndata: {{\"download_url\": \"{event['download_url']}\"}}\n\n"
                    break
                elif event["type"] == "error":
                    yield f"event: error\ndata: {{\"message\": \"{event['message']}\"}}\n\n"
                    break
        except asyncio.CancelledError:
            pass
        finally:
            if q in tracker.queues:
                tracker.queues.remove(q)
                
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/tasks/{task_id}/download")
async def download_file(task_id: str):
    """Retrieves and downloads the CSV file generated by the task."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
        
    tracker = tasks[task_id]
    if tracker.status != "completed" or not tracker.csv_path:
        raise HTTPException(status_code=400, detail="Scraper results are not ready or task failed")
        
    if not os.path.exists(tracker.csv_path):
        raise HTTPException(status_code=404, detail="Output rankings CSV file was not found on disk")
        
    return FileResponse(
        path=tracker.csv_path,
        media_type="text/csv",
        filename="rankings.csv"
    )
