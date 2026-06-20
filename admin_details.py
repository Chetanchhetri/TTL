from flask import Blueprint, request, jsonify
from socketio_setup import socketio
from bson import ObjectId
import pytz, jwt, os
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import emit
# from fpdf import FPDF
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

from decorators import find_user_info, token_required_admin,leads_collection ,chat_collection,find_admin_info,master_admin_collection, company_collection, collection, storage, moms_collection, upload_to_firebase, deleted_employees_collection, plans_collection

admin_details_app = Blueprint('admin_details_app',__name__)

SECRET_KEY = os.getenv('SECRET_KEY')

@admin_details_app.route('/api/verify-token-admin', methods=['GET'])
@token_required_admin
def verify_token_admin(current_user):
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

@admin_details_app.route('/api/update_admin_password', methods=['POST'])
@token_required_admin
def update_admin_password(current_user):
    _id = str(current_user['_id'])
    old_password = request.form.get("password")
    new_password = request.form['newPassword']

    admin_data = master_admin_collection.find_one({'_id': ObjectId(_id)})
    email = admin_data['email'] if admin_data else None
    lead_data = leads_collection.find_one({'email': email}) if email else None

    password_updated = False  # Track if password was updated

    if admin_data:
        if check_password_hash(admin_data['password'], old_password):
            result = master_admin_collection.update_one(
                {'_id': ObjectId(_id)},
                {'$set': {'password': generate_password_hash(new_password)}}
            )
            password_updated = result.modified_count > 0
        else:
            return jsonify({'message': 'Wrong password', 'status': False}), 401  # Unauthorized

    if lead_data:
        if check_password_hash(lead_data['password'], old_password):
            result = leads_collection.update_one(
                {'email': email},
                {'$set': {'password': generate_password_hash(new_password)}}
            )
            password_updated = password_updated or result.modified_count > 0
        else:
            return jsonify({'message': 'Wrong password', 'status': False}), 401  # Unauthorized

    if password_updated:
        return jsonify({'message': 'Credentials updated successfully', 'status': True}), 200
    else:
        return jsonify({'message': 'Failed to update credentials', 'status': False}), 500  # Internal Server Error




@admin_details_app.route('/api/update_admin_details', methods=['POST'])
@token_required_admin
def update_admin_details(current_user):
    try:
        # Extract data from form
        _id = str(current_user["_id"])
        
        name = request.form.get("name")
        new_username = request.form.get("username")
        email = request.form.get("email")
        phone = request.form.get("phone")
        language = request.form.get("language")
        dob = request.form.get("dob")
        country = request.form.get("country")
        city = request.form.get("city")
        bio = request.form.get("bio")
        address = request.form.get("address")

        # Find the user to update
        user_to_update = master_admin_collection.find_one({'_id': ObjectId(_id)})

        if not user_to_update:
            return jsonify({'message': 'User not found'}), 404

        # Update fields if present
        update_data = {}
        if new_username: update_data['username'] = new_username       
        if name: update_data['name'] = name
        if email: update_data['email'] = email
        if phone: update_data['phone'] = phone
        if language: update_data['language'] = language
        if dob: update_data['dob'] = dob
        if country: update_data['country'] = country
        if city: update_data['city'] = city
        if bio: update_data['bio'] = bio
        if address: update_data['address'] = address
        if 'profile_pic' in request.files:
            update_data['profile_pic'] = upload_to_firebase(request.files.get('profile_pic'),'profile_pic',_id)

        if 'banner_pic' in request.files:
            update_data['banner_pic'] = upload_to_firebase(request.files.get('banner_pic'),'banner_pic',_id)

        if update_data:
            # Perform the update operation
            master_admin_collection.update_one({'_id': ObjectId(_id)}, {"$set": update_data})

        # Fetch updated user details
        updated_user_data = master_admin_collection.find_one({'_id': ObjectId(_id)}, {'password': 0})  # Exclude password

        # Fetch company information
        company = str(updated_user_data['company'])
        company_info = company_collection.find_one({"company": company}, {"time_zone": 1, "email": 1, "regex_code": 1, "plan_list": 1})
        time_zone = company_info.get("time_zone")
        company_email = company_info.get("email")

        updated_user_data['_id'] = _id
        updated_user_data['access'] = updated_user_data.get('access', ["admin"])

        updated_user_data['trial_plan'] = "683679b3d625439aa30a1323"
        updated_user_data['trial_used'] = False
        # Check if the company has already purchased the specific trial plan
        trial_plan_id = ObjectId("683679b3d625439aa30a1323")
        for plan in company_info.get('plan_list', []):
            if plan.get('plan_id') == trial_plan_id:
                updated_user_data['trial_used'] = True

        return jsonify({
            "message": "Admin data updated successfully",
            "details": updated_user_data,
            "company_email": company_email
        }), 200
    
    except Exception as e:
        return jsonify({"message": f"An error occurred: {str(e)}"}), 500


