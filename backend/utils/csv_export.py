import csv
import io
from typing import List


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
                convo.session_id, convo.started_at, convo.ended_at,
                convo.escalated, convo.customer_email, convo.rating,
                convo.message_count, "", "", "", ""
            ])
        for msg in msgs:
            writer.writerow([
                convo.session_id, convo.started_at, convo.ended_at,
                convo.escalated, convo.customer_email, convo.rating,
                convo.message_count, msg.role, msg.content,
                msg.was_auto_reply, msg.created_at
            ])

    return output.getvalue()
