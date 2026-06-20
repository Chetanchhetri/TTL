from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
import pytz
from socketio_setup import socketio
from bson import ObjectId


from decorators import token_required, tasks_collection, upload_to_firebase, collection, notification_collection, find_user_info

tasks_app = Blueprint('tasks_app',__name__)

@tasks_app.route('/api/upload-task', methods=['POST'])
@token_required
def upload_task(current_user):
    try:
        employee_id = request.form['employee_id']
        title = request.form['title']
        priority = request.form['priority']
        target_date = request.form['target_date']
        description = request.form['description']

        # Upload file to AWS S3 Handle multiple files
        files = request.files.getlist('file')
        # Access 'time_zone' from the current_user dictionary
        time_zone = current_user.get('time_zone', 'UTC')  # Default to 'UTC' if not present

        frontend_timezone = pytz.timezone(time_zone)
        frontend_time = datetime.now(frontend_timezone)
        file_urls = []

        for file in files:
            # Upload each file to AWS S3
            file_url = upload_to_firebase(file,'Tasks', employee_id)
            file_urls.append(file_url)

        company = collection.find_one({"_id": ObjectId(employee_id)}).get("company")

        # Store data in MongoDB collection
        task_data = {
            'given_by' : str(current_user['_id']),
            'employee_id': str(employee_id),
            'title': title,
            'priority': priority,
            'target_date': target_date,
            'description': description,
            'file_url': file_urls,
            'status': 'Inactive',
            'company': company,
            'createdAt': frontend_time
        }
        tasks_collection.insert_one(task_data)
        task_data["_id"] = str(task_data["_id"])

        # Save notification in the notification_collection
        notification_data = {
            'user_id': str(employee_id),
            'message': 'A new task is assigned.',
            'timestamp': datetime.now(frontend_timezone),
            'isSeen':False
        }
        notification_collection.insert_one(notification_data)

        # Convert the MongoDB Date type to a string representation
        notification_data['timestamp'] = notification_data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
        # Convert ObjectId to string
        notification_data['_id'] = str(notification_data['_id'])
        
        # Emitting a socket notification
        socketio.emit(f'notification_{str(employee_id)}', [notification_data], namespace='/socket_connection')

        return jsonify(task_data)
    except Exception as e:
        return jsonify({"error": str(e)})

