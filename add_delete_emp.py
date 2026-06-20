from flask import Blueprint, request, jsonify
from datetime import datetime, date, timedelta
import pytz, re
from werkzeug.security import generate_password_hash
from socketio_setup import socketio
from bson import ObjectId
from collections import defaultdict

from decorators import token_required, token_required_admin, upload_to_firebase, collection, time_tracking_db, deleted_employees_collection, company_collection, find_user_info, find_users_info, token_required_admin_or_superadmin
from email_send import send_admin_details

add_delete_emp_app = Blueprint('add_delete_emp_app',__name__)

@add_delete_emp_app.route('/api/employee_details', methods=['POST'])
@token_required
def employee_details(current_user):
    try:
        request_data = request.get_json()

        if request_data and 'employee_id' in request_data:
            employee_id = request_data['employee_id']
            time_filter = request_data.get('time_filter')

            # Calculate start and end dates based on time_filter
            if time_filter == 'week':
                week_date = datetime.strptime(request_data.get('week'), '%Y-%m-%d')
                start_date = week_date - timedelta(days=week_date.weekday())
                end_date = start_date + timedelta(days=6)
            elif time_filter == 'month':
                month_year = datetime.strptime(request_data.get('month'), '%Y-%m')
                start_date = month_year.replace(day=1)
                end_date = month_year.replace(day=1, month=month_year.month % 12 + 1) - timedelta(days=1)
            else:
                start_date = datetime.min
                end_date = datetime.max

            # Fetch employee details from the user document
            employee = collection.find_one({'_id': ObjectId(employee_id)},
                                           {'name': 1, 'email': 1, 'phone': 1, 'gender': 1, 'dob': 1,
                                            'bio': 1, 'department': 1, 'job': 1, 'profile_pic': 1, 'employee_id': 1,
                                            '_id': 0})
            
            if not employee:
                employee = deleted_employees_collection.find_one({'_id': ObjectId(employee_id)},
                                           {'name': 1, 'email': 1, 'phone': 1, 'gender': 1, 'dob': 1,
                                            'bio': 1, 'department': 1, 'job': 1, 'profile_pic': 1, 'employee_id': 1,    
                                            '_id': 0})
                
            # Fetch time tracking details based on time frame
            employee_time_tracking = []
            user = collection.find_one({'_id': ObjectId(employee_id)})
            if user and 'time_tracking' in user:
                for entry in user['time_tracking']:
                    entry_date = datetime.strptime(entry.get('date'), '%Y-%m-%d')
                    # Filter only days where "start_time" is not empty
                    if start_date <= entry_date <= end_date:
                        response_values = [value for key, value in entry.items() if key.startswith("Response")]
                        entry = {key: value for key, value in entry.items() if not key.startswith("Response")}
                        entry['Response_values'] = response_values[1:]
                        entry['_id'] = str(entry.get('_id'))
                        employee_time_tracking.append(entry)

            # Sort employee_time_tracking by date in descending order
            employee_time_tracking.sort(key=lambda x: datetime.strptime(x.get('date'), '%Y-%m-%d'), reverse=True)

            # Apply additional filter for 'recent' (latest 3 entries with start_time != "")
            if time_filter == 'recent':
                employee_time_tracking = [entry for entry in employee_time_tracking][:3]

            if employee or employee_time_tracking:
                if employee:
                    employee['id'] = employee_id

            container = {
                'details': employee_time_tracking,
                'status': status_funct(employee_id, current_user["time_zone"]),
                'additional_details': employee
            }
            return jsonify(container)
        else:
            return jsonify(message="Invalid request or missing employee_id in the request!")
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@add_delete_emp_app.route('/api/response_details', methods=['POST'])
@token_required_admin
def response_details(current_user):
    request_data = request.get_json()

    if request_data and 'employee_id' in request_data:
        employee_id = request_data['employee_id']
        additional_details = find_user_info(employee_id)
        user = collection.find_one({"_id": ObjectId(employee_id)})
        if user:
            employee_details = user.get("time_tracking", [])
            modified_employee_details = []

            # Dictionary to store month-wise and date-wise hit and miss counts with response values
            response_totals_monthly = []
            response_totals_daily = []

            for entry in employee_details:
                date_str = entry.get('date', '')
                start_time = entry.get('start_time', '00:00:00')  # Get start_time from entry or default to '00:00:00'
                response_values = {key: value for key, value in entry.items() if key.startswith("Response")}
                miss_count = sum(1 for val in response_values.values() if isinstance(val, str) and "Missed" in val)

                # Aggregate month-wise and date-wise hit and miss counts
                if date_str:
                    month_year = datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m")
                    month_entry = next((item for item in response_totals_monthly if item["month"] == month_year), None)
                    if not month_entry:
                        month_entry = {"month": month_year, "hit_confirmation": 0, "miss_confirmation": 0}
                        response_totals_monthly.append(month_entry)

                    month_entry['hit_confirmation'] += max(0, len(response_values) - 1 - miss_count)
                    month_entry['miss_confirmation'] += miss_count

                    daily_entry = {
                        "date": date_str,
                        "start_time": start_time,  # Add start_time to daily entry
                        "hit_confirmation": max(0, len(response_values) - 1 - miss_count),
                        "miss_confirmation": miss_count,
                        "response_values": response_values
                    }
                    response_totals_daily.append(daily_entry)

                overall = {
                    "hit_confirmation": len(response_values),
                    "miss_confirmation": miss_count
                }
                entry['stats'] = overall

                modified_employee_details.append(entry)

            # Sort response_totals_monthly and response_totals_daily
            response_totals_monthly = sorted(response_totals_monthly, key=lambda x: x['month'], reverse=True)
            response_totals_daily = sorted(response_totals_daily, key=lambda x: x['date'], reverse=True)

            container = {
                'additional_details': additional_details,
                'response_totals_monthly': response_totals_monthly,
                'response_totals_daily': response_totals_daily
            }
            return jsonify(container)
        else:
            return jsonify(message="No details found for the specified employee!")
    else:
        return jsonify(message="Invalid request or missing employee_id in the request!")

