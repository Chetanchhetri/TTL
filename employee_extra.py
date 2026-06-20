from flask import Blueprint, request, jsonify
import pytz, pymongo
from socketio_setup import socketio
from bson import ObjectId
from dateutil.relativedelta import relativedelta
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, datetime, timedelta
from calendar import monthrange

from decorators import token_required, collection, company_collection, notification_collection, find_user_info, moms_collection, upload_to_firebase, get_user_ip_and_location

employee_extra_app = Blueprint('employee_extra_app',__name__) 

@employee_extra_app.route('/api/health',methods=['GET'])
def index():
    return jsonify({"message":"Time Tracking Backend is running v1.2.5 updated at 28th July 2025 on 01:00 IST"})

@employee_extra_app.route('/api/user-ip-location')
def user_ip_location():
    result = get_user_ip_and_location()
    return result

@employee_extra_app.route('/api/verify-token', methods=['GET'])
@token_required
def verify_token(current_user):
    try:
        company = current_user.get('company')
        company_details = company_collection.find_one({'company': company}, {'_id': 0, 'time_zone': 1, 'departments': 1})
        return jsonify({
            'message': 'Token is valid',
            'data':{
                'user_id': str(current_user['_id']),
                'company': current_user.get('company'),
                'time_zone': current_user.get('time_zone'),
                'departments': company_details.get('departments'),
            },
            'status': True
        }), 200
    except Exception as e:
        return jsonify({'message': str(e), 'status': False}), 500

@employee_extra_app.route('/api/refresh',methods=['GET'])
@token_required
def refresh(current_user):
    try:
        _id = str(current_user['_id'])
        company = str(current_user['company'])
        time_zone = current_user.get('time_zone', 'Asia/Kolkata')

        # Set timezone and get current time
        frontend_timezone = pytz.timezone(time_zone)
        frontend_time = datetime.now(frontend_timezone)
        today = frontend_time.strftime("%Y-%m-%d")

        # Fetch user details
        details = collection.find_one(
            {'_id': ObjectId(_id)},
            {
                'company':1,'employee_id':1,
                'name': 1,
                'email': 1,
                'phone': 1,
                'gender': 1,
                'dob': 1,
                'bio': 1,
                'department': 1,
                'job': 1,
                'access': 1,
                'userType': 1,
                'hourlyEmp': 1,
                '_id': 0,
                'profile_pic': 1
            }
        )
        details['id'] = _id
        details['userType'] = details.get('userType', 'normal')

        # Fetch time tracking information
        entry = collection.find_one({"_id": ObjectId(_id), "time_tracking.date": today})
        status = "Allowed"
        default_time = '00:00:00'
        call_time = elapsed_time = total_elapsed_time = default_time
        responses = []
        start_time = default_time

        if entry:
            time_tracking_data = entry.get('time_tracking', [])
            for time_entry in time_tracking_data:
                if time_entry.get('date') == today:
                    call_time = time_entry.get('call_time', default_time)
                    elapsed_time = time_entry.get('elapsed_time', default_time)
                    total_elapsed_time = time_entry.get('total_elapsed_time', default_time)
                    total_response = time_entry.get('Responses', 0)
                    start_time = time_entry.get('start_time', default_time)
                    responses = [time_entry.get(f'Response{i}', '') for i in range(1, total_response + 1) if time_entry.get(f'Response{i}')]
                    break

            for time_entry in time_tracking_data:
                if time_entry.get('date') == today and "end_time" in time_entry:
                    status = "Not Allowed"
                    break

        # Prepare the response similar to /login, without the token
        return jsonify({
            "details": details,
            "entry": status,
            "offline_data": {
                "response": responses,
                "startTime": start_time
            },
            "times": {
                "call_time": call_time,
                "elapsed_time": elapsed_time,
                "total_elapsed_time": total_elapsed_time
            },
            "date":today,
            "message": "Data refreshed successfully"
        }), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@employee_extra_app.route("/api/change_profilepic", methods=["POST"])
