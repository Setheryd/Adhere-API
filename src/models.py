from pydantic import BaseModel, Field
from typing import List, Dict, Any

class MemberProcessingRequest(BaseModel):
    member_ids: List[str] = Field(..., example=[    "100000224499",
    "100009208899",
    "100031222199",
    "100034692299",
    "100047872599",
    "100052792799",
    "100053155699",
    "100080761899",
    "100083761599",
    "100106311299",
    "100107747699",
    "100112067299",
    "100115364099",
    "100116654399",
    "100117923199",
    "100119036099",
    "100167106299",
    "100169623499",
    "100178044299",
    "100178431199",
    "121587618499",
    "121604797599",
    "121689759399"], description="A list of member IDs to process.")

class ProcessedMemberResult(BaseModel):
    member_id: str
    status: str
    details: Dict[str, Any]

class MemberProcessingResponse(BaseModel):
    job_id: str
    processed_results: List[ProcessedMemberResult]
    
    