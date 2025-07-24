import uuid
from fastapi import FastAPI, Body
from .. import models
from .endpoints import x12_processor # <-- CORRECTED LINE

app = FastAPI(
    title="Adhere API",
    description="An API for processing X12 data for a list of members.",
    version="1.0.0",
)

@app.get("/", tags=["Health Check"])
async def read_root():
    """A simple health check endpoint to confirm the API is running."""
    return {"status": "ok", "message": "Welcome to the Adhere API!"}

@app.post("/process-members", response_model=models.MemberProcessingResponse, tags=["X12 Processing"])
async def create_processing_job(request: models.MemberProcessingRequest):
    """
    Accepts a list of member IDs, processes them through an X12 loop,
    and returns a structured JSON payload with the results.
    """
    job_id = f"job_{uuid.uuid4()}"

    processed_data = await x12_processor.process_x12_for_members(
        member_ids=request.member_ids
    )

    return models.MemberProcessingResponse(
        job_id=job_id,
        processed_results=processed_data
    )