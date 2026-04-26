import csv
import io
from typing import List


_FORMULA_LEAD = ("=", "+", "-", "@")


def _safe_cell(value):
    """Prefix a leading '=', '+', '-', or '@' with a single quote to neutralise Excel/Sheets formula injection."""
    if value is None:
        return ""
    s = str(value)
    if s and s[0] in _FORMULA_LEAD:
        return "'" + s
    return s


def generate_conversations_csv(conversations: list, messages_map: dict) -> str:
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "session_id", "started_at", "ended_at", "escalated",
        "customer_email", "rating", "message_count",
        "role", "content", "was_auto_reply", "message_at"
    ])

    for convo in conversations:
        msgs = messages_map.get(convo.id, [])
        if not msgs:
            writer.writerow([
                _safe_cell(convo.session_id), convo.started_at, convo.ended_at,
                convo.escalated, _safe_cell(convo.customer_email), convo.rating,
                convo.message_count, "", "", "", ""
            ])
        for msg in msgs:
            writer.writerow([
                _safe_cell(convo.session_id), convo.started_at, convo.ended_at,
                convo.escalated, _safe_cell(convo.customer_email), convo.rating,
                convo.message_count, _safe_cell(msg.role), _safe_cell(msg.content),
                msg.was_auto_reply, msg.created_at
            ])

    return output.getvalue()
