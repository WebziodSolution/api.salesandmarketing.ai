import uuid
from datetime import datetime
import pytz
from typing import Union

def format_date(dt: Union[datetime, str], tz_name: str | None) -> str:
    if isinstance(dt, str):
        date_str = dt.strip()
        parsed = None
        try:
            parsed = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            pass
        
        if parsed is None:
            formats = [
                "%m/%d/%Y %H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
                "%m-%d-%Y %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S",
                "%m/%d/%Y %H:%M",
                "%Y-%m-%d %H:%M",
                "%m/%d/%Y",
                "%Y-%m-%d"
            ]
            for fmt in formats:
                try:
                    parsed = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    pass
        
        if parsed is None:
            raise ValueError(f"Invalid datetime string: {dt}")
        dt = parsed

    if tz_name:
        try:
            tz_map = {"Asia/Calcutta": "Asia/Kolkata", "Calcutta": "Asia/Kolkata", "Kolkata": "Asia/Kolkata"}
            resolved_tz = tz_map.get(tz_name, tz_name)
            tz = pytz.timezone(resolved_tz)
            if dt.tzinfo is None:
                dt = tz.localize(dt)
            else:
                dt = dt.astimezone(tz)
        except Exception:
            pass

    return dt.strftime("%Y%m%dT%H%M%S")

def generate_ics_file(ics_event_dto, file_path, site_name):
    """
    Manually generates an ICS file based on the logic in Java's ICS.java.
    Avoids external dependencies like 'icalendar'.
    """
    try:
        # ics_event_dto components: 
        # startDate, endDate (Date objects or ISO strings)
        # timeZone (String)
        # summary (String)
        # description (String)
        # replyToAdd (String)
        # memberName (String)
        # attendees (List of Strings)

        start_str = format_date(ics_event_dto.get('startDate'), ics_event_dto.get('timeZone'))
        end_str = format_date(ics_event_dto.get('endDate'), ics_event_dto.get('timeZone'))
        
        uid = str(uuid.uuid4())
        
        lines = [
            "BEGIN:VCALENDAR",
            f"PRODID:{site_name}",
            "VERSION:2.0",
            "CALSCALE:GREGORIAN",
            "BEGIN:VEVENT",
            f"DTSTART;TZID={ics_event_dto.get('timeZone')}:{start_str}",
            f"DTEND;TZID={ics_event_dto.get('timeZone')}:{end_str}",
            f"SUMMARY:{ics_event_dto.get('summary')}",
            f"UID:{uid}"
        ]
        
        if ics_event_dto.get('description'):
            lines.append(f"DESCRIPTION:{ics_event_dto.get('description')}")
            
        organizer = f"ORGANIZER;CN={ics_event_dto.get('memberName')}:mailto:{ics_event_dto.get('replyToAdd')}"
        lines.append(organizer)
        
        for attendee_email in ics_event_dto.get('attendees', []):
            lines.append(f"ATTENDEE;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;CN={attendee_email};X-NUM-GUESTS=0:mailto:{attendee_email}")
            
        lines.append("END:VEVENT")
        lines.append("END:VCALENDAR")
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\r\n".join(lines) + "\r\n")
            
        return True
    except Exception as e:
        import logging
        logging.error(f"Error generating ICS file: {e}")
        return False
