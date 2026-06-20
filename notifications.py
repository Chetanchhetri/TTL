from flask import request, jsonify

from flask import Blueprint, request, jsonify
from socketio_setup import socketio
import pymongo, pytz
from datetime import datetime, timedelta

from decorators import token_required, notification_collection,token_required_admin, company_collection, find_user_info

notifications_app = Blueprint('notifications_app',__name__)

@notifications_app.route("/api/delete_notifications", methods=["POST"])
@token_required
def delete_notifications(current_user):
    _id = str(current_user['_id'])

    # Assuming notification_collection is your MongoDB collection for notifications
    result = notification_collection.delete_many({'user_id': _id})

    if result.deleted_count > 0:
        return jsonify({'status': 'success', 'message': 'Notifications deleted successfully'})
    else:
        return jsonify({'status': 'error', 'message': 'No notifications found for the user'})


@socketio.on("get_alert_initals", namespace='/socket_connection')
def get_initial_alert(message):
    user_id = message
    if user_id:
        notification = {"message":"Connected"}
        # Emit the notification to the connected user
        socketio.emit(f'alert_{user_id}', notification, namespace='/socket_connection')

@notifications_app.route('/api/update_notification', methods=['PUT'])
@token_required
def update_notification(current_user):
    try:
        notification_id = request.json.get('_id')
        notification_collection.update_many({'user_id': str(notification_id),'type': {'$exists': False}}, {'$set': {'isSeen': True}})
        notifications = notification_collection.find({'user_id': str(notification_id),'type': {'$exists': False}}).sort('timestamp', pymongo.DESCENDING)
        sorted_notifications = list(notifications)
        notification_list = []
        for notification in sorted_notifications:
            # Convert the MongoDB Date type to a string representation
            if isinstance(notification.get('timestamp'), datetime):
                notification['timestamp'] = notification['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            
            notification['_id'] = str(notification['_id'])
            notification_list.append(notification)
        # Emit the notification to the connected user
        socketio.emit(f'notifications_{str(notification_id)}', notification_list, namespace='/socket_connection')        
        return {'message': 'Notifications updated successfully','data':notification_list}, 200

    except Exception as e:
        return {'error': str(e)}, 500

@notifications_app.route('/api/update_notification_admin', methods=['PUT'])
@token_required_admin
def update_notification_admin(current_user):
    try:
        company = current_user['company']
        notification_collection.update_many({'company': company,'type': {'$exists': False}}, {'$set': {'adminSeen': True}})
        notifications = notification_collection.find({'company': company,'type': {'$exists': False}}).sort('timestamp', pymongo.DESCENDING)
        sorted_notifications = list(notifications)
        notification_list = []
        for notification in sorted_notifications:
            # Convert the MongoDB Date type to a string representation
            notification['timestamp'] = notification['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            notification['_id'] = str(notification['_id'])
            notification_list.append(notification)
        # Emit the notification to the connected user
        socketio.emit(f'notification_{company}', notification_list, namespace='/socket_connection')        
        return {'message': 'Notifications updated successfully','data':notification_list}, 200

    except Exception as e:
        return {'error': str(e)}, 500

@notifications_app.route('/api/update_alert', methods=['PUT'])
@token_required
def update_alert(current_user):
    try:
        notification_id = request.json.get('_id')
        notification_collection.update_many({'user_id': str(notification_id),'type': {'$exists': True}}, {'$set': {'isSeen': True}})
        notifications = notification_collection.find({'user_id': str(notification_id),'type': {'$exists': True}}).sort('timestamp', pymongo.DESCENDING)
        sorted_notifications = list(notifications)
        notification_list = []
        for notification in sorted_notifications:
            # Convert the MongoDB Date type to a string representation
            notification['timestamp'] = notification['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            notification['_id'] = str(notification['_id'])
            notification_list.append(notification)
        # Emit the notification to the connected user
        socketio.emit(f'notifications_{str(notification_id)}', notification_list, namespace='/socket_connection')        
        return {'message': 'Notifications updated successfully','data':notification_list}, 200

    except Exception as e:
        return {'error': str(e)}, 500

@notifications_app.route('/api/get_initials_noti_api', methods=['GET'])
@token_required
def get_initial_noti(current_user):
    # user_id = request.json.get('user_id')
    user_id = str(current_user['_id'])
    if user_id:
        # Retrieve and send notifications to the connected user
        notifications = notification_collection.find({'user_id': user_id, 'type': {'$exists': False}}).sort('timestamp', pymongo.DESCENDING)
        notification_list = []
        frontendtime = pytz.timezone('Asia/Kolkata')
        for notification in notifications:
            # Convert the MongoDB Date type to a string representation
            try:
                utc_timestamp = notification['timestamp'] 
                front_timestamp = utc_timestamp.astimezone(frontendtime)
                # Convert the MongoDB Date type to a string representation
                notification['timestamp'] = front_timestamp.strftime('%Y-%m-%d %H:%M:%S')
            except:
                notification['timestamp'] = notification['timestamp']
            notification['_id'] = str(notification['_id'])
            notification_list.append(notification)
        return jsonify(notification_list)
    else:
        return jsonify({'error': 'User ID not provided'})

@notifications_app.route('/api/admin_initials_noti_api', methods=['GET'])
@token_required_admin
def admin_initial_noti(current_user):
    company = str(current_user['company'])
    
    if company:
        # Get pagination parameters from query string
        try:
            page = int(request.args.get('page', 1))  # Default page is 1
            limit = int(request.args.get('limit', 20))  # Default limit is 10
        except ValueError:
            return jsonify({'error': 'Invalid pagination parameters'}), 400
        
        # Ensure page and limit are positive integers
        if page < 1 or limit < 1:
            return jsonify({'error': 'Page and limit must be positive integers'}), 400

        # Calculate how many documents to skip
        skip = (page - 1) * limit

        # Retrieve notifications for the given company with pagination and sorting
        notifications = notification_collection.find(
            {'company': company, 'type': {'$exists': False}}
        ).sort('timestamp', pymongo.DESCENDING).skip(skip).limit(limit)

        notification_list = []
        frontendtime = pytz.timezone('Asia/Kolkata')

        for notification in notifications:
            try:
                # Convert the MongoDB UTC timestamp to the frontend time zone
                utc_timestamp = notification['timestamp']
                front_timestamp = utc_timestamp.astimezone(frontendtime)
                notification['timestamp'] = front_timestamp.strftime('%Y-%m-%d %H:%M:%S')
            except Exception as e:
                notification['timestamp'] = str(notification['timestamp'])  # Fallback in case of error

            notification['_id'] = str(notification['_id'])
            notification_list.append(notification)

        # Get total notification count to assist in pagination
        total_notifications = notification_collection.count_documents({'company': company, 'type': {'$exists': False}})

        # Return the paginated result
        return jsonify({
            'status':True,
            'notifications': notification_list,
            'total': total_notifications,
            'page': page,
            'limit': limit,
            'total_pages': (total_notifications + limit - 1) // limit  # Calculate total pages
        })
    else:
        return jsonify({'error': 'User ID not provided'}), 400

@notifications_app.route('/api/get_initials_alert_api', methods=['GET'])
@token_required
def get_initial_alert(current_user):
    # user_id = request.json.get('user_id')
    user_id = str(current_user['_id'])
    if user_id:
        # Retrieve and send notifications to the connected user
        notifications = notification_collection.find({'user_id': user_id, 'type': {'$exists': True}}).sort('timestamp', pymongo.DESCENDING)
        notification_list = []

        frontendtime = pytz.timezone('Asia/Kolkata')

        for notification in notifications:
            utc_timestamp = notification['timestamp']
            front_timestamp = utc_timestamp.astimezone(frontendtime)
            # Convert the MongoDB Date type to a string representation
            notification['timestamp'] = front_timestamp.strftime('%Y-%m-%d %H:%M:%S')
            notification['_id'] = str(notification['_id'])
            notification_list.append(notification)
        return jsonify(notification_list)
    else:
        return jsonify({'error': 'User ID not provided'})



@socketio.on("get_initals", namespace='/socket_connection')
def get_initial_noti(message):
    user_id = message
    if user_id:
        # Retrieve only the latest 20 notifications (excluding alerts), sorted by timestamp descending
        notifications = notification_collection.find(
            {'user_id': user_id, 'type': {'$ne': 'alert'}}
        ).sort('timestamp', pymongo.DESCENDING).limit(20)

        sorted_notifications = list(notifications)
        notification_list = []
        frontendtime = pytz.timezone('Asia/Kolkata')
        for notification in sorted_notifications:
            try:
                utc_timestamp = notification['timestamp']
                front_timestamp = utc_timestamp.astimezone(frontendtime)
                notification['timestamp'] = front_timestamp.strftime('%Y-%m-%d %H:%M:%S')
            except:
                notification['timestamp'] = notification['timestamp']
            notification['_id'] = str(notification['_id'])
            notification_list.append(notification)

        # Emit the notification to the connected user
        socketio.emit(f'notifications_{user_id}', notification_list, namespace='/socket_connection')

@socketio.on("get_initals_admin", namespace='/socket_connection')
def get_initial_noti_admin(message):
    company = message
    if company:
        # Retrieve and send notifications to the connected user
        notifications = notification_collection.find({'company': company, 'type': {'$ne': 'alert'}}).sort('timestamp', pymongo.DESCENDING)
        sorted_notifications = list(notifications)
        notification_list = []
        # Define the Asia/Kolkata timezone
        frontendtime = pytz.timezone('Asia/Kolkata')
        
        for notification in sorted_notifications:
            try:
                # Ensure that the timestamp is timezone-aware
                utc_timestamp = notification['timestamp']
                
                if utc_timestamp.tzinfo is None:
                    # Assume the timestamp is in UTC and make it timezone-aware
                    utc_timestamp = pytz.utc.localize(utc_timestamp)

                # Convert to the desired timezone (Asia/Kolkata)
                front_timestamp = utc_timestamp.astimezone(frontendtime)
                
                # Format the timestamp as a string for display
                notification['timestamp'] = front_timestamp.strftime('%Y-%m-%d %H:%M:%S')
            except Exception as e:
                # In case of any errors, keep the original timestamp
                notification['timestamp'] = str(notification['timestamp'])  # Convert it to string for safety

            notification['_id'] = str(notification['_id'])  # Convert ObjectId to string
            notification_list.append(notification)

        # Emit the notification to the connected user
        socketio.emit(f'notification_{company}', notification_list, namespace='/socket_connection')


@socketio.on("create_notification", namespace='/socket_connection')
def create_notification(data):
    user_id = data.get('user_id')
    notification_content = data.get('message')

    if user_id and notification_content:
        # Create the notification document
        notification_doc = {
            'user_id': user_id,
            'message': notification_content,
            'timestamp': datetime.now(),
            'seen': False
        }
        notification_doc2 = {
            'user_id': str(user_id),
            'message': notification_content,
            'timestamp': str(datetime.now()),
            'seen': False
        }

        # Insert the notification document into the database
        notification_collection.insert_one(notification_doc)

        # Emit the notification to the connected user
        socketio.emit(f'notification_{user_id}', [notification_doc2], namespace='/socket_connection')


@notifications_app.route('/api/create_notification', methods=['POST'])
def create_notification():
    try:
        data = request.get_json()
        user_types = data.get('userType', '')
        employee_id = data.get('employee_id')
        message = data.get('message')
        company = data.get('company', '')
        type = data.get('type', '')

        if not user_types or not message:
            return jsonify({'error': 'userType and message are required'}), 400
        
        if user_types != 'admin' and not employee_id:
            return jsonify({'error': 'employee_id is required for user notifications'}), 400
        
        if user_types == 'admin' and not company:
            return jsonify({'error': 'company is required for admin notifications'}), 400
        
        time_zone = company_collection.find_one({"company": company}).get('time_zone')
        frontend_timezone = pytz.timezone(time_zone)
        timestamp = datetime.now(frontend_timezone)
        
        if user_types == 'admin':
            notification_data = {
                'user_id': employee_id,
                'message': message,
                'timestamp': timestamp,
                'isSeen': False,
                'adminSeen': False,
                'company': company,
                'user_info': find_user_info(employee_id)
            }
            result = notification_collection.insert_one(notification_data)
            notification_data['_id'] = str(result.inserted_id)
            notification_data['timestamp'] = timestamp.strftime('%Y-%m-%d %H:%M:%S')

            # Emit to specific user and company
            socketio.emit(f'notification_{employee_id}', [notification_data], namespace='/socket_connection')
            socketio.emit(f'notification_{company}', [notification_data], namespace='/socket_connection')
        else:
            notification_data = {
                'user_id': employee_id,
                'message': message,
                'timestamp': timestamp,
                'isSeen': False
            }
            if type: notification_data['type'] = type
            
            result = notification_collection.insert_one(notification_data)
            
            notification_data['_id'] = str(result.inserted_id)
            notification_data['timestamp'] = timestamp.strftime('%Y-%m-%d %H:%M:%S')
            if type and type != "alert": socketio.emit(f'notification_{employee_id}', [notification_data], namespace='/socket_connection')
        return jsonify({
            'status': True,
            'data': notification_data
        }), 200

    except Exception as e:
        return jsonify({'error': str(e), 'status': False}), 500