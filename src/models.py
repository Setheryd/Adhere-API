# src/models.py

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class FinalMemberResult(BaseModel):
    member_id: str
    patient: Optional[str] = Field(None, description="Patient's name, formatted as LAST, FIRST M.")
    waiver_status: str = Field(description="Eligibility status for the waiver, e.g., 'Eligible' or 'Ineligible'.")
    mce: Optional[str] = Field(None, description="The Managed Care Entity (MCE) for the patient.")
    coverage: Optional[str] = Field(None, description="The specific name of the coverage plan.")
    start_date: Optional[str] = Field(None, description="The coverage start date.")
    end_date: Optional[str] = Field(None, description="The coverage end date.")



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
