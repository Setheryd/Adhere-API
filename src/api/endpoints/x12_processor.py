# src/api/endpoints/x12_processor.py

import os
import httpx
import uuid
import random
from datetime import datetime
from typing import List, Dict, Any

# We will need the models for the response structure
from ... import models

# Load environment variables (for the password)
from dotenv import load_dotenv
load_dotenv()

# --- Helper function to generate random numbers ---
def generate_random_number(digits: int) -> int:
    """Generates a random number with a specific number of digits."""
    min_val = 10**(digits - 1)
    max_val = (10**digits) - 1
    return random.randint(min_val, max_val)

# --- Function to generate the X12 270 payload for a single member ID ---
def generate_x12_payload(member_id: str) -> str:
    """Generates the X12 270 payload string for a given member ID."""
    now = datetime.utcnow()
    date_str = now.strftime('%Y%m%d')
    time_str = now.strftime('%H%M')
    isa_date_str = now.strftime('%y%m%d')
    
    control_number = f"1000{generate_random_number(5)}"
    group_control_number = str(generate_random_number(5))
    transaction_id = f"1000{generate_random_number(4)}"
    eligibility_date = date_str

    transaction_segments = [
        f"ST*270*1240*005010X279A1~",
        f"BHT*0022*13*{transaction_id}*{date_str}*{time_str}~",
        f"HL*1**20*1~",
        f"NM1*PR*2*INDIANA HEALTH COVERAGE PROGRAM*****PI*IHCP~",
        f"HL*2*1*21*1~",
        f"NM1*1P*2*ABSOLUTE CAREGIVERS LLC*****SV*300024773~",
        f"HL*3*2*22*0~",
        f"TRN*1*93175-012552-3*9877281234~",
        f"NM1*IL*1******MI*{member_id}~",
        f"DTP*291*D8*{eligibility_date}~",
        f"EQ*30~"
    ]

    se_segment = f"SE*{len(transaction_segments) + 1}*1240~"
    
    payload_segments = [
        f"ISA*00*          *00*          *ZZ*A367           *ZZ*IHCP           *{isa_date_str}*{time_str}*^*00501*{control_number}*0*P*:~",
        f"GS*HS*A367*IHCP*{date_str}*{time_str}*{group_control_number}*X*005010X279A1~",
        *transaction_segments,
        se_segment,
        f"GE*1*{group_control_number}~",
        f"IEA*1*{control_number}~"
    ]
    
    # The payload should be a single string with segments separated by newlines
    return "\r\n".join(payload_segments)

# --- Function to send a single request ---
async def send_270_request(member_id: str, client: httpx.AsyncClient) -> Dict[str, Any]:
    """Sends a single X12 270 request for one member ID."""
    domain = "coresvc.indianamedicaid.com"
    url = f"https://{domain}/HP.Core.mime/CoreTransactions.aspx"
    password = os.getenv("HCP_PASSWORD") # IMPORTANT: Make sure HCP_PASSWORD is in your .env file

    if not password:
        return {
            "member_id": member_id,
            "status": "error",
            "details": {"error": "HCP_PASSWORD not found in environment variables."}
        }
        
    x12_payload = generate_x12_payload(member_id)

    # Mimic the form-data structure from the JS code
    form_data = {
        'PayloadType': 'X12_270_Request_005010X279A1',
        'ProcessingMode': 'RealTime',
        'PayloadID': str(uuid.uuid4()),
        'TimeStamp': datetime.utcnow().isoformat(),
        'UserName': 'asll4982',
        'Password': password,
        'SenderID': 'A367',
        'ReceiverID': 'IHCP',
        'CORERuleVersion': '2.2.0',
    }
    
    # The payload is sent as a file
    files = {'Payload': ('payload.x12', x12_payload, 'text/plain')}

    try:
        # Send the POST request
        response = await client.post(url, data=form_data, files=files, timeout=20.0)
        
        # Check if the request was successful
        response.raise_for_status() 
        
        # Here you would parse the response.data (which is a string)
        # For now, we just return a success message and the raw response
        return {
            "member_id": member_id,
            "status": "processed",
            "details": {"response_status_code": response.status_code, "response_body": response.text}
        }

    except httpx.RequestError as exc:
        # Handle connection errors, timeouts, etc.
        return {
            "member_id": member_id,
            "status": "error",
            "details": {"error": f"An error occurred while requesting {exc.request.url!r}.", "exception": str(exc)}
        }

# --- Main service function called by the API endpoint ---
async def process_x12_for_members(member_ids: List[str]) -> List[models.ProcessedMemberResult]:
    """
    Processes a list of member IDs by sending X12 requests asynchronously.
    """
    results = []
    # Create an httpx client that can be reused for all requests
    async with httpx.AsyncClient() as client:
        for member_id in member_ids:
            # Note: For real high-concurrency, you would use asyncio.gather here
            # For simplicity, we process them sequentially but asynchronously.
            result_data = await send_270_request(member_id, client)
            results.append(models.ProcessedMemberResult(**result_data))
            
    return results