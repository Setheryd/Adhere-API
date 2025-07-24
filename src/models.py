from pydantic import BaseModel, Field
from typing import List, Dict, Any

class MemberProcessingRequest(BaseModel):
    member_ids: List[str] = Field(..., example=["member-id-123", "member-id-456"], description="A list of member IDs to process.")

class ProcessedMemberResult(BaseModel):
    member_id: str
    status: str
    details: Dict[str, Any]

class MemberProcessingResponse(BaseModel):
    job_id: str
    processed_results: List[ProcessedMemberResult]