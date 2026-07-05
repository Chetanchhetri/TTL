from flask import Blueprint, request, jsonify
from datetime import datetime
# Authentication decorators have been removed
from decorators import collection 

sticky_notes_bp = Blueprint('sticky_notes', __name__)
db = collection.database 

# -------------------------------------------------------------
# EMPLOYEE ROUTES (NO AUTHENTICATION)
# -------------------------------------------------------------

@sticky_notes_bp.route('/api/add_sticky_note', methods=['POST'])
def add_sticky_note():
    data = request.json
    content = data.get('content')
    color = data.get('color', '#FFFF88')
    
    # Manually extract the ID and company since there is no token
    employee_id = data.get('employee_id')
    company = data.get('company')

    if not content or not employee_id or not company:
        return jsonify({"error": "content, employee_id, and company are required"}), 400

    new_note = {
        "employee_id": employee_id,
        "company": company,
        "content": content,
        "color": color,
        "created_at": datetime.utcnow()
    }

    db.sticky_notes.insert_one(new_note)
    return jsonify({"message": "Sticky note created successfully"}), 201


@sticky_notes_bp.route('/api/my_sticky_notes', methods=['GET'])
def my_sticky_notes():
    # Pass employee_id as a query parameter (e.g., /api/my_sticky_notes?employee_id=123)
    employee_id = request.args.get('employee_id')
    
    if not employee_id:
        return jsonify({"error": "employee_id query parameter is required"}), 400

    notes = list(db.sticky_notes.find(
        {"employee_id": employee_id},
        {"_id": 0} 
    ))
    return jsonify({"sticky_notes": notes}), 200


# -------------------------------------------------------------
# ADMIN ROUTES (NO AUTHENTICATION)
# -------------------------------------------------------------

@sticky_notes_bp.route('/api/admin/employee_sticky_notes/<target_emp_id>', methods=['GET'])
def admin_view_sticky_notes(target_emp_id):
    # Pass company as a query parameter (e.g., /api/admin/employee_sticky_notes/123?company=CM001)
    company = request.args.get('company')
    
    if not company:
        return jsonify({"error": "company query parameter is required"}), 400

    notes = list(db.sticky_notes.find(
        {
            "employee_id": target_emp_id,
            "company": company 
        },
        {"_id": 0}
    ))
    return jsonify({"sticky_notes": notes}), 200


@sticky_notes_bp.route('/api/admin/add_sticky_note', methods=['POST'])
def admin_add_sticky_note():
    data = request.json
    content = data.get('content')
    color = data.get('color', '#FFFF88')
    
    # Manually extract the admin ID and company
    admin_id = data.get('admin_id')
    company = data.get('company')

    if not content or not admin_id or not company:
        return jsonify({"error": "content, admin_id, and company are required"}), 400

    new_note = {
        "admin_id": admin_id, 
        "company": company,
        "content": content,
        "color": color,
        "created_at": datetime.utcnow()
    }

    db.sticky_notes.insert_one(new_note)
    return jsonify({"message": "Admin sticky note created successfully"}), 201