import json
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta

import requests, pytz
from socketio_setup import socketio
from bson import ObjectId, errors


from decorators import socket_token, token_required, company_collection, notification_collection, get_emp_list, collection, upload_ss_to_firebase

time_manage_app = Blueprint('time_manage_app',__name__) 


# In-memory data structures to track employee states by company code
employee_states = {}

@socketio.on('request_time', namespace='/socket_connection')
def handle_time_request(msg):
    # Get current IST time
    ist_timezone = pytz.timezone('Asia/Kolkata')
    ist_time = datetime.now(ist_timezone).strftime('%Y-%m-%d %H:%M:%S')

    # Send the time back to the client
    socketio.emit('response_time', {'time': ist_time}, namespace='/socket_connection')

@socketio.on('ping', namespace='/socket_connection')
def handle_ping(msg):
    socketio.emit('pong',msg, namespace='/socket_connection')

def get_company_state(company):
    if company not in employee_states:
        employee_states[company] = {
            'active_emp': [],
            'inactive_emp': [],
            'incall_emp': []
        }
    return employee_states[company]

@socketio.on('get_online_emp', namespace='/socket_connection')
def get_total_employees(company):
    # Fetch the company state
    company_state = get_company_state(company)

    # Combine all employees into a single list
    all_emps = company_state['active_emp'] + company_state['inactive_emp'] + company_state['incall_emp']
    
    # Safely convert _id values to ObjectId, skipping invalid ones
    all_emp_ids = []
    for emp in all_emps:
        try:
            if isinstance(emp['_id'], (str, ObjectId)):
                all_emp_ids.append(ObjectId(emp['_id']))
        except (errors.InvalidId, TypeError):
            continue  # Skip invalid or malformed _id values
    
    # Remove duplicates
    all_emp_ids = list(set(all_emp_ids))

    # Fetch all valid employee _ids from DB
    valid_ids_cursor = collection.find({'_id': {'$in': all_emp_ids}}, {'_id': 1})
    valid_ids = {str(doc['_id']) for doc in valid_ids_cursor}

    # Helper to filter valid employees and update state
    def filter_valid_emps(employee_list_key):
        employee_list = company_state[employee_list_key]
        valid_list = [emp for emp in employee_list if str(emp['_id']) in valid_ids]
        company_state[employee_list_key] = valid_list
        return valid_list

    valid_active_emp = filter_valid_emps('active_emp')
    valid_inactive_emp = filter_valid_emps('inactive_emp')
    valid_incall_emp = filter_valid_emps('incall_emp')

    # Fetch total employees from company collection
    company_entry = company_collection.find_one({"company": company})
    total_employees = len(company_entry.get("empList", [])) if company_entry else 0

    # Emit results
    socketio.emit(f'employee_counts_{company}', {
        'total': total_employees,
        'online': len(valid_active_emp),
        'offline': len(valid_inactive_emp),
        'incall': len(valid_incall_emp),
        'online_emp': get_emp_list(valid_active_emp),
        'offline_emp': get_emp_list(valid_inactive_emp),
        'incall_emp': get_emp_list(valid_incall_emp)
    }, namespace='/socket_connection')