@token_required
def change_profilepic(current_user):
    _id = str(current_user['_id'])
    profile_pic = request.files.get('profile_pic')

    if not profile_pic:
        return jsonify({'message': 'Profile picture not found'}), 400

    profile_pic = upload_to_firebase(profile_pic, 'Employee_Profile_Pic', _id)

    # Save profile picture to MongoDB
    collection.update_one(
        {'_id': ObjectId(_id)},
        {"$set": {"profile_pic": profile_pic}}
    )
    return jsonify({'message': 'Profile picture uploaded successfully','data':profile_pic,'status':True})


@employee_extra_app.route("/api/change_password", methods=["POST"])
@token_required 
def change_password(current_user):
    _id = str(current_user['_id'])
    previous_password = request.json.get('previous_password')
    new_password = request.json.get('new_password')

    user = collection.find_one({'_id': ObjectId(_id)})

    if user:
        stored_hashed_password = user.get('password', '')
        if check_password_hash(stored_hashed_password, previous_password):
            
            new_hashed_password = generate_password_hash(new_password)  
            collection.update_one(
                {'_id': ObjectId(_id)},
                {"$set": {"password": new_hashed_password}}
            )
            # Save notification in the notification_collection
            notification_data = {
                'user_id': _id,
                'message': 'Your password has been changed.',
                'timestamp': datetime.now(pytz.timezone(current_user["time_zone"])),
                'isSeen':False
            }
            notification_collection.insert_one(notification_data)

            # Convert the MongoDB Date type to a string representation
            notification_data['timestamp'] = notification_data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            # Convert ObjectId to string
            notification_data['_id'] = str(notification_data['_id'])

            # Emitting a socket notification
            socketio.emit(f'notification_{_id}', [notification_data], namespace='/socket_connection')
            return jsonify({'status': 'success', 'message': 'Password updated successfully'})
        else:
            return jsonify({'status': 'error', 'message': 'Incorrect previous password'})
    else:
        return jsonify({'status': 'error', 'message': 'User not found'})



@employee_extra_app.route("/api/get_previous_days_time", methods=["GET"])
@token_required
def get_previous_days_time(current_user):
    # Use employee_id from the request if provided, otherwise fallback to the token
    _id = request.args.get('employee_id', str(current_user['_id']))

    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    time_range = request.args.get('time_range')

    today = datetime.now(pytz.timezone(current_user["time_zone"]))

    if start_date_str and end_date_str:
        # Parse provided start_date and end_date
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
        date_format = "%Y-%m-%d"
    else:
        end_date = today - timedelta(days=1)

        # Adjust start date and format based on time range
        if time_range == '1_week':
            start_date = today - timedelta(weeks=1)
        elif time_range == '1_month':
            start_date = today - relativedelta(months=1)
        elif time_range == '1_year':
            start_date = today - relativedelta(years=1)
        else:  # Default to 3 days
            start_date = today - timedelta(days=3)

        # If filtering by 3 days, adjust start date if Sunday is included
        if time_range == '3_days':
            while start_date.weekday() == 6:  # Sunday
                start_date -= timedelta(days=1)

    time_worked = []
    delta = end_date - start_date

    total_elapsed_time_seconds = 0
    total_call_time_seconds = 0
    total_total_elapsed_time_seconds = 0

    for i in range(delta.days + 1):  # Include the end date in the range
        current_date = start_date + timedelta(days=i)
        formatted_date = current_date.strftime("%Y-%m-%d")

        entry = collection.find_one({"_id": ObjectId(_id), "time_tracking.date": formatted_date})
        if entry:
            time_tracking_data = entry.get('time_tracking', [])
            for time_entry in time_tracking_data:
                if time_entry.get('date') == formatted_date:
                    elapsed_time = time_entry.get('elapsed_time', '00:00:00')
                    call_time = time_entry.get('call_time', '00:00:00')
                    total_elapsed_time = time_entry.get('total_elapsed_time', '00:00:00')
                    start_time = time_entry.get('start_time', '')

                    # Convert times to seconds
                    elapsed_time_seconds = sum(
                        int(x) * 60 ** i for i, x in enumerate(reversed(elapsed_time.split(':')))
                    )
                    call_time_seconds = sum(
                        int(x) * 60 ** i for i, x in enumerate(reversed(call_time.split(':')))
                    )
                    total_elapsed_time_entry_seconds = sum(
                        int(x) * 60 ** i for i, x in enumerate(reversed(total_elapsed_time.split(':')))
                    )

                    # Accumulate total times
                    total_elapsed_time_seconds += elapsed_time_seconds
                    total_call_time_seconds += call_time_seconds
                    total_total_elapsed_time_seconds += total_elapsed_time_entry_seconds

                    time_worked.append({
                        "date": formatted_date,
                        "elapsed_time": elapsed_time,
                        "call_time": call_time,
                        "total_elapsed_time": total_elapsed_time,
                        "start_time": start_time
                    })
                    break
        else:
            time_worked.append({
                "date": formatted_date,
                "elapsed_time": '00:00:00',
                "call_time": '00:00:00',
                "total_elapsed_time": '00:00:00',
                "start_time": '00:00:00'
            })

    # Reverse the list to get dates in descending order
    time_worked.reverse()

    # Convert accumulated total times to HH:MM:SS format
    def seconds_to_hms(seconds):
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"

    total_elapsed_time_hms = seconds_to_hms(total_elapsed_time_seconds)
    total_call_time_hms = seconds_to_hms(total_call_time_seconds)
    total_total_elapsed_time_hms = seconds_to_hms(total_total_elapsed_time_seconds)

    return jsonify({
        "time_worked": time_worked,
        "date_range": {
            "start_date": start_date.strftime("%d %b %Y"),
            "end_date": end_date.strftime("%d %b %Y")
        },
        "totals": {
            "total_elapsed_time": total_elapsed_time_hms,
            "total_call_time": total_call_time_hms,
            "total_total_elapsed_time": total_total_elapsed_time_hms
        }
    }), 200



