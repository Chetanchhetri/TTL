from flask import Blueprint, request, jsonify
from datetime import datetime
from decorators import collection 

attendance_app = Blueprint('attendance_app', __name__)
db = collection.database 

# -------------------------------------------------------------
# PUNCH IN ENDPOINT
# -------------------------------------------------------------
@attendance_app.route('/api/punch_in', methods=['POST'])
def punch_in():
    data = request.json
    employee_id = data.get('employee_id')
    company = data.get('company')

    if not employee_id or not company:
        return jsonify({"error": "employee_id and company are required"}), 400

    # Safety Guard: Check if the user is already punched in (has an unclosed shift)
    active_shift = db.attendance.find_one({
        "employee_id": employee_id,
        "company": company,
        "punch_out_time": None
    })

    if active_shift:
        return jsonify({
            "error": "User is already punched in. Please punch out of your current shift first."
        }), 400

    now = datetime.utcnow()
    
    new_shift = {
        "employee_id": employee_id,
        "company": company,
        "date": now.strftime('%Y-%m-%d'),
        "punch_in_time": now,
        "punch_out_time": None,
        "duration_seconds": 0,
        "duration_formatted": "00:00:00",
        "current_status": "Working", 
        "status_logs": [             
            {"status": "Working", "time": now}
        ]
    }

    db.attendance.insert_one(new_shift)
    
    return jsonify({
        "status": True,
        "message": "Punched in successfully",
        "time": now.strftime('%H:%M:%S')
    }), 201


# -------------------------------------------------------------
# UPDATE STATUS ENDPOINT (Break, Meeting, etc.)
# -------------------------------------------------------------
@attendance_app.route('/api/update_status', methods=['PATCH'])
def update_status():
    data = request.json
    employee_id = data.get('employee_id')
    company = data.get('company')
    new_status = data.get('status') # e.g., "On Break", "In Meeting", "Working"

    if not employee_id or not company or not new_status:
        return jsonify({"error": "employee_id, company, and status are required"}), 400

    # Find the active unclosed shift
    active_shift = db.attendance.find_one({
        "employee_id": employee_id,
        "company": company,
        "punch_out_time": None
    })

    if not active_shift:
        return jsonify({
            "error": "No active shift found. You must punch in first."
        }), 400

    now = datetime.utcnow()

    # Update current status and push to the timeline log
    db.attendance.update_one(
        {"_id": active_shift["_id"]},
        {
            "$set": {"current_status": new_status},
            "$push": {"status_logs": {"status": new_status, "time": now}}
        }
    )

    return jsonify({
        "status": True,
        "message": f"Status updated to {new_status}",
        "time": now.strftime('%H:%M:%S')
    }), 200


# -------------------------------------------------------------
# PUNCH OUT ENDPOINT
# -------------------------------------------------------------
@attendance_app.route('/api/punch_out', methods=['POST'])
def punch_out():
    data = request.json
    employee_id = data.get('employee_id')
    company = data.get('company')

    if not employee_id or not company:
        return jsonify({"error": "employee_id and company are required"}), 400

    active_shift = db.attendance.find_one({
        "employee_id": employee_id,
        "company": company,
        "punch_out_time": None
    })

    if not active_shift:
        return jsonify({
            "error": "No active punch-in session found. You must punch in first."
        }), 400

    punch_out_time = datetime.utcnow()
    punch_in_time = active_shift['punch_in_time']

    # Duration calculations
    duration_delta = punch_out_time - punch_in_time
    total_seconds = int(duration_delta.total_seconds())

    # Format seconds into HH:MM:SS
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    duration_formatted = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    # Update the existing record with closure details and final status
    db.attendance.update_one(
        {"_id": active_shift["_id"]},
        {
            "$set": {
                "punch_out_time": punch_out_time,
                "duration_seconds": total_seconds,
                "duration_formatted": duration_formatted,
                "current_status": "Punched Out" 
            },
            "$push": {"status_logs": {"status": "Punched Out", "time": punch_out_time}} 
        }
    )

    return jsonify({
        "status": True,
        "message": "Punched out successfully",
        "punch_out_time": punch_out_time.strftime('%H:%M:%S'),
        "work_duration": duration_formatted
    }), 200