@admin_details_app.route('/api/company_regex', methods=['POST'])
@token_required_admin
def handle_regex_company(current_user):

    employee_id = request.json.get("employee_id")
    company_name = current_user["company"]

    # Retrieve company information by company_id
    company = company_collection.find_one({"company":company_name})
    if company:
        if 'regex_code' in company:
            return jsonify({'error': 'regex_code already exists for this company'}), 400
        else:
            company['regex_code'] = str(employee_id)
            company_collection.update_one({"company":company_name},{"$set":company})
            return jsonify({'message': 'regex_code added successfully'})
    else:
        return jsonify({'error': 'Company not found'}), 404
    
@admin_details_app.route('/api/edit_company', methods=['POST'])
@token_required_admin
def edit_company(current_user):
    try:
        company_name = current_user["company"]

        # Fetch the company document
        company = company_collection.find_one({"company": company_name})
        if not company:
            return jsonify({"error": "Company not found"}), 404

        # Handle logo upload
        if 'logo' in request.files:
            logo_file = request.files['logo']
            file_url = upload_to_firebase(logo_file, 'Company_Profile', company["email"])
        else:
            file_url = "https://d1csarkz8obe9u.cloudfront.net/posterpreviews/company-logo-design-template-7c91d15837ad91ad70909087e4a2955d_screen.jpg?ts=1694257442"

        # Update company logo in the database
        result = company_collection.update_one(
            {"company": company_name},
            {"$set": {"logo": file_url}}
        )

        if result.modified_count > 0:
            return jsonify({"message": "Company logo updated successfully", "logo": file_url}), 200
        else:
            return jsonify({"message": "Logo already up to date", "logo": file_url}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_details_app.route('/api/save_work_schedule', methods=['POST'])
@token_required_admin
def save_work_schedule(current_user):
    try:
        # Extract fields
        work_start_str = request.json.get("work_start")
        work_end_str = request.json.get("work_end")
        num_day = request.json.get("num_day")
        departments = request.json.get("departments")

        if departments:
            departments = [d.strip() for d in departments]

        company_name = current_user["company"]
        company = company_collection.find_one({"company": company_name})

        if not company:
            return jsonify({'error': 'Company not found'}), 404

        update_fields = {}

        # Validate and update work schedule fields
        if work_start_str and work_end_str and num_day:
            try:
                work_start = datetime.strptime(work_start_str, "%H:%M").time()
                work_end = datetime.strptime(work_end_str, "%H:%M").time()
            except ValueError:
                return jsonify({'error': 'Invalid time format'}), 400

            update_fields["work_schedule"] = {
                "work_start": work_start.strftime("%H:%M"),
                "work_end": work_end.strftime("%H:%M"),
                "num_day": num_day
            }

        # Check for removed departments
        if departments is not None:
            old_departments = company.get("departments", [])
            removed_departments = list(set(old_departments) - set(departments))

            update_fields["departments"] = departments

            if removed_departments:
                # Set department="" for all employees in removed departments
                collection.update_many(
                    {
                        "company": company_name,
                        "department": {"$in": removed_departments}
                    },
                    {"$set": {"department": ""}}
                )

        if update_fields:
            company_collection.update_one(
                {"company": company_name},
                {"$set": update_fields}
            )

        return jsonify({'message': 'Work schedule updated successfully'}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
            
@admin_details_app.route('/api/get_work_schedule', methods=['GET'])            
@token_required_admin
def get_work_schedule(current_user):
    try:
        # Assuming 'company' is still a field in your current_user object
        company_name = current_user["company"]

        # Retrieve company information by company_id
        company = company_collection.find_one({"company": company_name})
        if company:
            # Check if the 'work_schedule' field exists in the company document
            data = {}

            if 'work_schedule' in company: data = company['work_schedule']
            else: data = {"work_start": "", "work_end": "", "num_day": ""}
            
            other_data = {}
            if 'email_cred' in company: 
                email_cred = company['email_cred']
                if email_cred["email"] and email_cred["password"]: 
                    email_cred['password'] = True
                    other_data['email_cred'] = email_cred
                else: other_data['email'] = {"email_cred": "", "password": False}

            if 'email_stats' in company: other_data['email_stats'] = company['email_stats']
            else: other_data['email_stats'] = {}

            if 'departments' in company: data['departments'] = company['departments']
            else: data['departments'] = []
            data['email'] = other_data
            return jsonify(data)
        else:
            return jsonify({'error': 'Company not found'}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def generate_regex(employee_id):
    # Create a regex pattern based on the structure of the employee_id
    pattern = ''
    for char in employee_id:
        if char.isalpha():
            pattern += char  # Keep alphabets as they are
        elif char.isdigit():
            pattern += '\\d'
        elif char == '_':
            pattern += '_'
        elif char == '-':
            pattern += '-'
    return f'^{pattern}$'


@admin_details_app.route('/api/give_access', methods=['POST'])
@token_required_admin
def give_access(current_user):
    try:
        employee_id = request.json.get('employee_id')
        access_given = request.json.get('access_given')
        not_access = request.json.get('not_access')  # New field

        _id = str(current_user['_id'])
        time_zone = str(current_user['time_zone'])
        frontend_timezone = pytz.timezone(time_zone)
        frontend_time = datetime.now(frontend_timezone)

        # Validate input parameters
        if not employee_id:
            return jsonify({'error': 'Invalid input parameters'}), 400

        # Find the employee by employee_id
        employee = collection.find_one({'_id': ObjectId(employee_id)})
        if not employee:
            return jsonify({'error': 'Employee not found'}), 404

        # Prepare the new access information
        access_info = {
            'access_given': access_given if access_given is not None else [],
            'not_access': not_access if not_access is not None else [],  # Include not_access
            'datetime': frontend_time,
            'given_by': _id  # Replace with the actual admin username or ID
        }

        # Update the employee entry
        collection.update_one(
            {'_id': ObjectId(employee_id)},
            {'$set': {'access': access_info}}
        )
        return jsonify({'message': 'Access updated successfully', "status":True}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@socketio.on('send_message', namespace='/socket_connection')
def message_to_SA(data):
    frontend_timezone = pytz.timezone('Asia/Kolkata')
    frontend_time = datetime.now(frontend_timezone)
    room_id = data.get('room_id')
    sender_id = data.get('sender_id')
    receiver_id = data.get('receiver_id')
    message = data.get('message')
    timestamp = frontend_time.strftime("%Y-%m-%d %H:%M:%S")

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
        'sender_info': find_admin_info(sender_id),
        'receiver_info': find_admin_info(receiver_id),
        'message': message,
        'timestamp': timestamp
    }, namespace='/socket_connection', broadcast=True)

@socketio.on('admin_chat_history', namespace='/socket_connection')
def admin_chat_history(data):
    room_id = data

    if room_id:
        room = chat_collection.find_one({'_id': str(room_id)})
        if room:
            chat_history = room.get('messages', [])
            enriched_history = []
            for message in chat_history:
                sender_info = find_admin_info(message['sender_id'])
                receiver_info = find_admin_info(message['receiver_id'])

                enriched_message = {
                    'sender_info': sender_info,
                    'receiver_info': receiver_info,
                    'message': message['message'],
                    'timestamp': message['timestamp']
                }

                enriched_history.append(enriched_message)
            emit('previous_chats', {'room_id': room_id, 'history': enriched_history})
        else:
            emit('previous_chats', {'room_id': room_id, 'history': []})
    else:
        emit('previous_chats', {'error': 'No room_id provided'})

@admin_details_app.route('/api/get_ss_pdf', methods=['GET'])
@token_required_admin
def get_pdf_link(current_user):

    company = current_user['company']
    empId = request.args.get('empId')
    date = request.args.get('date')

    if not empId or not date:
        return jsonify({"error": "EmployeeID and date name must be provided"}), 400

    try:
        # Construct the full path of the file in Firebase storage
        file_path = f"ScreenShort_PDF/{empId}/{date}.pdf"

        # Get the URL of the file
        pdf_url = storage.child(file_path).get_url(None)

        return jsonify({'pdf_url': pdf_url, 'message': 'PDF link retrieved successfully', 'status': True}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_details_app.route('/api/get_ss', methods=['GET'])
@token_required_admin
def get_images(current_user):
    try:
        # Get the parameters from the request
        employee_id = request.args.get('employeeId')
        start_date = request.args.get('startDate')
        end_date = request.args.get('endDate')
        is_deleted = request.args.get('deleted', 'false').lower() == 'true'

        if not employee_id or not start_date or not end_date:
            return jsonify({'error': 'Missing required parameters', 'status': False}), 400

        # Validate date format
        try:
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
            end_date = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD.', 'status': False}), 400

        # Ensure end date is after start date
        if end_date < start_date:
            return jsonify({'error': 'End date must be after start date.', 'status': False}), 400

        target_collection = deleted_employees_collection if is_deleted else collection

        # Find the employee document by employee_id
        employee_doc = target_collection.find_one({'_id': ObjectId(employee_id)})
        if not employee_doc:
            return jsonify({'error': 'Employee not found', 'status': False}), 404

        # Filter time_tracking entries within the date range
        filtered_entries = [
            entry for entry in employee_doc.get('time_tracking', [])
            if start_date <= datetime.strptime(entry['date'], "%Y-%m-%d") <= end_date
        ]

        # Sort the entries by date and images by time in descending order
        sorted_entries = sorted(filtered_entries, key=lambda x: x['date'], reverse=True)
        for entry in sorted_entries:
            if 'images' in entry:
                entry['images'] = sorted(entry['images'], key=lambda x: x['time'])

        # Prepare the response with images
        images_response = [
            {
                'date': entry['date'],
                'images': entry['images']
            }
            for entry in sorted_entries if 'images' in entry
        ]

        return jsonify({'data': images_response, 'status': True}), 200

    except Exception as e:
        return jsonify({'error': str(e), 'status': False}), 500

# @admin_details_app.route('/api/generate_ss_pdf', methods=['POST'])
# @token_required_admin
# def generate_images_pdf(current_user):
#     try:
#         # Get the data from the request
#         employee_id = request.form.get('employeeId')
#         start_date = request.form.get('startDate')
#         end_date = request.form.get('endDate')

#         if not employee_id or not start_date or not end_date:
#             return jsonify({'error': 'Missing required fields', 'status': False}), 400

#         # Validate date format
#         try:
#             start_date = datetime.strptime(start_date, "%Y-%m-%d")
#             end_date = datetime.strptime(end_date, "%Y-%m-%d")
#         except ValueError:
#             return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD.', 'status': False}), 400

#         # Ensure end date is after start date
#         if end_date < start_date:
#             return jsonify({'error': 'End date must be after start date.', 'status': False}), 400

#         # Find the employee document by employee_id
#         employee_doc = collection.find_one({'_id': ObjectId(employee_id)})
#         if not employee_doc:
#             return jsonify({'error': 'Employee not found', 'status': False}), 404

#         # Filter time_tracking entries within the date range
#         filtered_entries = [
#             entry for entry in employee_doc.get('time_tracking', [])
#             if start_date <= datetime.strptime(entry['date'], "%Y-%m-%d") <= end_date
#         ]

#         # Sort the entries by date and images by time in descending order
#         sorted_entries = sorted(filtered_entries, key=lambda x: x['date'], reverse=True)
#         all_images = []
#         for entry in sorted_entries:
#             if 'images' in entry:
#                 sorted_images = sorted(entry['images'], key=lambda x: x['time'], reverse=True)
#                 all_images.extend([(entry['date'], img) for img in sorted_images])

#         if not all_images:
#             return jsonify({'error': 'No images found in the specified date range', 'status': False}), 404

#         # Create PDF
#         pdf = FPDF()
#         pdf.set_auto_page_break(auto=True, margin=15)

#         for date, image in all_images:
#             pdf.add_page()
#             pdf.set_font('Arial', 'B', 12)
#             pdf.cell(200, 10, f'Date: {date} Time: {image["time"]}', ln=True)

#             # Download the image from the URL
#             response = requests.get(image["url"])
#             if response.status_code == 200:
#                 img = Image.open(io.BytesIO(response.content))

#                 # Convert RGBA to RGB if necessary
#                 if img.mode == 'RGBA':
#                     img = img.convert('RGB')

#                 # Save the image to a temporary file
#                 with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_image:
#                     img.save(temp_image, format='JPEG')
#                     temp_image_path = temp_image.name

#                 # Add the image to the PDF
#                 pdf.image(temp_image_path, x=10, y=30, w=180)

#                 # Clean up the temporary file
#                 os.remove(temp_image_path)
#             else:
#                 pdf.cell(200, 10, f'Error loading image: {image["url"]}', ln=True)

#         # Save the PDF to a binary stream
#         pdf_output = io.BytesIO()
#         pdf.output(pdf_output)
#         pdf_output.seek(0)

#         # Get the public URL of the uploaded PDF
#         pdf_url = upload_report_firebase(pdf_output, f'SS_PDF/{current_user["company"]}', f'{employee_id}.pdf')

#         return jsonify({'message': 'PDF generated and uploaded successfully', 'pdf_url': pdf_url, 'status': True}), 200

#     except Exception as e:
#         return jsonify({'error': str(e), 'status': False}), 500

@admin_details_app.route('/api/moms/<employee_id>', methods=['GET'])
@token_required_admin
def get_employee_moms(current_user, employee_id):
    try:
        company = current_user.get("company")
        page = request.args.get('page', 1, type=int)
        per_page = 10

        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')

        # Parse date range if provided
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d') if start_date_str else None
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d') if end_date_str else None

        # Find the document with the given employeeId and company
        employee_moms = moms_collection.find_one({"employeeId": employee_id, "company": company})

        if not employee_moms:
            return jsonify({"message": "No MoMs found for the given employee"}), 404

        # Reverse the momList to get the most recent MoMs first
        reversed_moms = employee_moms["momList"][::-1]

        # Filter by date range if provided
        if start_date and end_date:
            reversed_moms = [
                mom for mom in reversed_moms
                if start_date <= datetime.strptime(mom['date'], '%Y-%m-%d') <= end_date
            ]

        # Get the MoMs with pagination
        total_moms = len(reversed_moms)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_moms = reversed_moms[start:end]

        return jsonify({
            "data": paginated_moms,
            "total_moms": total_moms,
            "page": page,
            "per_page": per_page,
            "message": "MoMs retrieved successfully",
            "status": True
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_details_app.route('/api/moms/recent', methods=['GET'])
@token_required_admin
def get_recent_moms(current_user):
    try:
        company = current_user.get("company")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        # Find all documents for the given company
        company_moms = moms_collection.find({"company": company})

        recent_moms = []

        # Filter and group MoMs by date
        for employee_moms in company_moms:
            employee_id = find_user_info(employee_moms["employeeId"])
            for mom in employee_moms["momList"]:
                mom_date = datetime.strptime(mom["date"], '%Y-%m-%d')
                if start_date <= mom_date <= end_date:
                    mom_entry = {
                        "employeeId": employee_id,
                        "date": mom["date"],
                        "momData": mom["momData"]
                    }
                    recent_moms.append(mom_entry)

        # Sort the MoMs by date in reverse order
        recent_moms.sort(key=lambda x: datetime.strptime(x["date"], '%Y-%m-%d'), reverse=True)


        return jsonify({
            "data": recent_moms,
            "message": "MoMs retrieved successfully",
            "status": True
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

@admin_details_app.route('/api/signup_copy', methods=['POST'])
def signup_copy():
    try:
        admin_id = request.json.get('admin_id')
        if not admin_id:
            return jsonify({"error": "Missing admin_id"}), 400

        # Try fetching from master_admin_collection
        admin_data = master_admin_collection.find_one({'_id': ObjectId(admin_id)})
        user_type = "master_admin"

        # Fallback to normal user collection
        if not admin_data:
            admin_data = collection.find_one(
                {'_id': ObjectId(admin_id), 'access.access_given': {'$exists': True, '$ne': []}},
                {'time_tracking': 0}
            )
            user_type = "employee_user"

        if not admin_data:
            return jsonify({"error": "Invalid admin_id"}), 401

        _id = str(admin_data['_id'])
        admin_data['_id'] = _id
        company = str(admin_data['company'])

        company_info = company_collection.find_one(
            {"company": company},
            {"time_zone": 1, "email": 1, "regex_code": 1, "plan_list": 1}
        )
        if not company_info:
            return jsonify({"error": "Associated company not found"}), 404

        time_zone = company_info.get("time_zone", "Asia/Kolkata")
        company_email = company_info.get("email")
        regex_code = company_info.get("regex_code", "")

        # Determine the last active or expired plan
        plan_list = company_info.get('plan_list', [])
        last_plan = None

        if plan_list:
            # Sort in descending order of date_of_expiry
            plan_list_sorted = sorted(
                plan_list,
                key=lambda x: datetime.strptime(x['date_of_expiry'], '%Y-%m-%d'),
                reverse=True
            )
            last_plan = plan_list_sorted[0]  # First one has the latest expiry
            last_plan['plan_id'] = str(last_plan.get('plan_id'))
            # Find the active plan
            active_plan = next((plan for plan in plan_list if plan.get('status') == 'Active'), None)
            if active_plan:
                curr_plan = active_plan
            else:
                curr_plan = last_plan  # If no active plan, fallback to last plan

            curr_plan['plan_id'] = str(curr_plan.get('plan_id'))
        # Generate JWT token
        # token = jwt.encode({'_id': _id, 'company': company, 'time_zone': time_zone}, SECRET_KEY)

        # Handle access defaults
        admin_data.setdefault('access', ["admin"] if user_type == "master_admin" else [])
        if not admin_data['access']:
            return jsonify({"message": "Login Unsuccessful", "status": False}), 401
        
        plan_details = None
        plan_details = plans_collection.find_one({"_id": ObjectId(last_plan["plan_id"])}, {"_id": 0})
        if curr_plan:
            plan_details = plans_collection.find_one({"_id": ObjectId(curr_plan["plan_id"])}, {"_id": 0})

        # Check if the trial plan was already used
        trial_plan_id = ObjectId("683679b3d625439aa30a1323")
        admin_data['trial_used'] = any(plan.get('plan_id') == trial_plan_id for plan in plan_list)
        admin_data['trial_plan'] = str(trial_plan_id)

        return jsonify({
            "message": "Login successful",
            "details": admin_data,
            "company_email": company_email,
            "regex_code": regex_code,
            "last_plan": last_plan,
            "curr_plan": curr_plan,
            "plan_details": plan_details
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