@socketio.on("join_room", namespace='/socket_connection')
def handle_join_room(message):
    try:
        # Parse the incoming message as JSON
        if isinstance(message, str):
            message = json.loads(message)

        # Extract state and user information
        state = message.get('state')
        current_user = socket_token(message.get('token'))
        user_id = str(current_user['_id'])
        company = current_user['company']
        time_zone = str(current_user['time_zone'])
        
        # Get the current time in the user's timezone
        frontend_timezone = pytz.timezone(time_zone)
        frontend_time = datetime.now(frontend_timezone)
        start_time = frontend_time.strftime("%H:%M:%S")
        sid = request.sid

        # Get the current company state
        company_state = get_company_state(company)

        # Remove the user from all lists to ensure a clean state
        company_state['active_emp'] = [
            emp for emp in company_state['active_emp'] if emp['_id'] != user_id
        ]
        company_state['inactive_emp'] = [
            emp for emp in company_state['inactive_emp'] if emp['_id'] != user_id
        ]
        company_state['incall_emp'] = [
            emp for emp in company_state['incall_emp'] if emp['_id'] != user_id
        ]

        # Update the state based on the provided state
        if state == 'active':
            company_state['active_emp'].append({'_id': user_id, 'time': start_time, 'sid': sid})
        elif state == 'incall':
            company_state['incall_emp'].append({'_id': user_id, 'time': start_time, 'sid': sid})
        elif state == 'disconnect':
            company_state['inactive_emp'].append({'_id': user_id, 'time': start_time, 'sid': sid})

        # Emit the updated employee counts
        emit_employee_counts(company)

    except json.JSONDecodeError:
        # Handle invalid JSON in the message
        socketio.emit('error', {'message': 'Invalid message format'}, namespace='/socket_connection')
    except Exception as e:
        # Handle other errors
        socketio.emit('error', {'message': f"An error occurred: {str(e)}"}, namespace='/socket_connection')


def emit_employee_counts(company):
    company_state = get_company_state(company)

    active_employee_count = len(company_state['active_emp'])
    inactive_employee_count = len(company_state['inactive_emp'])
    incall_employee_count = len(company_state['incall_emp'])

    company_entry = company_collection.find_one({"company": company})
    total_employees = len(company_entry.get("empList", [])) if company_entry else 0

    socketio.emit(f'employee_counts_{company}', {
        'total': total_employees,
        'online': active_employee_count,
        'offline': inactive_employee_count,
        'incall': incall_employee_count,
        'online_emp': get_emp_list(company_state['active_emp']),
        'offline_emp': get_emp_list(company_state['inactive_emp']),
        'incall_emp': get_emp_list(company_state['incall_emp'])
    }, namespace='/socket_connection')

@socketio.on("disconnect", namespace='/socket_connection')
def handle_disconnect():
    sid = request.sid

    employee = None
    company = None

    # Search for the employee in all companies
    for comp, state in employee_states.items():
        for emp in state['active_emp']:
            if emp['sid'] == sid:
                employee = emp
                company = comp
                state['active_emp'].remove(emp)
                break

        if not employee:
            for emp in state['incall_emp']:
                if emp['sid'] == sid:
                    employee = emp
                    company = comp
                    state['incall_emp'].remove(emp)
                    break

        if employee:
            break

    if employee and company:
        company_state = get_company_state(company)
        company_state['inactive_emp'].append({'_id': employee['_id'], 'time': employee['time'], 'sid': sid})
        emit_employee_counts(company)

