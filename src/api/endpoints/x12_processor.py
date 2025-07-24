# src/api/endpoints/x12_processor.py

import os
import httpx
import uuid
import random
from datetime import datetime
from typing import List, Dict, Any

from requests_toolbelt.multipart import decoder
from ... import models
from dotenv import load_dotenv

load_dotenv()

def simple_x12_to_json(x12_string: str) -> List[Dict[str, Any]]:
    """Converts a raw X12 string into a list of segment dictionaries."""
    segments = []
    for line in x12_string.strip().split('~'):
        if line:
            elements = line.strip().split('*')
            segments.append({"segment_id": elements[0], "elements": elements[1:]})
    return segments

# src/api/endpoints/x12_processor.py

def extract_final_result(member_id: str, parsed_x12: List[Dict[str, Any]]) -> models.FinalMemberResult:
    """Processes the list of X12 segments to build the final, flat response object."""
    patient_name = None
    mce = None
    waiver_status = "Not Eligible"
    coverage = None
    start_date = None
    end_date = None

    primary_eb_index = -1
    for i, segment in enumerate(parsed_x12):
        if (segment["segment_id"] == "EB" and
                len(segment["elements"]) > 4 and
                segment["elements"][0] == '1' and
                ("Waiver" in segment["elements"][4] or "HCBS" in segment["elements"][4])):
            primary_eb_index = i
            waiver_status = "Eligible"
            coverage = segment["elements"][4]
            break

    if primary_eb_index != -1:
        next_segment_index = primary_eb_index + 1
        if next_segment_index < len(parsed_x12):
            next_segment = parsed_x12[next_segment_index]
            if next_segment["segment_id"] == "DTP" and len(next_segment["elements"]) > 2:
                date_range = next_segment["elements"][2]
                if '-' in date_range:
                    parts = date_range.split('-')
                    start_date, end_date = parts[0], parts[1]
                else:
                    start_date = date_range

    for segment in parsed_x12:
        if segment["segment_id"] == "NM1" and len(segment["elements"]) > 1 and segment["elements"][0] == "IL":
            # Defensive coding to prevent index errors
            last_name = segment["elements"][2] if len(segment["elements"]) > 2 else ""
            first_name = segment["elements"][3] if len(segment["elements"]) > 3 else ""
            middle_initial = segment["elements"][4] if len(segment["elements"]) > 4 else ""
            
            name_parts = [first_name, middle_initial] if middle_initial else [first_name]
            patient_name = f"{last_name}, {' '.join(filter(None, name_parts))}"

        if segment["segment_id"] == "NM1" and len(segment["elements"]) > 2 and segment["elements"][0] == "P5":
            mce = segment["elements"][2]
            
    return models.FinalMemberResult(
        member_id=member_id, patient=patient_name, waiver_status=waiver_status,
        mce=mce, coverage=coverage, start_date=start_date, end_date=end_date,
    )
    
def parse_and_extract(member_id: str, response: httpx.Response) -> models.FinalMemberResult:
    """Parses the multipart response and extracts the final, clean result."""
    try:
        multipart_data = decoder.MultipartDecoder.from_response(response)
        x12_payload_str = ""
        for part in multipart_data.parts:
            header_disp = part.headers.get(b'content-disposition', b'').decode('utf-8')
            if 'name="Payload"' in header_disp:
                x12_payload_str = part.text
                break
        
        if x12_payload_str:
            parsed_x12 = simple_x12_to_json(x12_payload_str)
            return extract_final_result(member_id, parsed_x12)
        else:
            error_code, error_message = "Unknown", "No X12 Payload in Response"
            for part in multipart_data.parts:
                header_disp = part.headers.get(b'content-disposition', b'').decode('utf-8')
                if 'name="ErrorCode"' in header_disp: error_code = part.text
                if 'name="ErrorMessage"' in header_disp: error_message = part.text.strip()
            return models.FinalMemberResult(member_id=member_id, waiver_status=f"Error: {error_code} - {error_message}")
            
    except Exception as e:
        return models.FinalMemberResult(member_id=member_id, waiver_status=f"Error during parsing: {str(e)}")

def generate_x12_payload(member_id: str) -> str:
    """Generates the X12 270 request payload for a member."""
    now = datetime.utcnow()
    date_str, time_str, isa_date_str = now.strftime('%Y%m%d'), now.strftime('%H%M'), now.strftime('%y%m%d')
    control_number = f"1000{random.randint(10000, 99999)}"
    group_control_number = str(random.randint(10000, 99999))
    transaction_id = f"1000{random.randint(1000, 9999)}"
    
    segments = [
        "ST*270*1240*005010X279A1", f"BHT*0022*13*{transaction_id}*{date_str}*{time_str}",
        "HL*1**20*1", "NM1*PR*2*INDIANA HEALTH COVERAGE PROGRAM*****PI*IHCP",
        "HL*2*1*21*1", "NM1*1P*2*ABSOLUTE CAREGIVERS LLC*****SV*300024773",
        "HL*3*2*22*0", "TRN*1*93175-012552-3*9877281234",
        f"NM1*IL*1******MI*{member_id}", f"DTP*291*D8*{date_str}", "EQ*30"
    ]
    
    full_segments = [
        f"ISA*00*          *00*          *ZZ*A367           *ZZ*IHCP           *{isa_date_str}*{time_str}*^*00501*{control_number}*0*P*:",
        f"GS*HS*A367*IHCP*{date_str}*{time_str}*{group_control_number}*X*005010X279A1",
        *segments,
        f"SE*{len(segments) + 1}*1240",
        f"GE*1*{group_control_number}",
        f"IEA*1*{control_number}"
    ]
    return "~".join(full_segments) + "~"

async def send_270_request(member_id: str, client: httpx.AsyncClient) -> models.FinalMemberResult:
    """Sends a single 270 request and returns a clean, final result object."""
    url = "https://coresvc.indianamedicaid.com/HP.Core.mime/CoreTransactions.aspx"
    password = os.getenv("HCP_PASSWORD")
    if not password:
        return models.FinalMemberResult(member_id=member_id, waiver_status="Error: HCP_PASSWORD not configured.")

    form_data = {
        'PayloadType': 'X12_270_Request_005010X279A1', 'ProcessingMode': 'RealTime',
        'PayloadID': str(uuid.uuid4()), 'TimeStamp': datetime.utcnow().isoformat(), 'UserName': 'asll4982',
        'Password': password, 'SenderID': 'A367', 'ReceiverID': 'IHCP', 'CORERuleVersion': '2.2.0',
    }
    files = {'Payload': ('payload.x12', generate_x12_payload(member_id), 'text/plain')}

    try:
        response = await client.post(url, data=form_data, files=files, timeout=30.0)
        response.raise_for_status()
        return parse_and_extract(member_id, response)
    except httpx.RequestError as exc:
        return models.FinalMemberResult(member_id=member_id, waiver_status=f"Error: Request failed - {exc}")

async def process_x12_for_members(member_ids: List[str]) -> List[models.FinalMemberResult]:
    """Processes a list of member IDs and returns a list of final, clean results."""
    results = []
    async with httpx.AsyncClient() as client:
        for member_id in member_ids:
            result = await send_270_request(member_id, client)
            results.append(result)
    return results