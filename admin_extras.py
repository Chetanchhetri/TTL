import re
from flask import Blueprint, request, jsonify
from socketio_setup import socketio
from bson import ObjectId
import pytz, json
from datetime import datetime,timezone,timedelta
from pymongo import DESCENDING

from decorators import plans_collection ,collection,token_required_admin,find_user_info, company_collection, notice_collection, token_required ,get_emp_list, process_time_entry, deleted_employees_collection

admin_extras_app = Blueprint('admin_extras_app',__name__)

@admin_extras_app.route('/api/know_plans', methods=['GET'])
def know_plans():
    company_code = request.args.get('company_code')

    # company = company_collection.find_one({'company': company_code})
    company_plans = []
    all_plans = plans_collection.find({}).sort("cost", 1)
    if company_code:
        for plan in all_plans:
            if 'specified' in plan and company_code in plan['specified']:
                _id = str(plan['_id'])
                plan['_id'] = _id
                company_plans.append(plan)
            elif 'specified' not in plan:
                _id = str(plan['_id'])
                plan['_id'] = _id
                company_plans.append(plan)                
    else:
        for plan in all_plans:
            if 'specified' in plan and len(plan['specified']) == 0:
                _id = str(plan['_id'])
                plan['_id'] = _id
                company_plans.append(plan)
    return jsonify(company_plans), 200