@add_delete_emp_app.route('/api/response_details_by_date', methods=['POST'])
@token_required_admin
def response_details_by_date(current_user):
    request_data = request.get_json()

    if request_data and 'employee_id' in request_data and 'date' in request_data:
        employee_id = request_data['employee_id']
        date_str = request_data['date']
        additional_details = find_user_info(employee_id)
        user = collection.find_one({"_id": ObjectId(employee_id)})
        if user:
            employee_details = user.get("time_tracking", [])

            response_details = None

            for entry in employee_details:
                entry_date_str = entry.get('date', '')
                if entry_date_str == date_str:
                    response_details = entry
                    break

            if response_details:
                response_values = [value for key, value in response_details.items() if key.startswith("Response")]
                miss_count = sum(1 for val in response_values if isinstance(val, str) and "Missed" in val)

                overall = {
                    "hit_confirmation": max(0, len(response_values) - 1 - miss_count),
                    "miss_confirmation": miss_count
                }

                # Ensure start_time is set properly
                start_time = response_details.get('start_time', '00:00:00')
                if start_time == "":
                    start_time = "11:00:00"

                response_details['start_time'] = start_time
                response_details['response_values'] = response_values
                response_details['stats'] = overall

                # Remove the original response values from the dictionary
                for key in list(response_details.keys()):
                    if key.startswith("Response"):
                        del response_details[key]

                container = {
                    'additional_details': additional_details,
                    'response_details': response_details
                }
                return jsonify(container)
            else:
                return jsonify(message="No data found for the specified date for the employee!")
        else:
            return jsonify(message="No details found for the specified employee!")
    else:
        return jsonify(message="Invalid request or missing employee_id or date in the request!")

@add_delete_emp_app.route('/api/response_details_all', methods=['POST'])
@token_required_admin
def response_details_all(current_user):
    try:
        company_name = current_user['company']
        company_entity = company_collection.find_one({'company': company_name})
        emp_list = company_entity.get('empList', [])

        if not emp_list:
            return jsonify([])  # Return an empty list if no employees exist

        # Fetch all users in one query
        users = find_users_info(emp_list)

        last_entry_details_all = []

        for user in users:
            if not user:
                continue  # Skip if user doesn't exist

            user_id = str(user['_id'])  # Convert _id to string
            additional_details = {
                "name": user.get("name"),
                "profile_pic": user.get("profile_pic"),
                "job": user.get("job"),
                "_id": user_id
            }

            employee_details = user.get("time_tracking", [])

            if not employee_details:
                continue  # Skip if no time tracking data

            # Find the last entry date
            last_entry = max(employee_details, key=lambda x: x.get('date', ''), default=None)

            if last_entry:
                response_values = [value for key, value in last_entry.items() if key.startswith("Response")]
                miss_count = sum(1 for val in response_values if isinstance(val, str) and "Missed" in val)

                overall = {
                    "hit_confirmation": max(0, len(response_values) - 1 - miss_count),
                    "miss_confirmation": miss_count
                }

                response_entry = {
                    "date": last_entry.get('date', ''),
                    "start_time": last_entry.get('start_time', '11:00:00'),
                    "additional_details": additional_details,
                    "stats": overall,
                    "response_values": response_values
                }

                last_entry_details_all.append(response_entry)

        return jsonify(last_entry_details_all)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def validate_input(name, password, email):
    if not name : return False, "Invalid name"

    if not password or len(password) < 6: return False, "Invalid password"

    if not email or "@" not in email: return False, "Invalid email"

    # Check if the name exists in the collection
    existing_user = collection.find_one({'name': name})
    if existing_user:
        return False, "Name already exists in the collection, Try Another Name"

    return True, None


