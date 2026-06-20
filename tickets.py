from flask import request, jsonify
from bson import ObjectId
from flask import Blueprint, request, jsonify
from socketio_setup import socketio
from datetime import datetime
import pytz
from flask_socketio import SocketIO, join_room, leave_room, emit

from decorators import ticket_collection,collection,chat_collection, token_required, token_required_admin, collection, find_user_info

ticket_app = Blueprint('ticket_app',__name__) 

@ticket_app.route('/api/create_ticket', methods=['POST'])
@token_required
def create_ticket(current_user):
    try:
        _id = str(current_user['_id'])
        company = current_user['company']
        data = request.get_json()

        time_zone = current_user.get('time_zone', 'UTC')
        frontend_timezone = pytz.timezone(time_zone)
        frontend_time = datetime.now(frontend_timezone).strftime("%Y-%m-%d %H:%M:%S")

        reason = data.get('reason')
        description = data.get('description')

        ticket_data = {
            'emp_id': str(_id),
            'reason': reason,
            'description': description,
            'datetime': frontend_time,
            'action': 'active',
            'company': company
        }

        ticket_id = ticket_collection.insert_one(ticket_data).inserted_id

        ticket_data2 = {
            'reason': reason,
            'description': description,
            'datetime': frontend_time,
            'action': 'active',
            'company': company,
            'ticket_id': str(ticket_id)
        }

        return jsonify(ticket_data2)

    except Exception as e:
        response = {
            'status': 'error',
            'message': str(e)
        }
        return jsonify(response)


@ticket_app.route('/api/tickets/<user_id>', methods=['GET'])
@token_required
def get_tickets_by_user_id(current_user, user_id):
    try:
        # Check if the current user is authorized to access this endpoint
        if str(current_user['_id']) != user_id:
            return jsonify({'status': 'error', 'message': 'Unauthorized access'}), 403

        # Fetch all tickets with the given user_id
        tickets = ticket_collection.find({'emp_id': user_id})

        # Convert ObjectId to str for JSON serialization
        tickets_data = [{'_id': str(ticket['_id']), 'reason': ticket['reason'], 'description': ticket['description'], 'datetime': str(ticket['datetime']), 'action': ticket['action']} for ticket in tickets]

        return jsonify({'status': 'success', 'tickets': tickets_data})

    except Exception as e:
        response = {
            'status': 'error',
            'message': str(e)
        }
        return jsonify(response)


@ticket_app.route('/api/ticket_employees', methods=['GET'])
@token_required_admin
def get_employee_details(current_user):
    try:
        # Fetch all unique employee_ids from the tickets
        employee_ids = ticket_collection.distinct('emp_id')
        company = current_user['company']
        employee_details = []

        for emp_id in employee_ids:
            # Get employee details
            employee_document = collection.find_one({"company": company, "_id": ObjectId(emp_id)})
            if employee_document:
                employee_data = {
                    'employee_id': emp_id,
                    'profile_pic': employee_document.get("profile_pic", ""),
                    'email': employee_document.get("email", ""),
                    'phone': employee_document.get("phone", ""),
                    'name': employee_document.get("name", "")
                }

                # Count total tickets raised by the employee
                total_tickets = ticket_collection.count_documents({'emp_id': emp_id})

                # Count total active tickets raised by the employee
                total_active_tickets = ticket_collection.count_documents({'emp_id': emp_id, 'action': 'active'})

                # Get the date of the last ticket raised by the employee
                last_ticket = ticket_collection.find({'emp_id': emp_id}).sort('datetime', -1).limit(1)
                last_ticket_date = None
                last_ticket_status = None
                for ticket in last_ticket:
                    last_ticket_date = ticket['datetime']
                    last_ticket_status = ticket['action']
                    break

                # Get all tickets of the employee in decreasing order of datetime
                all_tickets = ticket_collection.find({'emp_id': emp_id}).sort('datetime', -1)
                employee_data['all_tickets'] = [
                    {
                        '_id': str(ticket['_id']),
                        'reason': ticket['reason'],
                        'description': ticket['description'],
                        'datetime': str(ticket['datetime']),
                        'action': ticket['action']
                    }
                    for ticket in all_tickets
                ]            
                employee_data['total_tickets'] = total_tickets
                employee_data['total_active_tickets'] = total_active_tickets
                employee_data['last_ticket_date'] = str(last_ticket_date) if last_ticket_date else None
                employee_data['ticket_status'] = str(last_ticket_status) if last_ticket_status else None

                employee_details.append(employee_data)

        return jsonify({'status': 'success', 'employees': employee_details})

    except Exception as e:
        response = {
            'status': 'error',
            'message': str(e)
        }
        return jsonify(response)



@ticket_app.route('/api/update_ticket_action', methods=['POST'])
@token_required_admin
def update_ticket_action(current_user):
    try:
        data = request.get_json()
        ticket_id = data.get('ticket_id')
        new_action = data.get('action')

        # Validate if the ticket exists
        ticket = ticket_collection.find_one({'_id': ObjectId(ticket_id)})
        if not ticket:
            return jsonify({'status': 'error', 'message': 'Ticket not found or unauthorized access'}), 404

        # Update the ticket action
        modified_ticket = ticket_collection.update_one({'_id': ObjectId(ticket_id)}, {'$set': {'action': new_action}})

        return jsonify({'status': 'success', 'message': f'Ticket action updated to {new_action}'})

    except Exception as e:
        response = {
            'status': 'error',
            'message': str(e)
        }
        return jsonify(response)


@socketio.on('message', namespace='/socket_connection')
def handle_message(data):
    room_id = data.get('room_id')
    sender_id = data.get('sender_id')
    receiver_id = data.get('receiver_id')
    message = data.get('message')
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Find or create a document for the room
    room_document = chat_collection.find_one_and_update(
        {'_id': room_id},
        {'$setOnInsert': {'messages': []}},
        upsert=True,
        return_document=True
    )

    # Append the new message to the messages list
    room_document['messages'].append({
        'sender_id': sender_id,
        'receiver_id': receiver_id,
        'message': message,
        'timestamp': timestamp
    })

    # Update the document in the collection
    chat_collection.update_one({'_id': room_id}, {'$set': {'messages': room_document['messages']}})

    # Broadcast the message to all clients in the room
    emit(f'message_{room_id}', {
        'room_id': room_id,
        'sender_info': find_user_info(sender_id),
        'receiver_info': find_user_info(receiver_id),
        'message': message,
        'timestamp': timestamp
    }, namespace='/socket_connection', broadcast=True)



@socketio.on('get_chat_history', namespace='/socket_connection')
def get_chat_history(data):
    room_id = data

    if room_id:
        room = chat_collection.find_one({'_id': str(room_id)})
        if room:
            chat_history = room.get('messages', [])
            enriched_history = []
            for message in chat_history:
                sender_info = find_user_info(message['sender_id'])
                receiver_info = find_user_info(message['receiver_id'])

                enriched_message = {
                    'sender_info': sender_info,
                    'receiver_info': receiver_info,
                    'message': message['message'],
                    'timestamp': message['timestamp']
                }

                enriched_history.append(enriched_message)
            emit('chat_history', {'room_id': room_id, 'history': enriched_history})
        else:
            emit('chat_history', {'room_id': room_id, 'history': []})
    else:
        emit('chat_history', {'error': 'No room_id provided'})