@admin_extras_app.route('/api/employees_activity/monthly_data', methods=['GET'])
@token_required_admin
def get_monthly_data(current_user):
    try:
        company_name = current_user["company"]

        # Fetch employees list from the company entity
        company_entity = company_collection.find_one({'company': company_name}, {'empList': 1})
        emp_list = company_entity.get('empList', []) or []  # ✅ Fix 1: Ensure emp_list is a list
        if not emp_list:
            return jsonify({"employees": [], "total": 0})

        # Get month and date filters
        month = request.args.get('month')
        date = request.args.get('date')

        # Convert date filter to the required format
        start_date, end_date, entry_month = None, None, None
        if date:
            try:
                date_obj = datetime.strptime(date, '%Y-%m-%d')
                entry_month = date_obj.strftime('%Y-%m')
            except ValueError:
                return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
        elif month:
            try:
                start_date = datetime.strptime(month, '%Y-%m')
                end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                month_str = start_date.strftime('%Y-%m')
            except ValueError:
                return jsonify({"error": "Invalid month format. Use YYYY-MM"}), 400

        # Fetch employees and filter time_tracking in MongoDB
        users = list(collection.find(
            {'_id': {'$in': [ObjectId(eid) for eid in emp_list]}},
            {
                'name': 1,
                'profile_pic': 1,
                'job': 1,
                '_id': 1,
                'time_tracking': {
                    '$filter': {
                        'input': "$time_tracking",
                        'as': "entry",
                        'cond': {
                            '$and': [
                                {'$gte': ["$$entry.date", date]} if date else {'$gte': ["$$entry.date", start_date.strftime('%Y-%m-%d')]},
                                {'$lte': ["$$entry.date", date]} if date else {'$lte': ["$$entry.date", end_date.strftime('%Y-%m-%d')]}
                            ]
                        }
                    }
                }
            }
        )) or []  # ✅ Fix 2: Ensure users is a list

        monthly_data = []

        for user in users:
            employee_data = {
                "_id": str(user["_id"]),
                "name": user.get("name"),
                "profile_pic": user.get("profile_pic"),
                "job": user.get("job"),
                "monthly_details": {}
            }

            # ✅ Fix 3: Ensure time_tracking is always a list
            time_tracking = user.get("time_tracking") or []

            # Process filtered time_tracking data
            for entry in time_tracking:
                entry_date_str = entry.get('date', '')
                entry_month = entry_date_str[:7]  # Extract YYYY-MM format

                if date and entry_date_str == date and (entry.get('start_time') or entry.get('total_elapsed_time')):
                    process_time_entry(entry, employee_data, current_user['time_zone'])
                    employee_data['start_time'] = entry.get('start_time', '00:00:00')

                elif month and entry_month == month_str and (entry.get('start_time') or entry.get('total_elapsed_time')):
                    process_time_entry(entry, employee_data, current_user['time_zone'])

            if employee_data["monthly_details"]:
                monthly_data.append(employee_data)

        return jsonify({"employees": monthly_data, "total": len(monthly_data)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_extras_app.route('/api/employee_times', methods=['GET'])
@token_required_admin
def get_employee_data(current_user):
    try:
        # Get employee_id from request arguments
        employee_id = request.args.get('employee_id')

        frontend_timezone = pytz.timezone(current_user['time_zone'])
        frontend_time = datetime.now(frontend_timezone)
        # Get current date and time
        current_date = frontend_time.strftime("%Y-%m-%d")

        # Retrieve user document
        user = collection.find_one({"_id": ObjectId(employee_id)})
        if not user:
            return jsonify({
                'start_time': '00:00:00',
                'active_time': '00:00:00',
                'end_time': '',
                'inactive_time': '00:00:00',
                'call_time': '00:00:00'
            })

        time_tracking_list = user.get("time_tracking", [])
        
        # Iterate over time_tracking_list to find entry for the current date
        entry = next((entry for entry in time_tracking_list if entry.get('date') == current_date), None)

        def format_time(seconds):
            hours, remainder = divmod(seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            return '{:02d}:{:02d}:{:02d}'.format(int(hours), int(minutes), int(seconds))

        if entry:
            employee_monthly_data = {
                'monthly_details': {}
            }
            process_time_entry(entry, employee_monthly_data, current_user['time_zone'])
            entry_month = datetime.strptime(entry.get('date', ''), '%Y-%m-%d').strftime('%Y-%m')
            return jsonify({
                'start_time': entry.get('start_time', '00:00:00'),
                'active_time': entry.get('total_elapsed_time', '00:00:00'),
                'end_time': entry.get('end_time', ''),
                'inactive_time': format_time(employee_monthly_data['monthly_details'][entry_month]['inactive_time']),
                'call_time': entry.get('call_time', '00:00:00')
            })
        else:
            # If entry for current date not found, return default values
            return jsonify({
                'start_time': '00:00:00',
                'active_time': '00:00:00',
                'end_time': '',
                'inactive_time': '00:00:00',
                'call_time': '00:00:00'
            })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_extras_app.route('/api/add_email_stats', methods=['POST'])
@token_required_admin
def add_email_stats(current_user):
    try:
        company_id = current_user["company"]
        data = request.json
        email_stats = data.get('email_stats')
        email_cred = data.get('email_cred')
        if not company_id or not email_stats:
            return jsonify({'message': 'Missing company_id or email_stats parameter'}), 400

        # Update the company document with new email stats
        result = company_collection.update_one(
            {'company': company_id},
            {'$set': {'email_stats': email_stats, 'email_cred': email_cred}}
        )

        if result.modified_count > 0:
            return jsonify({'message': 'Email stats added successfully'}), 200
        else:
            return jsonify({'message': 'Already Same Credentials'}), 500

    except Exception as e:
        return jsonify({'message': str(e)}), 500
        
@admin_extras_app.route('/api/all_notes_last_15_days', methods=['GET'])
@token_required_admin
def all_notes_last_15_days(current_user):
    try:
        company_name = current_user['company']

        # Get optional start_date and end_date query parameters
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')

        # Default to last 15 days if dates are not provided
        if start_date_str and end_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            except ValueError:
                return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400
        else:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=14)

        start_date_iso = start_date.strftime('%Y-%m-%d')
        end_date_iso = end_date.strftime('%Y-%m-%d')

        # Fetch company entity once
        company_entity = company_collection.find_one({'company': company_name}, {'empList': 1})
        if not company_entity:
            return jsonify({"error": "Company not found"}), 404

        employee_ids = company_entity.get('empList', [])
        if not employee_ids:
            return jsonify([]), 200  # Return empty list if no employees exist

        # Fetch employees with only relevant time_tracking data
        employees = list(collection.find(
            {'_id': {'$in': [ObjectId(eid) for eid in employee_ids]}},
            {
                'name': 1,
                'profile_pic': 1,
                'job': 1,
                '_id': 1,
                'time_tracking': {
                    '$ifNull': [
                        {
                            '$filter': {
                                'input': "$time_tracking",
                                'as': "entry",
                                'cond': {
                                    '$and': [
                                        {'$gte': ["$$entry.date", start_date_iso]},
                                        {'$lte': ["$$entry.date", end_date_iso]}
                                    ]
                                }
                            }
                        },
                        []
                    ]
                }
            }
        ))

        all_notes = []

        for user in employees:
            user_info = {
                '_id': str(user['_id']),
                'name': user.get('name', ''),
                'profile_pic': user.get('profile_pic', ''),
                'job': user.get('job', '')
            }

            # Ensure time_tracking is always a list
            for entry in user.get("time_tracking", []):  # ✅ Safely iterate over an empty list if needed
                entry_date_str = entry.get('date', '')
                notes = entry.get('notes', [])

                for note in notes:
                    parts = note.split(': ', 1)
                    if len(parts) == 2:
                        timestamp, note_content = parts
                        all_notes.append({
                            'employee_details': user_info,
                            'date': entry_date_str,
                            'notes': {
                                'timestamp': timestamp,
                                'note_content': note_content
                            }
                        })

        # Sort all_notes by date and timestamp in descending order
        all_notes_sorted = sorted(
            all_notes, 
            key=lambda x: (datetime.strptime(x['date'], '%Y-%m-%d'), datetime.strptime(x['notes']['timestamp'], '%H:%M:%S')),
            reverse=True
        )

        return jsonify(all_notes_sorted), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    
@admin_extras_app.route('/api/employee_notes', methods=['GET'])
@token_required
def get_employee_notes(current_user):
    try:
        employee_id = request.args.get('employee_id')

        if not employee_id:
            employee_id = current_user['_id']
            if not employee_id:
                return jsonify({'error': 'Employee ID is required'}), 400

        # Fetch the employee from MongoDB
        employee = collection.find_one({"_id": ObjectId(employee_id)})
        if not employee:
            return jsonify({'error': 'Employee not found'}), 404

        # Extract notes from the employee's time_tracking data
        time_tracking = employee.get('time_tracking', [])
        notes = []

        for entry in time_tracking:
            entry_date = entry.get('date')
            entry_notes = entry.get('notes', [])

            for note in entry_notes:
                timestamp, note_content = note.split(': ', 1)
                notes.append({
                    'date': entry_date,
                    'timestamp': timestamp,
                    'note': note_content
                })

        # Sort notes by date and timestamp in descending order
        sorted_notes = sorted(notes, key=lambda x: (x['date'], datetime.strptime(x['timestamp'], '%H:%M:%S')), reverse=True)

        # Prepare structured response with notes grouped by date
        response_data = []
        current_date = None
        current_group = None

        for note in sorted_notes:
            if note['date'] != current_date:
                if current_group:
                    response_data.append(current_group)
                current_date = note['date']
                current_group = {'date': current_date, 'notes': []}
            current_group['notes'].append(note['timestamp'] + ': ' + note['note'])

        # Append the last group
        if current_group:
            response_data.append(current_group)

        return jsonify({'notes': response_data})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_extras_app.route('/api/update_holiday_list', methods=['POST'])
@token_required_admin
def update_company_holiday_list(current_user):
    # Retrieve company_code and holiday_list from request data
    data = request.json
    company_code = current_user['company']
    holiday_list = data.get('holiday_list')

    # Validate input
    if not company_code or not holiday_list:
        return jsonify({'status': False, 'message': 'Company code and holiday list are required.'}), 400
    
    # Validate holiday_list format
    for holiday in holiday_list:
        if 'date' not in holiday or 'name' not in holiday:
            return jsonify({'status': False, 'message': 'Each holiday must include a "date" and "name" field.'}), 400

        try:
            datetime.strptime(holiday['date'], '%Y-%m-%d')
        except ValueError:
            return jsonify({'status': False, 'message': f'Invalid date format in holiday: {holiday["date"]}. Use YYYY-MM-DD format.'}), 400

    # Find the company document and update the holiday list
    result = company_collection.update_one(
        {'company': company_code},
        {'$set': {'holiday_list': holiday_list}},
        upsert=False
    )

    # Check if company was found and updated
    if result.matched_count == 0:
        return jsonify({'status': False, 'message': 'Company not found.'}), 404

    return jsonify({
        'status': True,
        'message': 'Holiday list updated successfully.',
        'data': {
            'company_code': company_code,
            'holiday_list': holiday_list
        }
    }), 200

@admin_extras_app.route('/api/get_holiday_list', methods=['GET'])
def get_company_holiday_list():
    # Retrieve company_code and optional filter for upcoming holidays
    company_code = request.args.get('company')
    view_upcoming = request.args.get('view_upcoming', 'false').lower() == 'true'
    
    # Validate input
    if not company_code:
        return jsonify({'status': False, 'message': 'Company code is required.'}), 400

    # Find the company document
    company = company_collection.find_one({'company': company_code}, {'holiday_list': 1})
    
    if not company:
        return jsonify({'status': False, 'message': 'Company not found.'}), 404

    # Retrieve the holiday list
    holiday_list = company.get('holiday_list', [])

    # Filter upcoming holidays if the filter is applied
    if view_upcoming:
        current_date = datetime.now()
        holiday_list = [
            holiday for holiday in holiday_list
            if datetime.strptime(holiday['date'], '%Y-%m-%d') > current_date
        ]

    # Sort the holidays by date in ascending order
    holiday_list.sort(key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'))

    return jsonify({
        'status': True,
        'message': 'Holiday list fetched successfully.',
        'data': {
            'company_code': company_code,
            'holiday_list': holiday_list
        }
    }), 200


@admin_extras_app.route("/api/search_employees", methods=["GET"])
@token_required_admin
def search_employees(current_user):
    company_code = current_user.get("company") 

    search_query = request.args.get("query", "").strip()
    search_key = request.args.get("key", "").strip()  
    filters = {key: request.args.get(key) for key in ["name", "email", "job", "department", "phone", "address", "bio","employee_id"] if request.args.get(key)}
    gender = request.args.get("gender", "").strip()  
    query = {"company": company_code}

    if filters:
        query.update(filters)

    if gender:
        query["gender"] = gender

    if search_query and search_key:
        regex_pattern = re.compile(f".*{re.escape(search_query)}.*", re.IGNORECASE)
        query[search_key] = regex_pattern

    elif search_query:
        regex_pattern = re.compile(f".*{re.escape(search_query)}.*", re.IGNORECASE)
        query["$or"] = [
            {"name": regex_pattern},
            {"email": regex_pattern},
            {"job": regex_pattern},
            {"department": regex_pattern},
            {"address": regex_pattern},
            {"phone": regex_pattern},
            {"bio": regex_pattern},
            {"employee_id": regex_pattern}
        ]

    employees = list(collection.find(query, {"password": 0, "time_tracking": 0}))  # Exclude password field for security
    deleted_employees = list(deleted_employees_collection.find(query, {"password": 0, "time_tracking": 0}))


    for emp in employees + deleted_employees:
        emp["_id"] = str(emp["_id"])

    all_employees = employees + deleted_employees

    for emp in employees:
        emp["_id"] = str(emp["_id"])
        if 'deleted_at' in emp:
            emp['deleted_at'] = str(emp['deleted_at'])
        else:
            emp['deleted_at'] = None

    return jsonify({"status": True, "message": "Employees fetched successfully", "data": all_employees}), 200

@socketio.on('get_notice_history', namespace='/socket_connection')
def handle_fetch_notices_connect(data):
    notices = list(notice_collection.find({}, {'_id': 0}).sort('date', -1))
    socketio.emit('notices_data', {'notices': notices}, namespace='/socket_connection')


@socketio.on('send_notice', namespace='/socket_connection')
def handle_save_notice(data):
    notice_text = data.get('notice_text')
    datetime = data.get('datetime')
    
    if notice_text:
        notice_data = {
            'date': datetime,
            'text': notice_text
        }
        notice_data2 = {
            'date': datetime,
            'text': notice_text
        }
        notice_collection.insert_one(notice_data)

        # Broadcast the new notice to all connected clients in the 'fetch_notices' namespace
        # notices = list(notice_collection.find({}, {'_id': 0}))
        socketio.emit('notices_data', {'notices': notice_data2}, namespace='/socket_connection')


@socketio.on('get_all_notes', namespace='/socket_connection')
def get_all_notes(company_name):
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=14)

        company_entity = company_collection.find_one({'company': company_name})
        all_notes = []

        # Iterate over each employee in the company
        for employee_id in company_entity.get('empList', []):
            user = collection.find_one({"_id": ObjectId(employee_id)})
            if user:
                # Fetch user info for the employee
                user_info = find_user_info(employee_id)

                # Iterate over each entry in the time_tracking list
                for entry in user.get("time_tracking", []):
                    entry_date_str = entry.get('date', '')
                    if entry_date_str:
                        entry_date = datetime.strptime(entry_date_str, '%Y-%m-%d')

                        # Check if the entry date is within the last 15 days
                        if start_date <= entry_date <= end_date:
                            notes = entry.get('notes', [])
                            for note in notes:
                                # Extract timestamp and note content
                                timestamp, note_content = note.split(': ', 1)
                                all_notes.append({
                                    'employee_details': user_info,
                                    'date': entry_date_str,
                                    'notes': {
                                    'timestamp': timestamp,
                                    'note_content': note_content
                                    }
                                })

        # Sort all_notes by date in decreasing order
        all_notes_sorted = sorted(all_notes, key=lambda x: (datetime.strptime(x['date'], '%Y-%m-%d'), datetime.strptime(x['notes']['timestamp'], '%H:%M:%S')), reverse=True)

        socketio.emit('notes_data', [all_notes_sorted], namespace='/socket_connection')

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

# Socket event for announcements
@socketio.on('create_announcement', namespace='/socket_connection')
def handle_create_announcement(data):
    try:
        data = json.loads(str(data))
        senderId = data.get('senderId')
        userType = data.get('userType')  # "all" or "list"
        empList = data.get('empList', [])  # Employee list for specific employees
        announcement = data.get('announcement')
        company = data.get('company')

        # Extract timezone from company 
        timeZone = company_collection.find_one({"company": company}).get('time_zone')

        frontend_timezone = pytz.timezone(timeZone)
        frontend_time = datetime.now(frontend_timezone)
        today = frontend_time.strftime("%Y-%m-%d %H:%M:%S")

        # Create announcement data
        announcement_data = {
            'senderId': senderId,
            'userType': userType,
            'empList': empList,
            'datetime': today,  # Store current UTC time
            'announcement': announcement,
            'company': company
        }

        # Function to populate empList dynamically
        def populate_empList(emp_ids):
            populated_list = []
            for emp_id in emp_ids:
                employee_info = find_user_info(emp_id)  # Fetch employee info from your custom function
                if employee_info:
                    populated_list.append(employee_info)
            return populated_list

        # If userType is "all", emit to all employees of the company
        if userType == "all":
            # Fetch company data from the database
            company_data = company_collection.find_one({"company": company})
            if company_data and 'empList' in company_data:
                populated_empList = []  # Populate all employees of the company
                populated_announcement = {**announcement_data, 'empList': populated_empList}

                for empId in company_data['empList']:
                    socketio.emit(f'announce_{empId}', {"status": True, "announcements": [populated_announcement]}, namespace='/socket_connection')

        # If userType is "list", emit to specific employees in the empList
        if userType == "list" and empList:
            populated_empList = populate_empList(empList)  # Populate specific employees
            populated_announcement = {**announcement_data, 'empList': populated_empList}

            for empId in empList:
                socketio.emit(f'announce_{empId}', {"status": True, "announcements": [populated_announcement]}, namespace='/socket_connection')

        # Store the original announcement without populated empList
        notice_collection.insert_one(announcement_data)

        # Emit a confirmation back to the admin
        socketio.emit(f'announcement_created_{company}', {'status': True, 'message': 'Announcement created successfully', 'announcements': populated_announcement}, namespace='/socket_connection')

        # # Emit populated announcement data to the admin as well
        # socketio.emit(f'admin_announcements_fetched_{company}', {'status': True, 'announcements': [populated_announcement]}, namespace='/socket_connection')

    except Exception as e:
        print(f"Error: {str(e)}")
        socketio.emit(f'announcement_created_{company}', {'status': False, 'message': f"Error: {str(e)}"}, namespace='/socket_connection')

# Socket event to fetch previous announcements
@socketio.on('fetch_announcements', namespace='/socket_connection')
def handle_fetch_announcements(data):
    try:
        data = json.loads(str(data))
        employeeId = data.get('employeeId')
        company = data.get('company')

        if not employeeId or not company:
            socketio.emit('announcements_fetched', {'status': False, 'message': 'Invalid employeeId or company'})
            return

        # Query to fetch announcements for the given company
        announcements = notice_collection.find({'company': company})

        # List to store relevant announcements for the employee
        relevant_announcements = []

        # Iterate through the announcements and filter based on userType
        for announcement in announcements:
            userType = announcement.get('userType')

            if userType == 'all':
                # Include announcements for all employees
                relevant_announcements.append(announcement)
            elif userType == 'list':
                # Check if employeeId is in the list for userType 'list'
                empList = announcement.get('empList', [])
                if employeeId in empList:
                    relevant_announcements.append(announcement)

        # Convert ObjectId to string and remove unnecessary fields before sending to the client
        for announcement in relevant_announcements:
            announcement['_id'] = str(announcement['_id'])

        # Sort announcements by 'datetime' in descending order
        relevant_announcements.sort(key=lambda x: x['datetime'], reverse=True)

        # Emit the filtered announcements back to the client
        socketio.emit(f'announce_{employeeId}', {'status': True, 'announcements': relevant_announcements}, namespace='/socket_connection')

    except Exception as e:
        socketio.emit(f'announce_{employeeId}', {'status': False, 'message': f"Error: {str(e)}"}, namespace='/socket_connection')


@socketio.on('admin_fetch_announcements', namespace='/socket_connection')
def handle_admin_fetch_announcements(data):
    try:
        data = json.loads(str(data))
        company = data.get('company')
        page = int(data.get('page', 1))  # Default page is 1
        limit = int(data.get('limit', 10))  # Default limit is 10

        if not company:
            socketio.emit(f'admin_announcements_fetched_{company}', {'status': False, 'message': 'Invalid company'}, namespace='/socket_connection')
            return

        # Pagination parameters
        skip = (page - 1) * limit

        # Fetch all announcements for the company with pagination
        announcements_cursor = notice_collection.find({'company': company}).sort('datetime', DESCENDING).skip(skip).limit(limit)

        # List to store all announcements with populated employee info
        announcements_with_emp_info = []

        # Function to populate empList dynamically
        def populate_empList(emp_ids):
            populated_list = []
            for emp_id in emp_ids:
                employee_info = find_user_info(emp_id)  # Fetch employee info from your custom function
                if employee_info:
                    populated_list.append(employee_info)
            return populated_list

        for announcement in announcements_cursor:
            empList = announcement.get('empList', [])
            userType = announcement.get('userType', '')

            # # Check if userType is "all"
            # if userType == "all":
            #     # Fetch company data from the database
            #     company_data = company_collection.find_one({"company": company})
            #     if company_data and 'empList' in company_data:
            #         # Populate all employees of the company
            #         populated_empList = populate_empList(company_data['empList'])
            #         announcement['empList'] = populated_empList

            # If userType is "list", populate empList with employee information
            if userType == "list" and empList:
                populated_empList = populate_empList(empList)
                announcement['empList'] = populated_empList

            # Convert ObjectId to string for the announcement ID
            announcement['_id'] = str(announcement['_id'])
            announcements_with_emp_info.append(announcement)

        # Emit the announcements back to the admin with pagination details
        socketio.emit(f'admin_announcements_fetched_{company}', {
            'status': True, 
            'announcements': announcements_with_emp_info, 
            'page': page, 
            'limit': limit
        }, namespace='/socket_connection')
    except Exception as e:
        socketio.emit(f'admin_announcements_fetched_{company}', {'status': False, 'message': f"Error: {str(e)}"}, namespace='/socket_connection')


@socketio.on('delete_announcement', namespace='/socket_connection')
def handle_delete_announcement(data):
    try:
        data = json.loads(str(data))
        announcement_id = data.get('announcementId')
        company = data.get('company')

        if not announcement_id:
            socketio.emit(f'announcement_deleted_{company}', {
                'status': False,
                'message': 'announcementId is required'
            }, namespace='/socket_connection')
            return

        # Find the announcement first
        announcement = notice_collection.find_one({'_id': ObjectId(announcement_id)})
        if not announcement:
            socketio.emit(f'announcement_deleted_{company}', {
                'status': False,
                'message': 'Announcement not found'
            }, namespace='/socket_connection')
            return

        # Extract company and userType for broadcasting
        userType = announcement['userType']
        empList = announcement.get('empList', [])

        # Delete the announcement from DB
        result = notice_collection.delete_one({'_id': ObjectId(announcement_id)})

        if result.deleted_count == 0:
            socketio.emit(f'announcement_deleted_{company}', {
                'status': False,
                'message': 'Failed to delete announcement'
            }, namespace='/socket_connection')
            return

        # Broadcast to users
        if userType == 'all':
            company_data = company_collection.find_one({'company': company})
            if company_data and 'empList' in company_data:
                for empId in company_data['empList']:
                    socketio.emit(f'announcement_deleted_{empId}', {
                        'status': True,
                        'announcementId': announcement_id
                    }, namespace='/socket_connection')
        elif userType == 'list':
            for empId in empList:
                socketio.emit(f'announcement_deleted_{empId}', {
                    'status': True,
                    'announcementId': announcement_id
                }, namespace='/socket_connection')

        # Optional: notify admin panel
        socketio.emit(f'announcement_deleted_{company}', {
            'status': True,
            'announcementId': announcement_id,
            'message': 'Announcement deleted successfully'
        }, namespace='/socket_connection')

    except Exception as e:
        print(f"Error deleting announcement: {str(e)}")
        socketio.emit(f'announcement_deleted_{company}', {
            'status': False,
            'message': f"Internal error: {str(e)}"
        }, namespace='/socket_connection')