@time_manage_app.route("/api/start_time", methods=["POST"])
@token_required
def start_time_tracking(current_user):
    try:
        _id = str(current_user['_id'])
        call_time_seconds = request.json.get('callTime')
        time_zone = str(current_user['time_zone'])

        frontend_timezone = pytz.timezone(time_zone)
        frontend_time = datetime.now(frontend_timezone)

        today = frontend_time.strftime("%Y-%m-%d")

        # Fetch the user document
        user = collection.find_one(
            {"_id": ObjectId(_id)},
            {"time_tracking": {"$slice": -15}}  # Get only the last 20 entries
        )
        company = current_user['company']

        # Convert call time from seconds to HH:MM:SS format
        call_time_formatted = str(timedelta(seconds=call_time_seconds))

        # Search for the entry with the specified date in the time_tracking list
        time_tracking_entry = None
        for entry in user.get("time_tracking", []):
            if entry["date"] == today:
                time_tracking_entry = entry
                break

        # If the entry for the date exists, update start_time and call_time
        if time_tracking_entry:
            # Check if start_time is missing, empty, or None
            if not time_tracking_entry.get("start_time"):
                collection.update_one(
                    {"_id": ObjectId(_id), "time_tracking.date": today},
                    {"$set": {
                        "time_tracking.$.start_time": frontend_time.strftime("%H:%M:%S")
                    }}
                )
            # Get existing call time from the entry and convert to seconds for comparison
            existing_call_time = time_tracking_entry.get('call_time', '00:00:00')
            h, m, s = map(int, existing_call_time.split(':'))
            existing_call_time_seconds = h * 3600 + m * 60 + s
            
            # Compare existing call time and new call time
            if existing_call_time_seconds >= call_time_seconds:
                # If the existing time is greater or equal, skip updating and return success message
                return jsonify({'status': 'success'})

            # Update today's existing entry
            collection.update_one(
                {"_id": ObjectId(_id), "time_tracking.date": today},
                {"$set": {
                    "time_tracking.$.call_time": call_time_formatted
                }}
            )

        else:
            # Create a new entry with the provided data
            new_entry = {
                "date": today,
                "Responses": 0,
                "start_time": frontend_time.strftime("%H:%M:%S"),
                "total_elapsed_time": "00:00:00",
                "note": "",
                "call_time": "00:00:00",
                "elapsed_time": "00:00:00"
            }
            collection.update_one(
                {"_id": ObjectId(_id)},
                {"$push": {"time_tracking": new_entry}}
            )

        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}) , 500

@time_manage_app.route("/api/pause_time", methods=["POST"])
@token_required
def pause_time_tracking(current_user):
    try:
        _id = str(current_user['_id'])

        # Access 'time_zone' from the current_user dictionary
        time_zone = current_user.get('time_zone', 'Asia/Kolkata')  # Default to 'Asia/Kolkata' if not present

        frontend_timezone = pytz.timezone(time_zone)
        frontend_time = datetime.now(frontend_timezone)
        pause_time = frontend_time.strftime("%H:%M:%S")
        # Adjust today's date according to the specified timezone
        today = frontend_time.strftime("%Y-%m-%d")

        # Fetch the user document
        user = collection.find_one(
            {"_id": ObjectId(_id)},
            {"time_tracking": {"$slice": -15}}  # Get only the last 20 entries
        )

        company = current_user['company']
        # Search for the entry with the specified date in the time_tracking list
        time_tracking_entry = None
        for entry in user.get("time_tracking", []):
            if entry["date"] == today:
                time_tracking_entry = entry
                break

        # If the entry for the date exists, perform the check and update if conditions are met
        if time_tracking_entry:
            elapsed_time_seconds = request.json.get("elapsedTime")
            call_time_seconds = request.json.get("callTime")
            
            # Calculate total_elapsed_time by adding elapsed_time_seconds and call_time_seconds
            total_elapsed_time_seconds = elapsed_time_seconds + call_time_seconds
            
            # Convert seconds to HH:MM:SS format
            elapsed_time_formatted = str(timedelta(seconds=elapsed_time_seconds))
            call_time_formatted = str(timedelta(seconds=call_time_seconds))
            total_elapsed_time_formatted = str(timedelta(seconds=total_elapsed_time_seconds))
            
            # Convert existing total_elapsed_time from HH:MM:SS format to seconds for comparison
            existing_total_elapsed_time = time_tracking_entry.get('total_elapsed_time', '00:00:00')
            h, m, s = map(int, existing_total_elapsed_time.split(':'))
            existing_total_elapsed_time_seconds = h * 3600 + m * 60 + s
            
            # Compare existing and new total_elapsed_time
            if existing_total_elapsed_time_seconds >= total_elapsed_time_seconds:
                # If the existing time is greater or equal, skip updating and return success message
                return jsonify({'status': 'success'})

            # Update today's record properly inside array
            collection.update_one(
                {"_id": ObjectId(_id), "time_tracking.date": today},
                {"$set": {
                    "time_tracking.$.elapsed_time": elapsed_time_formatted,
                    "time_tracking.$.call_time": call_time_formatted,
                    "time_tracking.$.total_elapsed_time": total_elapsed_time_formatted
                }}
            )


        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@time_manage_app.route("/api/end_time", methods=["POST"])
