import os
import httpx
import uuid
import random
from datetime import datetime
from typing import List, Dict, Any

# --- Import new parsers ---
from requests_toolbelt.multipart import decoder
from badx12 import Parser as X12Parser

from ... import models
from dotenv import load_dotenv

load_dotenv()

# --- Helper function (no changes) ---
def generate_random_number(digits: int) -> int:
    min_val = 10**(digits - 1)
    max_val = (10**digits) - 1
    return random.randint(min_val, max_val)

# --- Helper function (no changes) ---
def generate_x12_payload(member_id: str) -> str:
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
    
    return "\r\n".join(payload_segments)

# --- NEW FUNCTION: To parse the server's response ---
def parse_x12_response(response: httpx.Response) -> Dict[str, Any]:
    """
    Parses the multipart/form-data response to extract and structure
    the X12 271 data.
    """
    try:
        # Decode the multipart response using the response's headers
        multipart_data = decoder.MultipartDecoder.from_response(response)
        
        parsed_response = {}
        x12_payload_str = ""

        # Extract data from each part of the multipart message
        for part in multipart_data.parts:
            # The header is bytes, so we decode it to a string to inspect it
            header_content_disposition = part.headers.get(b'content-disposition', b'').decode('utf-8')
            
            if 'name="Payload"' in header_content_disposition:
                # This is the X12 data, decode it from bytes to a string
                x12_payload_str = part.text
            elif 'name="ErrorCode"' in header_content_disposition:
                parsed_response['error_code'] = part.text
            elif 'name="ErrorMessage"' in header_content_disposition:
                parsed_response['error_message'] = part.text

        if x12_payload_str:
            # If we found an X12 payload, parse it to JSON
            x12_parser = X12Parser(x12_payload_str)
            # The .to_dict() method provides a clean dictionary representation
            parsed_response['x12_data'] = x12_parser.to_dict()
        else:
            # Handle cases where there might not be a payload (e.g., an initial error)
            parsed_response['x12_data'] = None

        return parsed_response

    except Exception as e:
        # If parsing fails for any reason, return the raw body for debugging
        return {"parsing_error": str(e), "raw_body": response.text}


# --- UPDATED FUNCTION: `send_270_request` to use the new parser ---
async def send_270_request(member_id: str, client: httpx.AsyncClient) -> Dict[str, Any]:
    """Sends a single X12 270 request and returns the parsed response."""
    domain = "coresvc.indianamedicaid.com"
    url = f"https://{domain}/HP.Core.mime/CoreTransactions.aspx"
    password = os.getenv("HCP_PASSWORD")

    if not password:
        return {
            "member_id": member_id, "status": "error",
            "details": {"error": "HCP_PASSWORD not found in environment variables."}
        }
        
    x12_payload = generate_x12_payload(member_id)

    form_data = {
        'PayloadType': 'X12_270_Request_005010X279A1', 'ProcessingMode': 'RealTime',
        'PayloadID': str(uuid.uuid4()), 'TimeStamp': datetime.utcnow().isoformat(),
        'UserName': 'asll4982', 'Password': password, 'SenderID': 'A367',
        'ReceiverID': 'IHCP', 'CORERuleVersion': '2.2.0',
    }
    
    files = {'Payload': ('payload.x12', x12_payload, 'text/plain')}

    try:
        response = await client.post(url, data=form_data, files=files, timeout=30.0)
        response.raise_for_status() 
        
        # *** Call the new parsing function here! ***
        parsed_details = parse_x12_response(response)
        
        return {
            "member_id": member_id,
            "status": "processed",
            "details": parsed_details
        }

    except httpx.RequestError as exc:
        return {
            "member_id": member_id, "status": "error",
            "details": {"error": f"An error occurred while requesting {exc.request.url!r}.", "exception": str(exc)}
        }

# --- Main service function (no changes) ---
async def process_x12_for_members(member_ids: List[str]) -> List[models.ProcessedMemberResult]:
    results = []
    async with httpx.AsyncClient() as client:
        for member_id in member_ids:
            result_data = await send_270_request(member_id, client)
            results.append(models.ProcessedMemberResult(**result_data))
    return results