@add_delete_emp_app.route("/api/delete_employee", methods=["POST"])
@token_required_admin
def delete_employee(current_user):
    try:
        time_zone = current_user.get('time_zone')
        if request.method == "POST":
            employee_id = request.form.get("employee_id")

            # Perform deletion operation from the database
            if employee_id:
                # Fetch the employee's data before deletion
                employee_data = collection.find_one({"_id": ObjectId(employee_id)})

                if employee_data:
                    # Get the current date and time in Asia/Kolkata timezone
                    kolkata_tz = pytz.timezone(time_zone)
                    deletion_date = datetime.now(kolkata_tz)

                    # Add the date of deletion to the employee's data
                    employee_data['deleted_at'] = deletion_date

                    # Add the employee's data to the "deleted_employees" collection
                    deleted_employees_collection.insert_one(employee_data)

                    # Remove the employee ID from the "empList" in the "company" collection
                    company_data = company_collection.find_one({"company": current_user["company"]})
                    if company_data:
                        emp_list = company_data.get("empList", [])
                        if employee_id in emp_list:
                            emp_list.remove(employee_id)
                            company_collection.update_one(
                                {"company": current_user["company"]},
                                {"$set": {"empList": emp_list}}
                            )

                    # Delete the employee from the original collection
                    collection.delete_one({"_id": ObjectId(employee_id)})

                    return jsonify({'message': f"Employee '{employee_id}' deleted successfully, data added to 'deleted_employees' collection with deletion date, and removed from 'empList' in 'company' collection"})
                else:
                    return jsonify({"message": "Failed. Employee not found"})
            else:
                return jsonify({"message": "Failed. Please provide a valid employee_id"})
    except Exception as e:
        return jsonify({'message': f"An error occurred: {str(e)}"}), 500


@add_delete_emp_app.route("/api/reactivate_employee", methods=["POST"])
@token_required_admin
def reactivate_employee(current_user):
    try:
        if request.method == "POST":
            employee_id = request.json.get("employee_id")

            if employee_id:
                # Fetch the employee's data from the deleted_employees collection
                employee_data = deleted_employees_collection.find_one({"_id": ObjectId(employee_id)})

                if employee_data:
                    # Remove 'deleted_at' field
                    employee_data.pop('deleted_at', None)
                    
                    # Insert employee back into the main collection
                    collection.insert_one(employee_data)
                    
                    # Remove employee from deleted_employees collection
                    deleted_employees_collection.delete_one({"_id": ObjectId(employee_id)})
                    
                    # Add the employee ID back to the "empList" in the "company" collection
                    company_data = company_collection.find_one({"company": current_user["company"]})
                    if company_data:
                        emp_list = company_data.get("empList", [])
                        if employee_id not in emp_list:
                            emp_list.append(employee_id)
                            company_collection.update_one(
                                {"company": current_user["company"]},
                                {"$set": {"empList": emp_list}}
                            )
                    
                    return jsonify({"message": f"Employee '{employee_id}' reactivated successfully and restored in 'empList' of company collection", "status": True})
                else:
                    return jsonify({"message": "Failed. Employee not found in deleted records", "status": False})
            else:
                return jsonify({"message": "Failed. Please provide a valid employee_id", "error": "Missing employee_id", "status": False})
    except Exception as e:
        return jsonify({"message": f"An error occurred: {str(e)}", "status": False}), 500
    

