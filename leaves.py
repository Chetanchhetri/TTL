from flask import Blueprint, request, jsonify
from datetime import datetime
from decorators import token_required, leaves_collection, find_user_info, notification_collection, token_required_admin, collection
import pytz, re
from bson import ObjectId
from pymongo import DESCENDING
from socketio_setup import socketio

leaves_app = Blueprint('leaves_app', __name__)

@leaves_app.route('/api/create_leaves', methods=['POST'])
@token_required
def create_leave_request(current_user):
    try:
        data = request.json
        # Extract data from the request
        leave_type = data.get('type')
        leave_start = data.get('leave_start')
        leave_end = data.get('leave_end')
        reason = data.get('reason')
        
        # Access 'time_zone' from the current_user dictionary
        # time_zone = current_user.get('time_zone', 'UTC')  # Default to 'UTC' if not present
        frontend_timezone = pytz.timezone(current_user.get('time_zone', 'UTC'))
        frontend_time = datetime.now(frontend_timezone)
        
        # Validation
        if not leave_type or not leave_start or not leave_end or not reason:
            return jsonify({"error": "All fields are required"}), 400

        try:
            # Parse the leave_start and leave_end to ensure they are valid dates
            leave_start = datetime.strptime(leave_start, '%Y-%m-%d')
            leave_end = datetime.strptime(leave_end, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "Invalid date format, should be YYYY-MM-DD"}), 400

        # Create the leave request document
        leave_request = {
            "user_id": current_user['_id'],
            "type": leave_type,
            "status":"Pending",
            "remark":"",
            "leave_start": leave_start,
            "leave_end": leave_end,
            "reason": reason,
            "company":current_user['company'],
            "created_at": frontend_time.strftime("%Y-%m-%d %H:%M:%S")
        }

        notification_data = {
            'user_id': str(current_user['_id']),
            'message': 'A new leave request has been created.',
            'timestamp': datetime.now(frontend_timezone),
            'isSeen': False,
            'adminSeen': False,
            'company': current_user['company'],
            'user_info': find_user_info(str(current_user['_id']))
        }

        notification_collection.insert_one(notification_data)
        notification_data['_id'] = str(notification_data['_id'])
        notification_data['timestamp'] = notification_data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')

        # Emitting a socket notification
        socketio.emit(f'notification_{current_user["company"]}', [notification_data], namespace='/socket_connection')

        # Insert the leave request into the database
        result = leaves_collection.insert_one(leave_request)

        return jsonify({"message": "Leave request created successfully", "leave_id": str(result.inserted_id)}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@leaves_app.route('/api/my_leaves', methods=['GET'])
@token_required
def get_leave_requests(current_user):
    try:
        user_id = request.args.get("user_id")
        if user_id:
            # Fetch leave requests for the specified user
            leave_requests = leaves_collection.find({"user_id": ObjectId(user_id)}).sort("created_at", DESCENDING)
        else:
            leave_requests = leaves_collection.find({"user_id": ObjectId(current_user['_id'])}).sort("created_at", DESCENDING)

        # Prepare the response data
        leaves_list = []
        for leave in leave_requests:
            leave['_id'] = str(leave['_id']) 
            leave['user_id'] = find_user_info(str(leave['user_id'])) 
            leave["leave_start"] = leave["leave_start"].strftime('%Y-%m-%d')
            leave["leave_end"]=  leave["leave_end"].strftime('%Y-%m-%d')
            leaves_list.append(leave)

        return jsonify({"data": leaves_list}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@leaves_app.route('/api/emp_leaves', methods=['GET'])
@token_required
def all_leave_requests(current_user):
    try:
        company = current_user['company']
        
        # Get filters from request parameters
        leave_type_filter = request.args.get('type', 'all').lower()
        leave_status_filter = request.args.get('status', 'all').lower()

        # Construct the query based on the filters
        query = {"company": company}
        if leave_type_filter == 'regular':
            query['type'] = 'regular'
        elif leave_type_filter == 'urgent':
            query['type'] = 'urgent'
        elif leave_type_filter != 'all':
            return jsonify({"error": "Invalid type filter"}), 400

        if leave_status_filter == 'accepted':
            query['status'] = 'Accepted'
        elif leave_status_filter == 'rejected':
            query['status'] = 'Rejected'
        elif leave_status_filter == 'pending':
            query['status'] = 'Pending'
        elif leave_status_filter != 'all':
            return jsonify({"error": "Invalid status filter"}), 400

        leave_requests = leaves_collection.find(query).sort("created_at", DESCENDING)

        # Prepare the response data
        leaves_list = []
        for leave in leave_requests:
            leave['_id'] = str(leave['_id'])
            leave['user_id'] = find_user_info(str(leave['user_id']))
            leave["leave_start"] = leave["leave_start"].strftime('%Y-%m-%d')
            leave["leave_end"] = leave["leave_end"].strftime('%Y-%m-%d')
            leaves_list.append(leave)

        return jsonify({"data": leaves_list}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@leaves_app.route('/api/change_leaves_status/<leave_id>', methods=['PUT'])
@token_required
def update_leave_request(current_user, leave_id):
    try:
        data = request.json
        # Extract data from the request
        new_status = data.get('status')
        remark = data.get('remark')

        # time_zone = current_user.get('time_zone', 'UTC')  # Default to 'UTC' if not present
        frontend_timezone = pytz.timezone(current_user.get('time_zone', 'UTC'))
        frontend_time = datetime.now(frontend_timezone)

        # Validation
        if not new_status:
            return jsonify({"error": "Status field is required"}), 400

        # Update the leave request document
        result = leaves_collection.update_one(
            {"_id": ObjectId(leave_id)},
            {"$set": {"status": new_status, "remark": remark, "updated_at": frontend_time.strftime("%Y-%m-%d %H:%M:%S")}}
        )

        if result.matched_count == 0:
            return jsonify({"error": "Leave request not found"}), 404

        # Fetch the updated leave request document
        updated_leave = leaves_collection.find_one({"_id": ObjectId(leave_id)})

        updated_leave_data = {
            "_id": str(updated_leave["_id"]),
            "user_id": find_user_info(str(updated_leave["user_id"])),
            "type": updated_leave["type"],
            "leave_start": updated_leave["leave_start"].strftime('%Y-%m-%d'),
            "leave_end": updated_leave["leave_end"].strftime('%Y-%m-%d'),
            "reason": updated_leave["reason"],
            "status": updated_leave["status"],
            "remark": updated_leave["remark"],
            "created_at": updated_leave["created_at"],
            "updated_at": updated_leave["updated_at"]
        }

        return jsonify({"message": "Leave request updated successfully", "data": updated_leave_data}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@leaves_app.route('/api/search-leaves', methods=['GET'])
@token_required_admin
def get_employee_leaves(current_user):
    try:
        company_id = current_user["company"]  # Get company ID from token
        employee_name = request.args.get('name', '').strip()
        page = int(request.args.get('page', 1))  # Default page 1
        limit = int(request.args.get('limit', 20))  # Default limit 10

        if not employee_name:
            return jsonify({"error": "Employee name is required"}), 400

        # Step 1: Find employees using case-insensitive regex (fuzzy search)
        employees_cursor = collection.find(
            {
                "company": company_id,
                "name": {"$regex": f".*{re.escape(employee_name)}.*", "$options": "i"}
            },
            {"_id": 1, "name": 1}  # Fetch only necessary fields
        )
        employees = list(employees_cursor)

        if not employees:
            return jsonify({"message": "No employees found with this name"}), 404

        employee_ids = [emp["_id"] for emp in employees]  # Extract employee IDs

        # Step 2: Find leaves for matching employees, sorted by company and leave date
        leaves_cursor = leaves_collection.find(
            {"user_id": {"$in": employee_ids}, "company": company_id}
        ).sort([ ("leave_start", DESCENDING)]).skip((page - 1) * limit).limit(limit)

        leaves = []
        for leave in leaves_cursor:
            leaves.append({
                "_id": str(leave["_id"]),
                "user_id": str(leave["user_id"]),
                "type": leave["type"],
                "status": leave["status"],
                "remark": leave.get("remark", ""),
                "leave_start": leave["leave_start"].strftime('%Y-%m-%d'),
                "leave_end": leave["leave_end"].strftime('%Y-%m-%d'),
                "reason": leave.get("reason", ""),
                "company": leave["company"],
                "created_at": leave["created_at"],
                "updated_at": leave["updated_at"]
            })

        return jsonify({
            "data": [{"_id": str(emp["_id"]), "name": emp["name"]} for emp in employees],
            "leaves": leaves,
            "page": page,
            "limit": limit,
            "total": len(leaves),
            "message": "Leaves fetched successfully"
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500