@employee_extra_app.route('/api/submit_note', methods=['POST'])
@token_required
def submit_note(current_user):
    try:
        if request.method == 'POST':
            note_content = request.json.get('note_content')
            _id = str(current_user['_id'])

            # Access 'time_zone' from the current_user dictionary
            time_zone = current_user.get('time_zone', 'Asia/Kolkata')  # Default to 'UTC' if not present

            frontend_timezone = pytz.timezone(time_zone)
            frontend_time = datetime.now(frontend_timezone)

            today = frontend_time.strftime("%Y-%m-%d")
            timestamp = frontend_time.strftime('%H:%M:%S')

            if note_content:
                new_note = f"{timestamp}: {note_content}"

                existing_entry = collection.find_one({"_id": ObjectId(_id), "time_tracking.date": today})

                if existing_entry:
                    collection.update_one(
                        {"_id": ObjectId(_id), "time_tracking.date": today},
                        {'$push': {'time_tracking.$.notes': new_note}}
                    )
                
                    # Fetch all notes for today
                    updated_entry = collection.find_one({"_id": ObjectId(_id), "time_tracking.date": today})
                    all_notes = []
                    if updated_entry:
                        for entry in updated_entry.get('time_tracking', []):
                            if entry.get('date') == today:
                                all_notes = entry.get('notes', [])
                                break

                    notes_data = {
                        'date': today,
                        'notes': [{'timestamp': note.split(': ')[0], 'note_content': note.split(': ', 1)[1]} for note in all_notes],
                        'employee_details': find_user_info(_id)
                    }
                    # Emitting socket update
                    socketio.emit(f'notes_{_id}', [notes_data], namespace='/socket_connection')

                    # Emitting notification
                    notification_data = {
                        'user_id': _id,
                        'message': 'A new note has been added.',
                        'timestamp':  datetime.now(frontend_timezone),
                        'isSeen': False,
                        'adminSeen': False,
                        'company': current_user['company'],
                        'user_info': find_user_info(_id)
                    }

                    notification_collection.insert_one(notification_data)

                    notification_data['_id'] = str(notification_data['_id'])
                    notification_data['timestamp'] = notification_data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
                    socketio.emit(f'notification_{current_user["company"]}', [notification_data], namespace='/socket_connection')
                    return jsonify({"message": "Note added successfully", "notes": notes_data['notes']}), 200
                else:
                    return jsonify({"error": "No entry found for today"}), 400
            else:
                return jsonify({"error": "Note content missing"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@employee_extra_app.route('/api/graph', methods=['GET']) 
@token_required
def get_total_hours(current_user):
    try:
        employee_id = str(current_user["_id"])
        year = int(request.args.get('year'))
        month_param = request.args.get('month')  # Optional, e.g., "01"

        if not employee_id or not year:
            return jsonify({'error': 'Invalid input parameters'}), 400

        month_filter = int(month_param) if month_param else None

        # Base match query
        match_query = {"_id": ObjectId(employee_id)}

        # Build date range
        if month_filter:
            start_date = datetime(year, month_filter, 1)
            _, last_day = monthrange(year, month_filter)
            end_date = datetime(year, month_filter, last_day, 23, 59, 59)
        else:
            start_date = datetime(year, 1, 1)
            end_date = datetime(year + 1, 1, 1)

        # Aggregate relevant time_tracking entries
        work_entries = collection.aggregate([
            {"$match": match_query},
            {"$unwind": "$time_tracking"},
            {
                "$addFields": {
                    "time_tracking.date_as_date": {
                        "$dateFromString": {
                            "dateString": "$time_tracking.date",
                            "format": "%Y-%m-%d",
                            "onError": None,
                            "onNull": None
                        }
                    }
                }
            },
            {
                "$match": {
                    "time_tracking.date_as_date": {
                        "$gte": start_date,
                        "$lte": end_date
                    }
                }
            },
            {"$sort": {"time_tracking.date_as_date": pymongo.ASCENDING}},
            {
                "$project": {
                    "date": "$time_tracking.date_as_date",
                    "total_elapsed_time": "$time_tracking.total_elapsed_time"
                }
            }
        ])

        if month_filter:
            # Fixed-size list for 5 weeks (week 0 to week 4)
            weekly_hours = [0.0 for _ in range(5)]

            for entry in work_entries:
                date = entry["date"]
                total_elapsed_time = entry.get("total_elapsed_time", "0:00:00")

                try:
                    h, m, s = map(int, total_elapsed_time.split(":"))
                    duration = timedelta(hours=h, minutes=m, seconds=s)
                except:
                    duration = timedelta(0)

                first_day_of_month = datetime(year, month_filter, 1)
                week_index = ((date - first_day_of_month).days + first_day_of_month.weekday()) // 7

                if 0 <= week_index < 5:
                    weekly_hours[week_index] += duration.total_seconds() / 3600

            total_hours = weekly_hours
        else:
            # Monthly aggregation (12 months)
            monthly_hours = [0.0 for _ in range(12)]
            for entry in work_entries:
                date = entry["date"]
                total_elapsed_time = entry.get("total_elapsed_time", "0:00:00")

                try:
                    h, m, s = map(int, total_elapsed_time.split(":"))
                    duration = timedelta(hours=h, minutes=m, seconds=s)
                except:
                    duration = timedelta(0)

                monthly_hours[date.month - 1] += duration.total_seconds() / 3600

            total_hours = monthly_hours

        return jsonify({"total_hours": total_hours}), 200

    except Exception as e:
        return jsonify({"error": f"Something went wrong: {e}"}), 500


@employee_extra_app.route('/api/add_mom', methods=['POST'])
@token_required
def add_mom(current_user):
    data = request.get_json()
    mom_data = data.get("momData")
    date = data.get("date")
    employee_id = str(current_user['_id'])
    company = current_user['company']
    
    if not employee_id or not mom_data or not date:
        return jsonify({"error": "employeeId, momData, and date are required"}), 400

    try:
        # Find the document with the given employeeId and company
        existing_doc = moms_collection.find_one({"employeeId": employee_id, "company": company})

        if existing_doc:
            # Check if the MoM list already has an entry for the given date
            mom_entry = next((entry for entry in existing_doc["momList"] if entry["date"] == date), None)
            if mom_entry:
                # Append the new MoM data to the existing date entry
                mom_entry["momData"].append(mom_data)
            else:
                # Add a new entry for the given date
                existing_doc["momList"].append({
                    "date": date,
                    "momData": [mom_data]
                })
            moms_collection.update_one({"_id": existing_doc["_id"]}, {"$set": {"momList": existing_doc["momList"]}})
        else:
            # Create a new document for the employeeId if it doesn't exist
            new_doc = {
                "employeeId": employee_id,
                "company": company,
                "momList": [{
                    "date": date,
                    "momData": [mom_data]
                }]
            }
            moms_collection.insert_one(new_doc)
        
        return jsonify({"message": "MoM added successfully", "data": mom_data }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