@add_delete_emp_app.route('/api/add_employee', methods=['POST']) 
@token_required_admin
def add_employee(current_user):
    try:
        name = request.form.get("name")
        password = request.form.get("password")
        email = request.form.get("email")
        phone = request.form.get("phone")
        gender = request.form.get("gender")
        dob = request.form.get("dob")
        job = request.form.get("job")
        joining = request.form.get("joining")
        bio = request.form.get("bio")
        department = request.form.get("department")
        address = request.form.get("address")
        userType = request.form.get("userType")

        # Optional fields
        nationality = request.form.get("nationality")
        marital_status = request.form.get("marital_status")
        city = request.form.get("city")
        state = request.form.get("state")
        zip_code = request.form.get("zip_code")
        username = request.form.get("username")
        linkedinID = request.form.get("linkedinID")
        slackID = request.form.get("slackID")
        skypeID = request.form.get("skypeID")
        githubID = request.form.get("githubID")

        # Check if email already exists
        if collection.find_one({'email': email}):
            return jsonify({"error": "User already exists with this email"}), 400

        # Department validation
        company_data = company_collection.find_one({"company": current_user["company"]})
        if department and (not company_data or department not in company_data.get("departments", [])):
            return jsonify({"error": "Invalid department"}), 400

        # Hourly employee check
        hourly_data = {}
        if userType == 'hourly':
            hourly_time = request.form.get('hourlyTime')
            noti_before = request.form.get('notiBefore')
            extend_time_option = request.form.get('extendTimeOption')

            if not all([hourly_time, noti_before, extend_time_option]):
                return jsonify({"error": "hourlyTime, notiBefore, and extendTimeOption are required for hourly employees"}), 400

            extend_time_option_list = extend_time_option.strip('[]').replace("'", "").split(', ')
            hourly_data = {
                "hourlyTime": hourly_time,
                "notiBefore": noti_before,
                "extendTimeOption": extend_time_option_list
            }

        # Profile pic upload
        file_url = "https://th.bing.com/th/id/OIP.EYsBbvQxJK_0DhnzMap0ZAHaHa?rs=1&pid=ImgDetMain"
        if 'profile_pic' in request.files:
            profile_pic_file = request.files['profile_pic']
            file_url = upload_to_firebase(profile_pic_file, 'Employee_Profile_Pic', email)

        valid, message = validate_input(name, password, email)
        if not valid:
            return jsonify({"error": message}), 400

        if len(company_data.get("empList", [])) >= int(company_data.get("maxEmp", 0)):
            return jsonify({"error": "Employee limit reached in the company"}), 400

        regex_code = company_data.get('regex_code')
        if not regex_code:
            return jsonify({"error": "First create Regex Code"}), 400

        employee_id = str(increment_employee_ids(current_user["company"], regex_code))
        new_employee_oid = ObjectId()

        # Firebase uploads for documents
        doc_files = {}
        doc_fields = ["appointment_letter", "experience_letter", "releasing_letter", "salary_slips"]
        for doc_field in doc_fields:
            if doc_field in request.files:
                doc_file = request.files[doc_field]
                doc_files[doc_field] = upload_to_firebase(doc_file, 'Employee_Documents', f"{email}_{doc_field}")

        # Build new employee data
        new_employee_data = {
            "_id": new_employee_oid,
            "employee_id": employee_id,
            "name": name,
            "password": generate_password_hash(password),
            "email": email,
            "phone": phone,
            "gender": gender,
            "dob": dob,
            "job": job,
            "bio": bio,
            "department": department,
            "address": address,
            "joining": joining,
            "company": current_user["company"],
            "userType": userType if userType else "normal",
            "hourlyEmp": hourly_data if hourly_data else None,
            "profile_pic": file_url,
            "nationality": nationality,
            "marital_status": marital_status,
            "city": city,
            "state": state,
            "zip_code": zip_code,
            "username": username,
            "linkedinID": linkedinID,
            "slackID": slackID,
            "skypeID": skypeID,
            "githubID": githubID
        }

        # Add uploaded doc URLs if available
        new_employee_data.update(doc_files)

     # Push employee ID to company.empList
        company_collection.update_one(
            {"company": current_user["company"]},
            {"$push": {"empList": str(new_employee_oid)}}
        )

        # # Insert new employee
        collection.insert_one(new_employee_data)
        html_message = f'''
 <html lang="en">
 <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Toggle Timer Account Activation</title>
 <style>
 body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu,Cantarell, sans-serif;
    line-height: 1.6;
    color: #333;
    background-color: #f4f4f4;
    margin: 0;
    padding: 0;
 }}
 .email-container {{
    max-width: 600px;
    margin: 20px auto;
    background-color: #ffffff;
    border-radius: 8px;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
    overflow: hidden;
 }}
 .header {{
    color: white;
    padding: 40px 30px;
    text-align: center;
    background: linear-gradient(90deg, #00ff8e 0%, #00c9ff 100%);
 }}
 .header h1 {{
    margin: 0;
    font-size: 28px;
    font-weight: 600;
 }}
 .header p {{
    margin: 10px 0 0 0;
    font-size: 16px;
    opacity: 0.9;
 }}
 .content {{
    padding: 40px 30px 0;
    text-align: left;
 }}
 .greeting {{
    font-size: 20px;
    color: #2c3e50;
    margin-bottom: 20px;
    font-weight: 600;
 }}
 .message {{
    font-size: 16px;
    color: #555;
    margin-bottom: 25px;
    line-height: 1.7;
 }}
 .credentials-container {{
    background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
    border: 2px solid #00c9ff;
    border-radius: 12px;
    padding: 30px;
    margin: 30px 0;
    position: relative;
    overflow: hidden;
 }}
 .credentials-container::before {{
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 4px;
    background: linear-gradient(90deg, #00ff8e 0%, #00c9ff 100%);
 }}
 .credentials-icon {{
    font-size: 32px;
    margin-bottom: 15px;
}}
 .credentials-title {{
    font-size: 20px;
    font-weight: 600;
    color: #00c9ff;
    margin-bottom: 20px;
 }}
 .credential-item {{
    display: flex;
    align-items: center;
    margin: 15px 0;
    background: rgba(255, 255, 255, 0.7);
    padding: 12px 15px;
    border-radius: 6px;
    border: 1px solid rgba(0, 201, 255, 0.2);
 }}
 .credential-label {{
    font-weight: 600;
    color: #2c3e50;
    width: 100px;
    font-size: 14px;
 }}
 .credential-value {{
    font-family: 'Courier New', monospace;
    color: #00c9ff;
    font-weight: 600;
    font-size: 14px;
 }}
 .cta-button {{
    display: inline-block;
    background: linear-gradient(90deg, #00ff8e 0%, #00c9ff 100%);
    color: white;
    padding: 15px 30px;
    text-decoration: none;
    border-radius: 25px;
    font-weight: 600;
    font-size: 16px;
    margin: 25px 0;
    transition: all 0.3s ease;
    box-shadow: 0 4px 15px rgba(0, 255, 142, 0.3);
    width: 120px;
    text-align: center;
 }}
.cta-button:hover {{
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(0, 255, 142, 0.4);
 }}
 .demo-section {{
    background: linear-gradient(135deg, #e8f5e8 0%, #f0f9ff 100%);
    border-radius: 12px;
    padding: 25px;
    margin: 25px 0;
    border: 1px solid #00ff8e;
 }}
 .demo-text {{
    font-size: 16px;
    color: #2c3e50;
    margin-bottom: 15px;
 }}
 .contact-info {{
    background-color: #f8f9fa;
    border-radius: 8px;
    padding: 20px;
    margin: 25px 0;
    border-left: 4px solid #00ff8e;
 }}
 .contact-item {{
    display: flex;
    align-items: center;
    margin: 10px 0;
 }}
 .contact-icon {{
    width: 24px;
    height: 24px;
    background: linear-gradient(90deg, #00ff8e 0%, #00c9ff 100%);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-right: 15px;
    color: white;
    font-weight: 600;
    font-size: 12px;
 }}
 .contact-text {{
    color: #555;
    font-size: 14px;
 }}
 .contact-link {{
    color: #00c9ff;
    text-decoration: none;
 }}
 .contact-link:hover {{
    text-decoration: underline;
 }}
 .footer {{
    background-color: #343a40;
    color: #adb5bd;
    padding: 25px 30px;
    text-align: center;
 }}
 .footer p {{
    margin: 5px 0;
    font-size: 14px;
 }}
 .company-name {{
    font-weight: 600;
    color: #fff;
 }}
 @media (max-width: 600px) {{
    .email-container {{
    margin: 10px;
    border-radius: 0;
    }}
    .content {{
    padding: 20px;
    }}
    .header {{
    padding: 30px 20px;
    }}
    .header h1 {{
    font-size: 24px;
    }}
    .credentials-container {{
    padding: 20px;
    }}
    .credentials-icon {{
    font-size: 28px;
    }}
    .credentials-title {{
    font-size: 18px;
    }}
    .credential-item {{
    flex-direction: column;
    align-items: flex-start;
    }}
    .credential-label {{
    width: auto;
    margin-bottom: 5px;
    }}
 }}
 </style>
 </head>
 <body>
 <div class="email-container">
 <div class="header">
 <h1>⏱ Toggle Timer Account Activated</h1>
 <p>Your time-tracking journey begins now</p>
 </div>
 <div class="content">
 <div class="greeting">
 Dear {name},
 </div>
 <div class="message">
 We're excited to announce that your Toggle Timer account is now active, starting from {datetime.now().strftime('%Y-%m-%d')}.
 </div>
 <div class="message">
 This powerful time-tracking and collaboration tool will help us manage tasks, track progress, and streamline daily updates across the team.
</div>
 <div class="credentials-container">
 <div class="credentials-icon">🔐</div>
 <div class="credentials-title">Your Login Credentials</div>
 <div class="credential-item">
 <span class="credential-label">Username:</span>
 <span class="credential-value">{email}</span>
 </div>
 <div class="credential-item">
 <span class="credential-label">Password:</span>
 <span class="credential-value">{password}</span>
 </div>
 </div>
 <div style="text-align: center;">
 <a href="https://firebasestorage.googleapis.com/v0/b/toggletimerr.firebasestorage.app/o/executables%2Flatest_release.exe?alt=media" class="cta-button" style="margin-right: 10px;">
 WINDOWS
 </a>
 <a href="https://firebasestorage.googleapis.com/v0/b/toggletimerr.firebasestorage.app/o/executables%2Flatest_release_mac.app?alt=media" class="cta-button" style="margin-left: 10px;">
 MAC
 </a>
 </div>
 <div class="demo-section">
 <div class="demo-text">
 Please let us know a convenient time to schedule a demo session for better understanding and smoother onboarding.
 </div>
 </div>
 <div class="contact-info">
<div class="contact-item">
 <div class="contact-icon">📧</div>
 <div class="contact-text">
 <strong>Email:</strong> <a href="mailto:team@toggletimer.com" class="contactlink">team@toggletimer.com</a>
 </div>
 </div>
 <div class="contact-item">
 <div class="contact-icon">🌐</div>
 <div class="contact-text">
 <strong>Help Center:</strong> <a href="https://www.toggletimer.com/" class="contact-link">https://www.toggletimer.com/</a>
 </div>
 </div>
 </div>
 <div class="message">
 Regards,<br>
 <strong>Toggletime.com</strong>
 </div>
 </div>
 <div class="footer">
 <p class="company-name">Toggle Timer</p>
 <p>Crafted by Hansraj Ventures Pvt. Ltd</p>
 <p>© 2025 All rights reserved</p>
 </div>
 </div>
 </body>
 </html>
'''
        send_admin_details(html_message, email, company_data.get('email'), " Toggle Timer Account Activated")
        return jsonify({
            "message": f"{name}! Signed Up, Successfully",
            "employee_id": str(new_employee_oid)
        }), 200

    except Exception as e:
        return jsonify({"error": f"Something went wrong: {e}"}), 500

