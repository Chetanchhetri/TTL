from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from bson.objectid import ObjectId

# Ensure you import token_required from your decorators file
from decorators import collection, token_required 

todo_app = Blueprint('todo_app', __name__)
db = collection.database

def get_ist_time():
    return datetime.utcnow() + timedelta(hours=5, minutes=30)

# -------------------------------------------------------------
# 1. ADD ASSIGNMENT / TO-DO
# -------------------------------------------------------------
@todo_app.route('/api/todo/add', methods=['POST'])
@token_required
def add_todo(*args, **kwargs):
    data = request.json
    employee_id = data.get('employee_id')
    company = data.get('company')
    title = data.get('title')
    description = data.get('description', '')
    admin_id = data.get('admin_id') 

    if not employee_id or not company or not title:
        return jsonify({"error": "employee_id, company, and title are required"}), 400

    initial_status = "Pending_Acceptance" if admin_id else "Incomplete"

    new_task = {
        "employee_id": employee_id,
        "company": company,
        "admin_id": admin_id,
        "title": title,
        "description": description,
        "status": initial_status,
        "created_at": get_ist_time()
    }

    result = db.todos.insert_one(new_task)
    return jsonify({
        "status": True,
        "message": "Task added successfully",
        "task_id": str(result.inserted_id),
        "task_status": initial_status
    }), 201

# -------------------------------------------------------------
# 2. RESPOND TO ADMIN ASSIGNMENT
# -------------------------------------------------------------
@todo_app.route('/api/todo/respond', methods=['PATCH'])
@token_required
def respond_to_assignment(*args, **kwargs):
    data = request.json
    task_id = data.get('task_id')
    user_response = data.get('response') 

    if not task_id or not user_response:
        return jsonify({"error": "task_id and response are required"}), 400

    status_map = {
        "Accept": "Incomplete",       
        "Talk": "Talk_To_Manager",    
        "Reject": "Rejected"          
    }

    new_status = status_map.get(user_response)
    
    if not new_status:
        return jsonify({"error": "Invalid response. Use 'Accept', 'Talk', or 'Reject'."}), 400

    try:
        db.todos.update_one(
            {"_id": ObjectId(task_id)},
            {"$set": {"status": new_status, "updated_at": get_ist_time()}}
        )
        return jsonify({"status": True, "message": f"Task updated to {new_status}"}), 200
    except Exception as e:
        return jsonify({"error": "Invalid task_id format"}), 400

# -------------------------------------------------------------
# 3. MARK TASK COMPLETE / INCOMPLETE
# -------------------------------------------------------------
@todo_app.route('/api/todo/toggle_status', methods=['PATCH'])
@token_required
def toggle_todo_status(*args, **kwargs):
    data = request.json
    task_id = data.get('task_id')
    new_status = data.get('status') 

    if not task_id or not new_status:
        return jsonify({"error": "task_id and status are required"}), 400

    db.todos.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {"status": new_status, "updated_at": get_ist_time()}}
    )
    return jsonify({"status": True, "message": f"Task marked as {new_status}"}), 200

# -------------------------------------------------------------
# 4. GET ALL TO-DOS (WITH FILTERS & SORTING)
# -------------------------------------------------------------
@todo_app.route('/api/todo/list', methods=['POST'])
@token_required
def list_todos(*args, **kwargs):
    data = request.json
    employee_id = data.get('employee_id')
    company = data.get('company')
    filter_status = data.get('status')
    sort_order = data.get('sort_order', 'desc') 

    if not employee_id or not company:
        return jsonify({"error": "employee_id and company are required"}), 400

    query = {"employee_id": employee_id, "company": company}

    if filter_status:
        if isinstance(filter_status, list):
            query["status"] = {"$in": filter_status}
        else:
            query["status"] = filter_status

    sort_direction = -1 if sort_order == 'desc' else 1
    tasks = db.todos.find(query).sort("created_at", sort_direction)

    result = []
    for task in tasks:
        task["_id"] = str(task["_id"])
        task["created_at"] = task["created_at"].strftime('%Y-%m-%d %H:%M:%S')
        if "updated_at" in task:
            task["updated_at"] = task["updated_at"].strftime('%Y-%m-%d %H:%M:%S')
        result.append(task)

    return jsonify({"status": True, "count": len(result), "data": result}), 200