@token_required
def end_time_tracking(current_user):
    _id = str(current_user['_id'])

    # Access 'time_zone' from the current_user dictionary
    time_zone = current_user.get('time_zone', 'Asia/Kolkata')  # Default to 'Asia/Kolkata' if not present

    frontend_timezone = pytz.timezone(time_zone)
    frontend_time = datetime.now(frontend_timezone)

    today = frontend_time.strftime("%Y-%m-%d")
    end_time = frontend_time.strftime("%H:%M:%S")
    user = collection.find_one(
        {"_id": ObjectId(_id)},
        {"time_tracking": {"$slice": -15}}
    )

    # Search for the entry with the specified date in the time_tracking list
    time_tracking_entry = None
    for entry in user.get("time_tracking", []):
        if entry["date"] == today:
            time_tracking_entry = entry
            break

    # If the entry for the date exists, update end_time
    if time_tracking_entry:
        # Update today's entry with end_time
        collection.update_one(
            {"_id": ObjectId(_id), "time_tracking.date": today},
            {"$set": {
                "time_tracking.$.end_time": end_time
            }}
        )

        # Save notification in the notification_collection
        notification_data = {
            'user_id': _id,
            'message': 'You did job logout.',
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


    return jsonify({'status': 'success'})


@time_manage_app.route("/api/store_response_time", methods=["POST"])
@token_required
def store_response_time(current_user):
    try:
        user_id = str(current_user['_id'])

        # Access 'time_zone' from the current_user dictionary
        time_zone = current_user.get('time_zone', 'Asia/Kolkata')  # Default to 'Asia/Kolkata' if not present

        frontend_timezone = pytz.timezone(time_zone)
        frontend_time = datetime.now(frontend_timezone)

        today = frontend_time.strftime("%Y-%m-%d")

        response_time = request.form.get("responseTime")
        if response_time and response_time != '':
            response_time = float(response_time)
        else:
            response_time = None 

        # Fetch the user document
        user = collection.find_one({"_id": ObjectId(user_id)})

        # Search for the entry with the specified date in the time_tracking list
        time_tracking_entry = None
        for entry in user.get("time_tracking", []):
            if entry["date"] == today:
                time_tracking_entry = entry
                break

        # If the entry for the date exists, update the responses
        if time_tracking_entry:
            response_no = time_tracking_entry.get('Responses', 0)

            current_time = frontend_time.strftime('%H:%M:%S')

            if response_time is not None:
                response_with_time = f"{response_time} on {current_time}"
                notification = {"message": f"You did a confirmation at {current_time}"}
            else:
                response_with_time = f"Missed on {current_time}"
                notification = {"message": f"You missed a confirmation at {current_time}"}
                notification_collection.insert_one({
                    "type":"alert",
                    "timestamp": frontend_time,
                    "isSeen":False,
                    "message": f"You missed a confirmation at {current_time}",
                    "user_id": user_id,
                })                
            # Emitting a socket notification
            socketio.emit(f'alert_{user_id}', notification, namespace='/socket_connection')

            
            # Increment 'Responses' field
            time_tracking_entry['Responses'] += 1

            # Set the new response field
            time_tracking_entry[f"Response{response_no + 1}"] = response_with_time

            # Update the user document with the modified time_tracking list
            collection.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {"time_tracking": user.get("time_tracking", [])}}
            )

            return jsonify({"status": "success"})
        else:
            return jsonify({'message': "Please Login and Start Your time"}), 401
    except Exception as e:
        return jsonify({'message': e}), 401