def increment_employee_ids(company_id, regex_code):
    # Find all employees of the given company
    employees_cursor = collection.find({'company': company_id}, {'_id': 0, 'employee_id': 1})

    # Convert the cursor to a list
    employees_list = list(employees_cursor)

    if not employees_list:
        new_number = 1
    else:
        # Extract numeric part and find the highest
        employee_numbers = [
            int(re.search(r'\d+', emp['employee_id']).group()) 
            for emp in employees_list if re.search(r'\d+', emp['employee_id'])
        ]
        new_number = max(employee_numbers) + 1

    # Format: PREFIX + 3-digit padded number
    new_employee_id = f"{regex_code}{new_number:03d}"
    return new_employee_id


def status_funct(_id, time_zone):
    # Define the Asia/Kolkata timezone
    tz = pytz.timezone(time_zone)
    
    # Get today's date in Asia/Kolkata timezone
    today = datetime.now(tz).strftime("%Y-%m-%d")
    user = collection.find_one(
        {"_id": ObjectId(_id)}, 
        {"time_tracking": {"$slice": -3}}  # Fetch all fields, but only last 3 entries of time_tracking
    )

    if user:
        for entry in user.get("time_tracking", []):
            if entry.get("date") == today:
                start_time = entry.get("start_time", "00:00:00")
                end_time = entry.get("end_time")
                if start_time != '00:00:00' and not end_time:
                    return "Active"
                elif end_time:
                    return "JobLogout"
                else:
                    return "Inactive"
    return "Inactive"