@tasks_app.route('/api/update-task/<task_id>', methods=['PUT'])
@token_required
def update_task(current_user, task_id):
    try:
        task_data = request.form.to_dict()
        files = request.files.getlist('file')

        # Access 'time_zone' from the current_user dictionary
        time_zone = current_user.get('time_zone', 'UTC')
        frontend_timezone = pytz.timezone(time_zone)
        frontend_time = datetime.now(frontend_timezone)

        # Find the task by task_id
        task = tasks_collection.find_one({"_id": ObjectId(task_id)})
        if not task:
            return jsonify({"error": "Task not found"}), 404

        # Update fields if provided
        if 'employee_id' in task_data:
            task_data['employee_id'] = str(task_data['employee_id'])
        if 'title' in task_data:
            task_data['title'] = task_data['title']
        if 'priority' in task_data:
            task_data['priority'] = task_data['priority']
        if 'target_date' in task_data:
            task_data['target_date'] = task_data['target_date']
        if 'description' in task_data:
            task_data['description'] = task_data['description']

        # Handle file uploads
        file_urls = task.get('file_url', [])
        for file in files:
            file_url = upload_to_firebase(file, 'Tasks', task['employee_id'])
            file_urls.append(file_url)

        task_data['file_url'] = file_urls
        task_data['updatedAt'] = frontend_time

        # Update the task in the database
        tasks_collection.update_one({"_id": ObjectId(task_id)}, {"$set": task_data})
        
        task = tasks_collection.find_one({"_id": ObjectId(task_id)})

        # Save notification in the notification_collection
        notification_data = {
            'user_id': str(task['employee_id']),
            'message': 'Your task has been updated.',
            'timestamp': frontend_time,
            'isSeen': False
        }
        notification_collection.insert_one(notification_data)

        # Convert the MongoDB Date type to a string representation
        notification_data['timestamp'] = notification_data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
        # Convert ObjectId to string
        notification_data['_id'] = str(notification_data['_id'])

        # Emitting a socket notification
        socketio.emit(f'notification_{str(task["employee_id"])}', [notification_data], namespace='/socket_connection')

        return jsonify({"message": "Task updated successfully", "task": task_data}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@tasks_app.route('/api/tasks/<employee_id>', methods=['GET'])
@token_required
def get_tasks(current_user, employee_id):    
    try:
        # Get filters from request parameters
        completed_filter = request.args.get('completed', '').lower() == 'true'
        on_hold_filter = request.args.get('on_hold', '').lower() == 'true'
        today_filter = request.args.get('today', '').lower() == 'true'
        recent_filter = request.args.get('recent', '').lower() == 'true'
        pending_filter = request.args.get('pending', '').lower() == 'true'
        in_progress_filter = request.args.get('in_progress', '').lower() == 'true'
        expired_filter = request.args.get('expired', '').lower() == 'true'
        active_filter = request.args.get('active', '').lower() == 'true'
        date_filter = request.args.get('date', '')

        # Construct base query based on employee_id
        base_query = {'employee_id': employee_id}

        # Initialize counts for each filter
        count_stats = {
            'total': 0,
            'completed': 0,
            'on_hold': 0,
            'active': 0,
            'in_progress': 0,
            'today': 0,
            'pending': 0,
            'expired': 0
        }

        # Query MongoDB for tasks based on employee_id
        tasks = tasks_collection.find(base_query).sort('createdAt', -1)

        # Update count for each type of task
        for task in tasks:
            count_stats['total'] += 1
            if task['status'] == 'Completed':
                count_stats['completed'] += 1
            elif task['status'] == 'On Hold':
                count_stats['on_hold'] += 1
            elif task['status'] == 'Pending':
                count_stats['pending'] += 1
            elif task['status'] == 'In progress':
                count_stats['in_progress'] += 1
            elif task['status'] == 'Active':
                count_stats['active'] += 1

        # Calculate count for today's tasks
        today_date = datetime.now(pytz.timezone(current_user["time_zone"])).strftime('%Y-%m-%d')
        today_query = {'target_date': today_date, **base_query}
        count_stats['today'] = tasks_collection.count_documents(today_query)

        # Calculate count for expired tasks
        expired_query = {'status': {'$nin': ['Completed', 'On Hold']}, 'target_date': {'$lt': today_date}, **base_query}
        count_stats['expired'] = tasks_collection.count_documents(expired_query)

        # Construct query based on filters
        query = dict(base_query)

        # Apply status filters exclusively
        if completed_filter:
            query['status'] = 'Completed'
        elif on_hold_filter:
            query['status'] = 'On Hold'
        elif pending_filter:
            query['status'] = 'Pending'
        elif in_progress_filter:
            query['status'] = 'In progress'
        elif active_filter:
            query['status'] = 'Active'
        elif expired_filter:
            query['status'] = {'$nin': ['Completed', 'On Hold']}
            query['target_date'] = {'$lt': today_date}

        if today_filter:
            query['target_date'] = today_date
        if recent_filter:
            # Adjust the timedelta based on how "recent" you want the tasks to be
            recent_threshold = datetime.now(pytz.timezone(current_user["time_zone"])) - timedelta(days=7)
            query['createdAt'] = {'$gte': recent_threshold}
        if date_filter:
            # Assuming date_filter is provided in YYYY-MM-DD format
            query['createdAt'] = {'$gte': datetime.strptime(date_filter, '%Y-%m-%d'), '$lt': datetime.strptime(date_filter, '%Y-%m-%d') + timedelta(days=1)}

        # Query MongoDB for tasks based on employee_id and filters
        tasks = tasks_collection.find(query).sort('createdAt', -1)

        # Prepare response data
        task_list = []
        for task in tasks:
            active_status = 'Active' if task['status'] not in ['Completed', 'On Hold', 'Inactive', 'Pending', 'In progress'] else 'Inactive'
            
            task_data = {
                '_id': str(task['_id']),
                'title': task['title'],
                'given_by': find_user_info(task['given_by']),
                'priority': task['priority'],
                'target_date': task['target_date'],
                'description': task['description'],
                'file_url': task.get('file_url', []),
                'status': task.get('status'),
                'active_status': active_status,
                'createdAt': task['createdAt'].strftime('%Y-%m-%d %H:%M:%S')
            }
            task_list.append(task_data)

        return jsonify({"tasks": task_list, "count_stats": count_stats})
    except Exception as e:
        return jsonify({"error": str(e)})


@tasks_app.route('/api/tasks/filter', methods=['GET'])
@token_required
def get_tasks_by_status(current_user):
    try:
        # Get filters from request parameters
        completed_filter = request.args.get('completed', '').lower() == 'true'
        on_hold_filter = request.args.get('on_hold', '').lower() == 'true'
        active_filter = request.args.get('active', '').lower() == 'true'
        in_progress_filter = request.args.get('in_progress', '').lower() == 'true'
        today_filter = request.args.get('today', '').lower() == 'true'
        recent_filter = request.args.get('recent', '').lower() == 'true'
        pending_filter = request.args.get('pending', '').lower() == 'true'
        expired_filter = request.args.get('expired', '').lower() == 'true'

        # Construct query based on filters
        query = {'company': current_user["company"]}

        if completed_filter:
            query['status'] = 'Completed'
        elif on_hold_filter:
            query['status'] = 'On Hold'
        elif active_filter:
            query['status'] = {'$nin': ['Completed', 'On Hold']}
        elif in_progress_filter:
            query['status'] = 'In progress'
        elif pending_filter:
            query['status'] = 'Pending'
        if today_filter:
            today_date = datetime.now(pytz.timezone(current_user["time_zone"])).strftime('%Y-%m-%d')
            query['target_date'] = today_date
        if recent_filter:
            # Adjust the timedelta based on how "recent" you want the tasks to be
            recent_threshold = datetime.now(pytz.timezone(current_user["time_zone"])) - timedelta(days=7)
            query['createdAt'] = {'$gte': recent_threshold}
        if expired_filter:
            today_date = datetime.now(pytz.timezone(current_user["time_zone"])).strftime('%Y-%m-%d')
            query['status'] = {'$nin': ['Completed', 'On Hold']}
            query['target_date'] = {'$lt': today_date}

        # Query MongoDB for tasks based on company name and status filter
        tasks = tasks_collection.find(query).sort('createdAt', -1)

        # Prepare response data
        task_list = []
        for task in tasks:
            active_status = 'Active' if task.get('status') not in ['Completed', 'On Hold'] else 'Inactive'
            
            task_data = {
                '_id': str(task['_id']),
                'title': task['title'],
                'priority': task['priority'],
                'target_date': task['target_date'],
                'description': task['description'],
                'file_url': task.get('file_url', []),
                # 'status': task.get('status'),
                'active_status': active_status,
                'createdAt': task['createdAt'].replace(tzinfo=pytz.UTC).astimezone(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')
            }
            task_list.append(task_data)

        return jsonify({"tasks": task_list})
    except Exception as e:
        return jsonify({"error": str(e)})

@tasks_app.route('/api/tasks/stats', methods=['GET'])
@token_required
def get_tasks_stats(current_user):
    try:
        # Get company name filter
        company_name = current_user["company"]

        # Base query for company
        base_query = {'company': company_name}

        # Function to get the count and distinct given_by for a specific query
        def get_count_and_given_by(query):
            count = tasks_collection.count_documents(query)
            employee_id_list = tasks_collection.distinct('employee_id', query)  # Get distinct given_by values
            employee_list = []
            for emp_id in employee_id_list:
                employee_list.append(find_user_info(emp_id))
            return {
                'count': count,
                'emp_list': employee_list
            }

        # Generate stats for each category
        count_stats = {
            'total': get_count_and_given_by(base_query),
            'completed': get_count_and_given_by({'status': 'Completed', 'company': company_name}),
            'on_hold': get_count_and_given_by({'status': 'On Hold', 'company': company_name}),
            'pending': get_count_and_given_by({'status': 'Pending', 'company': company_name}),
            'active': get_count_and_given_by({'status': {'$nin': ['Completed', 'On Hold']}, 'company': company_name}),
            'in_progress': get_count_and_given_by({'status': 'In progress', 'company': company_name}),
            'today': get_count_and_given_by({'target_date': datetime.now(pytz.timezone(current_user["time_zone"])).strftime('%Y-%m-%d'), 'company': company_name}),
            'expired': get_count_and_given_by({
                'status': {'$nin': ['Completed', 'On Hold']}, 
                'target_date': {'$lt': datetime.now(pytz.timezone(current_user["time_zone"])).strftime('%Y-%m-%d')}, 
                'company': company_name
            }),
        }

        return jsonify(count_stats), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@tasks_app.route('/api/tasks/change-status', methods=['PUT'])
@token_required
def change_task_status(current_user):
    try:
        # Get new status and task ID from request body
        new_status = request.json.get('status')
        task_id = request.json.get('task_id')
        frontend_timezone = pytz.timezone(current_user.get('time_zone', 'UTC'))

        if not new_status:
            return jsonify({"error": "Status field is required in the request body"}), 400

        # Convert task_id to ObjectId
        task_id = ObjectId(task_id)

        # Retrieve the task to get the employee (given_by) information
        task = tasks_collection.find_one({'_id': task_id})
        if not task:
            return jsonify({"error": "Task not found"}), 404

        employee_id = task['given_by']  # Assuming the task was assigned by or to this employee

        # Update the status of the current task in MongoDB
        result = tasks_collection.update_one({'_id': task_id}, {'$set': {'status': new_status}})

        if new_status == 'Active':
            # Find all other tasks of the same employee that are currently 'Active'
            tasks_collection.update_many(
                {
                    '_id': {'$ne': task_id},  # Exclude the current task
                    'employee_id': employee_id,   # Same employee
                    'status': 'Active'         # Status is Active
                },
                {'$set': {'status': 'Inactive'}}  # Set to Inactive
            )

        # Retrieve the updated task data
        updated_task = tasks_collection.find_one({'_id': task_id})

        # Prepare response data
        task_data = {
            '_id': str(updated_task['_id']),
            'title': updated_task['title'],
            'given_by': find_user_info(updated_task['given_by']),
            'priority': updated_task['priority'],
            'target_date': updated_task['target_date'],
            'description': updated_task['description'],
            'file_url': updated_task.get('file_url', []),
            'status': updated_task['status'],
            'createdAt': updated_task['createdAt'].strftime('%Y-%m-%d %H:%M:%S')
        }
        if new_status == 'Completed':
            notification_data = {
                'user_id': str(current_user['_id']),
                'message': 'A Employee completed a task',
                'timestamp': datetime.now(frontend_timezone),
                'isSeen': False,
                'adminSeen': False,
                'company': current_user['company'],
                'user_info': find_user_info(current_user['_id'])
            }

            notification_collection.insert_one(notification_data)
            notification_data['_id'] = str(notification_data['_id'])
            notification_data['timestamp'] = notification_data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            # Emitting a socket notification
            socketio.emit(f'notification_{current_user["company"]}', [notification_data], namespace='/socket_connection')


        return jsonify({"message": "Task status updated successfully", "task": task_data}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500