@time_manage_app.route("/api/incall", methods=["POST"])
@token_required
def incall(current_user):
    _id = str(current_user['_id'])

    # Access 'time_zone' from the current_user dictionary
    time_zone = current_user.get('time_zone', 'Asia/Kolkata')  # Default to 'Asia/Kolkata' if not present

    frontend_timezone = pytz.timezone(time_zone)
    frontend_time = datetime.now(frontend_timezone)

    today = frontend_time.strftime("%Y-%m-%d")
    # Fetch the user document
    user = collection.find_one({"_id": ObjectId(_id)})

    # Search for the entry with the specified date in the time_tracking list
    time_tracking_entry = None
    for entry in user.get("time_tracking", []):
        if entry["date"] == today:
            time_tracking_entry = entry
            break

    if time_tracking_entry:
        company = current_user['company']
    else:
        # Create a new entry with the provided data
        new_entry = {
            "date": today,
            "Responses": 0,
            "start_time": frontend_time.strftime("%H:%M:%S"),
            "total_elapsed_time": "00:00:00",
            "note": "",
            "call_time": "00:00:00",
            "elapsed_time": "00:00:00"
        }

        user.setdefault("time_tracking", []).append(new_entry)
        collection.update_one(
            {"_id": ObjectId(_id)},
            {"$set": {"time_tracking": user["time_tracking"]}}
        )

    return jsonify({'status': 'success'})

@time_manage_app.route('/api/update_offline_data', methods=['POST'])
@token_required
def update_offline_data(current_user):
    try:
        _id = str(current_user['_id'])
        # Get data from request
        data = request.json
        day_count = 0
        last_updated_entry = None
        
        # Loop through each entry in the data list
        for entry in data:
            day_count += 1

            date = entry['date']
            responses = entry.get('response', [])
            totalmom = entry.get('totalmom', 0)
            afk_list = entry.get('afk', [])
            total_response = len(responses)
            start_time = entry.get('startTime', '')
            active_time_seconds = entry.get('activeTime', 0)
            in_call_time_seconds = entry.get('inCallTime', 0)
            
            # Convert seconds to HH:MM:SS format
            active_time = str(timedelta(seconds=active_time_seconds))
            in_call_time = str(timedelta(seconds=in_call_time_seconds))
            total_elapsed_time_seconds = active_time_seconds + in_call_time_seconds
            total_elapsed_time = str(timedelta(seconds=total_elapsed_time_seconds))
            
            last_updated_entry = entry
            # Find the document for the user
            user_doc = collection.find_one({'_id': ObjectId(_id)})
            if user_doc:
                # Check if the date entry exists in time_tracking
                time_tracking_entry = next((item for item in user_doc['time_tracking'] if item['date'] == date), None)
                if time_tracking_entry:
                    # Convert existing total_elapsed_time from HH:MM:SS format to seconds
                    existing_total_elapsed_time = time_tracking_entry.get('total_elapsed_time', '0:0:0')
                    h, m, s = map(int, existing_total_elapsed_time.split(':'))
                    existing_total_elapsed_time_seconds = h * 3600 + m * 60 + s
                    existing_totalmom = time_tracking_entry.get('totalmom', 0)
                    totalmom = max(totalmom, existing_totalmom)
                    # Check and update start_time if necessary
                    if ('start_time' not in time_tracking_entry) or (not time_tracking_entry['start_time']) or (time_tracking_entry['start_time'] in ['00:00:00', '', ' ']):
                        collection.update_one(
                            {'_id': ObjectId(_id), 'time_tracking.date': date},
                            {'$set': {'time_tracking.$.start_time': start_time}}
                        )
                        time_tracking_entry['start_time'] = start_time 
                        
                    # Only update if the new total elapsed time is greater
                    if total_elapsed_time_seconds >= existing_total_elapsed_time_seconds:
                        update_data = {
                            **{f'time_tracking.$.Response{i}': response for i, response in enumerate(responses, start=1)},
                            'time_tracking.$.elapsed_time': active_time,
                            'time_tracking.$.call_time': in_call_time,
                            'time_tracking.$.total_elapsed_time': total_elapsed_time,
                            'time_tracking.$.Responses': total_response,
                            'time_tracking.$.afk': afk_list,
                            'time_tracking.$.totalmom': totalmom
                        }
                        collection.update_one(
                            {'_id': ObjectId(_id), 'time_tracking.date': date},
                            {'$set': update_data}
                        )
                else:
                    # Create a new entry in time_tracking
                    new_entry = {
                        'date': date,
                        **{f'Response{i}': response for i, response in enumerate(responses, start=1)},
                        'start_time': start_time,
                        'elapsed_time': active_time,
                        'call_time': in_call_time,
                        'total_elapsed_time': total_elapsed_time,
                        'Responses': total_response,
                        'afk': afk_list,
                        'totalmom': totalmom
                    }
                    collection.update_one(
                        {'_id': ObjectId(_id)},
                        {'$push': {'time_tracking': new_entry}}
                    )
                
            else:
                raise Exception("User document not found.")
        
        if day_count >= 10:
            return jsonify({'message': f'Data updated successfully for {day_count} days', 'status': True, 'delete_local': True, 'last_updated_entry': last_updated_entry}), 200
        else:
            return jsonify({'message': 'Data updated successfully', 'status': True, 'delete_local': False, 'last_updated_entry': last_updated_entry}), 200
    
    except Exception as e:
        return jsonify({'error': str(e), 'status': False}), 500