@add_delete_emp_app.route('/api/employees_list', methods=['GET'])
@token_required_admin_or_superadmin
def get_employees(current_user):
    
    all_user = request.args.get('all_user')
    active = request.args.get('active')
    inactive = request.args.get('inactive')
    joblogout = request.args.get('joblogout')
    include_deleted = request.args.get('deleted') == 'true'
    if current_user["user_type"] == "super_admin": company = request.args.get('company')
    else: company = current_user["company"]

    employees = list(collection.find(
        {"company": company},
        {
            'name': 1, 'email': 1, 'joining': 1, 'department': 1, 'phone': 1, 'bio': 1,
            'job': 1, 'gender': 1, 'dob': 1, 'employee_id': 1, '_id': 1, 'access': 1, 'userType': 1,
            'hourlyEmp': 1, 'profile_pic': 1, 'address': 1, 'version': 1, 'company': 1,
            'time_tracking': {'$slice': -1}  # Fetch only the latest time_tracking entry
        }
    ).sort('joining', -1))
    formatted_employees = []
    for employee in employees:
        status = status_funct(str(employee.get('_id')), current_user["time_zone"])
        if (all_user and status) or (active and status == 'Active') or (inactive and status == 'Inactive') or (joblogout and status == 'JobLogout'):
            formatted_employee = {
                'name': employee.get('name', ''),
                'email': employee.get('email', ''),
                'joining': employee.get('joining', ''),
                'department': employee.get('department', ''),
                'mobile': employee.get('phone', ''),
                'bio': employee.get('bio', ''),
                'job': employee.get('job', ''),
                'gender': employee.get('gender', ''),
                'dob': employee.get('dob', ''),
                'status': status,
                'company': employee.get('company', ''),
                'employee_id':employee.get('employee_id'),
                '_id': str(employee.get('_id')),
                'profession': employee.get('job', ''),
                'profile_pic': employee.get('profile_pic',"https://th.bing.com/th/id/OIP.EYsBbvQxJK_0DhnzMap0ZAHaHa?rs=1&pid=ImgDetMain"),
                'address': employee.get('address', ''),
                'access': employee.get('access', {}),
                'userType': employee.get('userType', 'normal'),
                'hourlyEmp': employee.get('hourlyEmp', {}),
                'version': employee.get('version', '')
            }
            formatted_employees.append(formatted_employee)

    # Optionally include deleted employees
    if include_deleted:
        deleted_employees = list(deleted_employees_collection.find(
            {"company": company},
            {
                'name': 1, 'email': 1, 'joining': 1, 'department': 1, 'phone': 1, 'bio': 1,
                'job': 1, 'gender': 1, 'dob': 1, 'employee_id': 1, '_id': 1, 'access': 1, 'userType': 1,
                'hourlyEmp': 1, 'profile_pic': 1, 'address': 1, 'version': 1, 'company': 1,
            }
        ))

        for employee in deleted_employees:
            formatted_employees.append({
                'name': employee.get('name', ''),
                'email': employee.get('email', ''),
                'joining': employee.get('joining', ''),
                'department': employee.get('department', ''),
                'mobile': employee.get('phone', ''),
                'bio': employee.get('bio', ''),
                'job': employee.get('job', ''),
                'gender': employee.get('gender', ''),
                'dob': employee.get('dob', ''),
                'status': 'deleted',
                'company': employee.get('company', ''),
                'employee_id': employee.get('employee_id'),
                '_id': str(employee.get('_id')),
                'profession': employee.get('job', ''),
                'profile_pic': employee.get('profile_pic', "https://th.bing.com/th/id/OIP.EYsBbvQxJK_0DhnzMap0ZAHaHa?rs=1&pid=ImgDetMain"),
                'address': employee.get('address', ''),
                'access': employee.get('access', {}),
                'userType': employee.get('userType', 'normal'),
                'hourlyEmp': employee.get('hourlyEmp', {}),
                'version': employee.get('version', '')
            })
    return jsonify(formatted_employees)

