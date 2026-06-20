from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from socketio_setup import socketio
from bson import ObjectId
import pytz


from decorators import token_required, time_tracking_db, notification_collection, collection, upload_to_firebase, find_user_info, deleted_employees_collection

emp_work_update_app = Blueprint('emp_work_update_app',__name__)

@emp_work_update_app.route('/api/add_work_update', methods=['POST'])
@token_required
def add_work_update(current_user):
    try:
        # Extract data from the request
        date = request.form.get('date')
        work_update = request.form.get('work_update')
        employee_id = str(current_user['_id'])
        work_url = request.form.get('work_url', '')
        attachment_urls = []
        time_zone = str(current_user['time_zone'])
        frontend_timezone = pytz.timezone(time_zone)
        frontend_time = datetime.now(frontend_timezone).strftime('%Y-%m-%d %H:%M:%S')
        # Check if there are attachments
        attachments = request.files.getlist('attachment')

        # Check if the user has an existing time_tracking entry for the specified date
        user = collection.find_one({"_id": ObjectId(employee_id)})
        if not user:
            return jsonify({"error": "User not found"}), 404

        time_tracking = user.get("time_tracking", {})
        existing_document = next((item for item in time_tracking if item["date"] == date), None)

        if attachments:
            # Upload each attachment to Firebase storage with folder structure
            for attachment in attachments:
                attachment_url = upload_to_firebase(attachment,'Work_Update' ,employee_id)
                attachment_urls.append(attachment_url)

        # Check if there is an existing attachment_urls
        if existing_document and existing_document.get("attachment_urls"):
            # Append existing attachment_urls to the list
            attachment_urls += existing_document["attachment_urls"]

        # Update work update and attachment_urls in the time_tracking list
        new_entry = {
            "date": date,
            "work_update": work_update,
            "work_url": work_url,
            "workupdate_time": frontend_time,
            "attachment_urls": attachment_urls
        }

        if existing_document:
            # Update the existing entry
            existing_document.update(new_entry)
        else:
            # Add a new entry for the specified date
            # time_tracking.append(new_entry)
            return jsonify({"message": "Work update cannot be added, please make yourself active"}), 200

        # Update the user document with the modified time_tracking list
        collection.update_one(
            {"_id": ObjectId(employee_id)},
            {"$set": {"time_tracking": time_tracking}}
        )

        # Save notification in the notification_collection
        notification_data = {
            'user_id': employee_id,
            'message': 'New Work update submitted.',
            'timestamp': datetime.now(frontend_timezone),
            'isSeen': False,
            'adminSeen': False,
            'company': current_user['company'],
            'user_info': find_user_info(employee_id)
        }
        notification_collection.insert_one(notification_data)
        notification_data['_id'] = str(notification_data['_id'])
        notification_data['timestamp'] = notification_data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
        # Emitting a socket notification
        socketio.emit(f'notification_{employee_id}', [notification_data], namespace='/socket_connection')
        socketio.emit(f'notification_{current_user["company"]}', [notification_data], namespace='/socket_connection')

        return jsonify({
            "message": "Work update added successfully",
            "data": {
                "work_update": work_update,
                "attachment_urls": attachment_urls,
                "work_url": work_url,
                "workupdate_time": frontend_time
            }
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@emp_work_update_app.route('/api/get_work_update', methods=['GET'])
@token_required
def get_work_update(current_user):
    try:
        date_param = request.args.get('date')
        employee_id = request.args.get('employee_id')

        if not employee_id:
            employee_id = str(current_user['_id'])

        details = find_user_info(employee_id)

        user = collection.find_one({"_id": ObjectId(employee_id)})
        if not user:
            user = deleted_employees_collection.find_one({"_id": ObjectId(employee_id)})
            if not user:
                return jsonify({"error": "User not found"}), 404

        time_tracking = user.get("time_tracking", [])

        # Set default values
        if date_param == 'all':
            # Retrieve all work updates in decreasing order of date
            results = sorted(time_tracking, key=lambda x: x['date'], reverse=True)
        else:
            # Convert date string to datetime
            end_date = datetime.now()
            start_date = end_date - timedelta(days=6)  # Last 7 days

            if date_param:
                # If a specific date is provided, use it for filtering
                end_date = datetime.strptime(date_param, '%Y-%m-%d')
                start_date = end_date - timedelta(days=6)  # Last 7 days

            # Filter time_tracking entries for the specified date range
            results = [entry for entry in time_tracking if start_date <= datetime.strptime(entry['date'], '%Y-%m-%d') <= end_date]
            # Sort the filtered results in decreasing order of date
            results = sorted(results, key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'), reverse=True)

        response_list = []

        for result in results:
            work_update = result.get('work_update', '')
            attachment_url = result.get('attachment_urls', [])
            work_url = result.get('work_url', '')
            workupdate_time = result.get('workupdate_time', '')

            response = {
                "date": result['date'],
                "work_update": work_update,
                "attachment_url": attachment_url,
                "work_url": work_url,
                "time": workupdate_time
            }

            response_list.append(response)

        return jsonify(response_list, {"employee_details": details})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@emp_work_update_app.route('/api/delete_attachment', methods=['POST'])
@token_required
def delete_attachment(current_user):
    try:
        employee_id = str(current_user["_id"])
        date = request.form.get('date')
        url_to_delete = request.form.get('url')

        time_zone = str(current_user['time_zone'])
        frontend_timezone = pytz.timezone(time_zone)
        frontend_time = datetime.now(frontend_timezone).strftime('%Y-%m-%d %H:%M:%S')

        user = collection.find_one({"_id": ObjectId(employee_id)})
        if not user:
            return jsonify({"error": "User not found"}), 404

        time_tracking = user.get("time_tracking", [])
        for entry in time_tracking:
            if entry["date"] == date:
                if "attachment_urls" in entry:
                    # Remove the specified URL from the attachment_urls list
                    attachment_urls = entry["attachment_urls"]
                    attachment_urls = [url for url in attachment_urls if url != url_to_delete]

                    # Update the document with the modified attachment_urls list
                    collection.update_one(
                        {"_id": ObjectId(employee_id), "time_tracking.date": date},
                        {
                            "$set": {
                                "time_tracking.$.attachment_urls": attachment_urls,
                                "time_tracking.$.workupdate_time": frontend_time
                            }
                        }
                    )

                    return jsonify({"message": "URL deleted successfully"})

        return jsonify({"error": "Document or URL not found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500