@time_manage_app.route('/api/upload_ss', methods=['POST'])
@token_required
def upload_images(current_user):
    try:
        # Get the data from the request
        employee_id = str(current_user['_id'])
        company = current_user['company']
        date = request.form.get('date')
        time = request.form.get('time')
        images = request.files.getlist('image')  # Get multiple images

        if not employee_id or not date or not time or not images:
            return jsonify({'error': 'Missing required fields', 'status': False}), 400

        # Validate date format
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD.', 'status': False}), 400

        # Find the employee document by employee_id
        employee_doc = collection.find_one({'_id': ObjectId(employee_id)})
        if not employee_doc:
            return jsonify({'error': 'Employee not found', 'status': False}), 404

        uploaded_image_urls = []
        
        # Upload each image with numbered filenames
        for index, image in enumerate(images, start=1):
            filename = f"{time}_{index}.png"  # Name images sequentially

            # Google Drive Upload
            # response = requests.post(
            #     "https://drive.toggletimer.com/api/upload",
            #     files={"file": image},
            #     data={"company": company, "employee_id": employee_doc['employee_id'], "date": date, "filename": filename}
            # )

            # if response.status_code != 200:
            #     return jsonify({'error': 'Failed to upload to Google Drive', 'response': response.json(), 'status': False}), 500
            # image_url = response.json().get("data")


            # Firebase Upload
            image_url = upload_ss_to_firebase(image, company, employee_doc['employee_id'], date, filename)
            
            uploaded_image_urls.append({"time": time, "url": image_url})

        # Update the employee's time_tracking for the given date
        time_tracking_entry = next((item for item in employee_doc.get('time_tracking', []) if item['date'] == date), None)

        if time_tracking_entry:
            # Append image URLs to 'images' field
            if 'images' not in time_tracking_entry:
                time_tracking_entry['images'] = []
            time_tracking_entry['images'].extend(uploaded_image_urls)

            # Update MongoDB document
            collection.update_one(
                {'_id': ObjectId(employee_id), 'time_tracking.date': date},
                {'$set': {'time_tracking.$.images': time_tracking_entry['images']}}
            )
        else:
            # Create a new entry for the date
            new_entry = {
                'date': date,
                'images': uploaded_image_urls
            }
            collection.update_one(
                {'_id': ObjectId(employee_id)},
                {'$push': {'time_tracking': new_entry}}
            )

        return jsonify({'message': 'Images uploaded successfully', 'image_urls': uploaded_image_urls, 'status': True}), 200

    except Exception as e:
        return jsonify({'error': str(e), 'status': False}), 500