@add_delete_emp_app.route('/api/update_employee_data', methods=['POST'])
@token_required_admin
def update_employee(current_user):
    try:
        data = request.form
        employee_id = data.get('_id')
        
        if not employee_id:
            return jsonify({"error": "Employee ID is required"}), 400

        update_data = {}

        # Standard fields
        for field in ['name', 'email', 'phone', 'gender', 'dob', 'job', 'bio', 'joining', 'address', 'note',
                      'nationality', 'marital_status', 'city', 'state', 'zip_code', 'username', 'linkedinID',
                      'slackID', 'skypeID', 'githubID']:
            if field in data:
                update_data[field] = data.get(field)

        if 'password' in data:
            update_data['password'] = generate_password_hash(data.get('password'))

        # Validate department if provided
        if 'department' in data:
            department = data.get('department')
            company_data = company_collection.find_one({"company": current_user["company"]})
            if company_data and department not in company_data.get("departments", []):
                return jsonify({"error": f"Department '{department}' does not exist in company"}), 400
            update_data['department'] = department

        # Profile picture update
        if 'profile_pic' in request.files:
            update_data['profile_pic'] = upload_to_firebase(request.files.get('profile_pic'), 'Employee_Profile_Pic', employee_id)

        # Handle file uploads for documents
        file_fields = {
            "appointment_letter": "Appointment_Letters",
            "experience_letter": "Experience_Letters",
            "releasing_letter": "Releasing_Letters",
            "salary_slips": "Salary_Slips"
        }

        for field, folder in file_fields.items():
            if field in request.files:
                file_url = upload_to_firebase(request.files[field], folder, employee_id)
                update_data[field] = file_url

        # Handle userType field and related fields
        if 'userType' in data:
            user_type = data.get('userType')
            update_data['userType'] = user_type

            if user_type == 'hourly':
                hourly_time = data.get('hourlyTime')
                noti_before = data.get('notiBefore')
                extend_time_option = data.get('extendTimeOption')

                if not hourly_time or not noti_before or not extend_time_option:
                    return jsonify({"error": "hourlyTime, notiBefore, and extendTimeOption are required for hourly employees"}), 400

                extend_time_option_list = extend_time_option.strip('[]').replace("'", "").split(', ')
                update_data['hourlyEmp'] = {
                    "hourlyTime": hourly_time,
                    "notiBefore": noti_before,
                    "extendTimeOption": extend_time_option_list
                }

        # Update MongoDB record
        collection.update_one(
            {"_id": ObjectId(employee_id)},
            {"$set": update_data}
        )

        return jsonify({"message": "Employee details updated successfully", "status": "success"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@add_delete_emp_app.route("/api/permanent_delete_employee", methods=["DELETE"])
@token_required_admin
def permanent_delete_employee(current_user):
    try:
        employee_id = request.form.get("_id")

        if not employee_id:
            return jsonify({"error": "Employee ID is required"}), 400
        
        # Check if the given employee_id is a valid ObjectId
        query = {}
        if ObjectId.is_valid(employee_id):
            query = {"_id": ObjectId(employee_id)}

        # Check if employee exists
        employee = deleted_employees_collection.find_one(query, {"_id": 0})
        if not employee:
            return jsonify({"message": "Employee not found"}), 404

        # Perform deletion
        result = deleted_employees_collection.delete_one(query)
        if result.deleted_count == 1:
            return jsonify({"message": "Employee record deleted successfully", "status": "success", "data": employee}), 200
        else:
            return jsonify({"message": "Failed to delete employee"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@add_delete_emp_app.route('/api/deleted_employees', methods=['GET'])
@token_required_admin
def get_deleted_employees(current_user):
    try:
        # Get the company code from the request arguments
        company_code = current_user['company']
        
        if not company_code:
            return jsonify({'message': 'Company code is required'}), 400
        
        # Fetch deleted employees for the given company code
        deleted_employees = list(deleted_employees_collection.find({'company': company_code}).sort('deleted_at',-1))
        
        # Format the employee data
        formatted_employees = []
        for employee in deleted_employees:
            formatted_employee = {
                'name': employee.get('name', ''),
                'email': employee.get('email', ''),
                'joining': employee.get('joining', ''),
                'department': employee.get('department', ''),
                'mobile': employee.get('phone', ''),
                'bio': employee.get('bio', ''),
                'job': employee.get('job', ''),
                'gender': employee.get('gender', ''),
                'dob': employee.get('dob', ''),
                'status': 'Deleted',
                'employee_id': employee.get('employee_id'),
                '_id': str(employee.get('_id')),
                'profession': employee.get('job', ''),
                'profile_pic': employee.get('profile_pic', "https://th.bing.com/th/id/OIP.EYsBbvQxJK_0DhnzMap0ZAHaHa?rs=1&pid=ImgDetMain"),
                'address': employee.get('address', ''),
                'deleted_at': employee.get('deleted_at', '')
            }
            formatted_employees.append(formatted_employee)

        return jsonify({'data': formatted_employees, 'message': 'Deleted employees retrieved successfully', 'status': True}), 200

    except Exception as e:
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500
    
@add_delete_emp_app.route('/api/get_company_departments_employees', methods=['GET'])
@token_required_admin
def get_company_departments_employees(current_user):
    try:
        company_name = current_user.get('company')
        if not company_name:
            return jsonify({"error": "Company not associated with user"}), 400

        # Fetch company document
        company = company_collection.find_one({"company": company_name})
        if not company:
            return jsonify({"error": "Company not found"}), 404

        departments = company.get('departments', [])
        response_data = []

        for dept in departments:
            # Get employees in the department
            employees = collection.find(
                {"company": company_name, "department": dept},
                {"_id": 1, "name": 1, "profile_pic": 1, "employee_id": 1}
            )

            emp_list = [
                {
                    "_id": str(emp["_id"]),
                    "name": emp.get("name"),
                    "profile_pic": emp.get("profile_pic"),
                    "employee_id": emp.get("employee_id")
                }
                for emp in employees
            ]

            response_data.append({
                "department": dept,
                "employees": emp_list
            })

        return jsonify({"data": response_data, "status": "success"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
