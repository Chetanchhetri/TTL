import json, pymongo, pytz
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from socketio_setup import socketio
from bson import ObjectId
from smtplib import SMTP
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from decorators import token_required, db, company_collection, notification_collection, collection, upload_to_firebase, token_required_admin, find_user_info

email_send_app = Blueprint('email_send_app',__name__)

collection4 = db['emails']

def calculate_weekly_data(employee_id, start_of_week_str):
    user = collection.find_one({'_id': ObjectId(employee_id)})
    to_email = user['email']
    time_tracking = user.get('time_tracking', [])

    # Define the start and end date of the week based on the given start_of_week_str
    start_of_week = datetime.strptime(start_of_week_str, '%Y-%m-%d')
    end_of_week = start_of_week + timedelta(days=6)

    # Calculate total elapsed time for each day (excluding Sunday) and total time for the week
    total_elapsed_time_by_day = {day: timedelta() for day in range(6)}
    total_elapsed_time_week = timedelta()
    on_leave_count = 0

    # Process time tracking data for the specified week
    for entry in time_tracking:
        entry_date = datetime.strptime(entry['date'], '%Y-%m-%d')

        # Filter data for the specified week
        if start_of_week <= entry_date <= end_of_week:
            day_of_week = entry_date.weekday()

            # Exclude Sunday
            if day_of_week != 6:
                elapsed_time_str = entry.get('elapsed_time', '0:00:00')
                # Convert elapsed time string to timedelta
                elapsed_time = datetime.strptime(elapsed_time_str, '%H:%M:%S').time()
                elapsed_time_timedelta = timedelta(hours=elapsed_time.hour, minutes=elapsed_time.minute, seconds=elapsed_time.second)

                # Add elapsed time to the corresponding day
                total_elapsed_time_by_day[day_of_week] += elapsed_time_timedelta
                total_elapsed_time_week += elapsed_time_timedelta

    # Check if data is not present for a day and mark as "On Leave"
    for day, total_elapsed_time in total_elapsed_time_by_day.items():
        if total_elapsed_time == timedelta():
            total_elapsed_time_by_day[day] = "On Leave"
            on_leave_count += 1

    # Map day index to abbreviated day name (Mon, Tue, Wed, Thu, Fri, Sat)
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    total_elapsed_time_by_day = {day_names[day]: str(value) for day, value in total_elapsed_time_by_day.items()}

    return {
        "data": total_elapsed_time_by_day,
        "total_time_week": str(total_elapsed_time_week),
        "on_leave_count": on_leave_count,
        "to_email": to_email
    }



@email_send_app.route('/api/employee/<employee_id>/send_weekly_email', methods=['POST'])
@token_required_admin
def send_weekly_email_endpoint(current_user,employee_id):
    result = collection.find_one({"_id": ObjectId(employee_id)})
    email_cred = company_collection.find_one({"company": current_user["company"]},{"email_cred": 1, "name":1})
    if not result:
        return jsonify({"error": "Employee not found"}), 404
    
    name = result.get("name")
    
    # Retrieve file from the request and upload to Firebase (if present)
    file = request.files.get('file')
    file_url = None
    if file:
        file_url = upload_to_firebase(file,'Weekly_Emails' ,employee_id)
    
    # Retrieve stats from the form data
    stats = request.form.get('stats', '{}')
    stats_dict = json.loads(stats)  # Parse the JSON string into a dictionary

    # Extract feedback parameters from the stats dictionary if they exist
    growth = stats_dict.get('growth')
    work_updates = stats_dict.get('work_updates')
    work_performance = stats_dict.get('work_performance')
    attendence = stats_dict.get('attendence')
    responses = stats_dict.get('responses')
    work_ethics = stats_dict.get('work_ethics')
    behaviour = stats_dict.get('behaviour')
    communication = stats_dict.get('communication')
    discipline = stats_dict.get('discipline')
    sheet_manage = stats_dict.get('sheet_manage')
    work_potential = stats_dict.get('work_potential')
    work_skills = stats_dict.get('work_skills')

    # Retrieve signature and other request form data
    signature = request.form.get('signature')
    start_date = request.form.get('start_date')
    cc_email1 = request.form.get("cc_email1", 'hitman.harsh212gmail.com')
    cc_email2 = request.form.get("cc_email2")
    cc_email3 = request.form.get("cc_email3")
    
    description = request.form.get('description', f'I hope this email finds you well. As we approach the end of another week, I wanted to take a moment to acknowledge and review your work at {email_cred["name"]}. Here are some specific highlights from your performance in this week:')

    mon = request.form.get('mon', '')
    tue = request.form.get('tue', '')
    wed = request.form.get('wed', '')
    thu = request.form.get('thu', '')
    fri = request.form.get('fri', '')
    sat = request.form.get('sat', '')
    
    # Calculate weekly data using calculate_weekly_data
    weekly_data = calculate_weekly_data(employee_id, start_date)
    total_elapsed_time_week = weekly_data["total_time_week"]
    total_elapsed_time_by_day = weekly_data["data"]
    on_leave_count = weekly_data["on_leave_count"]
    to_email = weekly_data["to_email"]

    # Prepare the email content
    sender_email = email_cred['email_cred']['email']
    app_password = email_cred['email_cred']['password']

    if email_cred is None:
        return jsonify({"error": "Email credentials not found. Please set them first"}), 404 
        
    server = SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(sender_email, app_password)

    # Define the email message content
    message = f"""
    <html>
    <head>
        <style>
            body {{
                font-family: 'Arial', sans-serif;
            }}
            p {{
                margin-bottom: 10px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 20px;
            }}
            table, th, td {{
                border: 1px solid #ddd;
            }}
            th, td {{
                padding: 12px;
                text-align: left;
            }}
            th {{
                background-color: #f2f2f2;
            }}
        </style>
    </head>
    <body>
        <p style="font-size: 18px;">Dear {name},</p>
        <p style="font-size: 14px;">{description}</p>
        <p style="font-size: 14px;">Hours of working in a week: Your total working hours were {total_elapsed_time_week} (According to the time tracking tool)</p>
        <table>
            <tr>
                <th>Day</th>
                <th>Total Hours</th>
                <th>Work Details</th>
            </tr>
            <tr>
                <td>Monday</td>
                <td>{total_elapsed_time_by_day['Monday']}</td>
                <td>{mon}</td>
            </tr>
            <tr>
                <td>Tuesday</td>
                <td>{total_elapsed_time_by_day['Tuesday']}</td>
                <td>{tue}</td>
            </tr>
            <tr>
                <td>Wednesday</td>
                <td>{total_elapsed_time_by_day['Wednesday']}</td>
                <td>{wed}</td>
            </tr>
            <tr>
                <td>Thursday</td>
                <td>{total_elapsed_time_by_day['Thursday']}</td>
                <td>{thu}</td>
            </tr>
            <tr>
                <td>Friday</td>
                <td>{total_elapsed_time_by_day['Friday']}</td>
                <td>{fri}</td>
            </tr>
            <tr>
                <td>Saturday</td>
                <td>{total_elapsed_time_by_day['Saturday']}</td>
                <td>{sat}</td>
            </tr>
        </table>

        <p style="font-size: 14px;">Attachment (if any): {file_url}</p>

        <p style="font-size: 14px;">Attendance and leave status: {6 - on_leave_count} Days completed, {on_leave_count} Leave(s), 0 Half day(s)</p>

        <p style="font-size: 14px;">Feedback</p>
        <table>
            {f'<tr><td>Communication</td><td>{communication}</td></tr>' if communication else ''}
            {f'<tr><td>Discipline</td><td>{discipline}</td></tr>' if discipline else ''}
            {f'<tr><td>Behaviour</td><td>{behaviour}</td></tr>' if behaviour else ''}
            {f'<tr><td>Work Ethics</td><td>{work_ethics}</td></tr>' if work_ethics else ''}
            {f'<tr><td>Response</td><td>{responses}</td></tr>' if responses else ''}
            {f'<tr><td>Attandance</td><td>{attendence}</td></tr>' if attendence else ''}
            {f'<tr><td>Work Updates</td><td>{work_updates}</td></tr>' if work_updates else ''}
            {f'<tr><td>Work Performance</td><td>{work_performance}</td></tr>' if work_performance else ''}
            {f'<tr><td>Work Potential</td><td>{work_potential}</td></tr>' if work_potential else ''}
            {f'<tr><td>Work Skills</td><td>{work_skills}</td></tr>' if work_skills else ''}
            {f'<tr><td>Sheet Manage</td><td>{sheet_manage}</td></tr>' if sheet_manage else ''}
            {f'<tr><td>Growth</td><td>{growth}</td></tr>' if growth else ''}
        </table>

        <p style="font-size: 14px;">I hope the above feedback & work report will help you to grow personally and professionally.</p>

        <p style="font-size: 14px;">Best Regards,<br/>
        {signature}<br/>
        {email_cred["name"]}</p>
    </body>
    </html>
    """

    # Define the db message content
    db_message = f"""
    Dear {name},

    {description}

    Hours of working in a week: Your total working hours were {total_elapsed_time_week} (According to the time tracking tool)

    Day-wise Work Details:
    Monday: {total_elapsed_time_by_day['Monday']} hours, {mon}
    Tuesday: {total_elapsed_time_by_day['Tuesday']} hours, {tue}
    Wednesday: {total_elapsed_time_by_day['Wednesday']} hours, {wed}
    Thursday: {total_elapsed_time_by_day['Thursday']} hours, {thu}
    Friday: {total_elapsed_time_by_day['Friday']} hours, {fri}
    Saturday: {total_elapsed_time_by_day['Saturday']} hours, {sat}

    Attachment (if any): {file_url}

    Attendance and leave status: {6 - on_leave_count} Days completed, {on_leave_count} Leave(s), 0 Half day(s)

    Feedback:
    {'Communication: ' + communication if communication else ''}
    {'Discipline: ' + discipline if discipline else ''}
    {'Behaviour: ' + behaviour if behaviour else ''}
    {'Work Ethics: ' + work_ethics if work_ethics else ''}
    {'Response: ' + responses if responses else ''}
    {'Attendance: ' + attendence if attendence else ''}
    {'Work Performance: ' + work_performance if work_performance else ''}
    {'Work Updates: ' + work_updates if work_updates else ''}
    {'Work Potential: ' + work_potential if work_potential else ''}
    {'Work Skills: ' + work_skills if work_skills else ''}
    {'Sheet Manage: ' + sheet_manage if sheet_manage else ''}
    {'Growth: ' + growth if growth else ''}

    I hope the above feedback & work report will help you to grow personally and professionally.

    Best Regards,
    {signature}
    {email_cred["name"]}
    """

    start_date_str = start_date.strip('"')

    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = to_email
    msg['Cc'] = f"{cc_email1},{cc_email2},{cc_email3}"
    msg['Subject'] = f'Weekly work Performance from {start_date.strftime("%d-%m")} to {(start_date + timedelta(days=6)).strftime("%d-%m")}'
    msg.attach(MIMEText(message, 'html'))

    server.sendmail(sender_email, [to_email, cc_email1, cc_email2, cc_email3], msg.as_string())


   
    server.quit()

    employee_id_str = str(employee_id)
    email_data = {
        "sender_name": signature,  
        "sender_email": sender_email,
        "employee_id": employee_id_str,
        "employee_email": to_email,
        "message": db_message,
        "company": current_user["company"],
        "title":  f'Weekly work Performance from {start_date.strftime("%d-%m")} to {(start_date + timedelta(days=6)).strftime("%d-%m")}',
        "timestamp": datetime.now(pytz.timezone(current_user["time_zone"])),
    }
    
    collection4.insert_one(email_data)
    email_data["_id"] = str(email_data["_id"])
    return jsonify({"message": "Email sent successfully"},email_data)



@email_send_app.route('/api/get_email_initials', methods=['GET'])
@token_required_admin
def get_email_initials(current_user):
    try:
        # Retrieve the date and employee_id from the request arguments
        date = request.args.get('date')
        employee_id = request.args.get('employee_id')

        company_stats = company_collection.find_one({"company": current_user["company"]},{"email_stats": 1, "name":1})

        # Fetch employee data from the MongoDB collection
        collection = db["user_collection"]
        user = collection.find_one({'_id': ObjectId(employee_id)})
        # If the user doesn't exist, return an error response
        if not user:
            return jsonify({"error": "Employee not found"}), 404
        
        name = user.get("name")
        to_email = user.get('email')
        time_tracking = user.get('time_tracking', [])
        
        # Calculate the date range based on the provided date or default to the previous week
        if not date:
            today = datetime.now(pytz.timezone(current_user["time_zone"]))
            end_date = today - timedelta(days=today.weekday())  # Previous Saturday
            start_date = end_date - timedelta(days=6)  # Previous Monday
        else:
            # Convert date string to datetime
            start_date = datetime.strptime(date, '%Y-%m-%d')
            end_date = start_date + timedelta(days=6)  # Last 7 days
        
        # Define the range of dates for the week
        all_days = [start_date + timedelta(days=i) for i in range(7)]

        response_list = []

        # Process each day in the specified week
        for day in all_days:
            # Filter time tracking data for the current day
            day_str = day.strftime('%Y-%m-%d')
            result = next((entry for entry in time_tracking if entry['date'] == day_str), None)

            if result:
                work_update = result.get('work_update', None)
                attachment_url = result.get('attachment_url', None)
                work_url = result.get('work_url', None)

                # Get the day of the week
                day_of_week = day.strftime('%A')

                # Create a response dictionary for the day
                response = {
                    "date": day_str,
                    "day": day_of_week,
                    "work_update": work_update,
                    "attachment_url": attachment_url,
                    "work_url": work_url
                }
            else:
                # If no data for the day, set values to None
                response = {
                    "date": day_str,
                    "day": day.strftime('%A'),
                    "work_update": None,
                    "attachment_url": None,
                    "work_url": None
                }

            response_list.append(response)

        # Calculate weekly data using the updated calculate_weekly_data function
        weekly_data = calculate_weekly_data(employee_id, start_date.strftime('%Y-%m-%d'))
        total_elapsed_time_week = weekly_data["total_time_week"]
        total_elapsed_time_by_day = weekly_data["data"]
        on_leave_count = weekly_data["on_leave_count"]

        # Return a JSON response with the collected data
        return jsonify({
            'email_stats': company_stats['email_stats'],
            'work_update': response_list,
            'employee_id': employee_id,
            'employee_name': name,
            'employee_email': to_email,
            'total_time': total_elapsed_time_week,
            'leaves': on_leave_count,
            'Monday': total_elapsed_time_by_day['Monday'],
            'Tuesday': total_elapsed_time_by_day['Tuesday'],
            'Wednesday': total_elapsed_time_by_day['Wednesday'],
            'Thursday': total_elapsed_time_by_day['Thursday'],
            'Friday': total_elapsed_time_by_day['Friday'],
            'Saturday': total_elapsed_time_by_day['Saturday']
        })
    except Exception as e:
        # Return an error response if an exception occurs
        return jsonify({"error": str(e)}), 500


def send_otp_email(otp, email):
    sender_email = 'toggletimer@gmail.com'
    app_password = 'tamf cwmj asxh fplk'

    server = SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(sender_email, app_password)

    # HTML design for the email
    html_message = f"""
 <html lang="en">
 <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OTP Verification</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, 
Cantarell, sans-serif;
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
            background: linear-gradient(90deg, #00ff8e 0%, #00c9ff 100%);
            color: white;
            padding: 40px 30px;
            text-align: center;
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
            padding: 40px 30px;
            text-align: center;
        }}
        .greeting {{
            font-size: 18px;
            font-weight: 500;
            margin-bottom: 20px;
            color: #2c3e50;
        }}
        .message {{
            font-size: 16px;
            color: #555;
            margin-bottom: 30px;
            line-height: 1.7;
        }}
        .otp-container {{
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
            border: 2px solid #00c9ff;
            border-radius: 12px;
            padding: 30px;
            margin: 30px 0;
            position: relative;
            overflow: hidden;
        }}
        .otp-container::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, #00ff8e 0%, #00c9ff 100%);
        }}
        .otp-label {{
            font-size: 14px;
            font-weight: 600;
            color: #6c757d;
            margin-bottom: 15px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .otp-code {{
            font-size: 36px;
            font-weight: 700;
            color: #00c9ff;
            font-family: 'Courier New', monospace;
            letter-spacing: 8px;
            margin: 15px 0;
            text-shadow: 0 2px 4px rgba(0, 201, 255, 0.2);
        }}
        .otp-note {{
            font-size: 14px;
            color: #6c757d;
            margin-top: 15px;
        }}
        .security-notice {{
            background-color: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 20px;
            margin: 25px 0;
            border-radius: 4px;
            text-align: left;
        }}
        .security-notice h3 {{
            margin-top: 0;
            color: #856404;
            font-size: 16px;
            font-weight: 600;
        }}
        .security-notice p {{
            margin-bottom: 0;
            color: #856404;
            font-size: 14px;
        }}
        .expiry-info {{
            background-color: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            margin: 25px 0;
            border-left: 4px solid #00ff8e;
        }}
        .expiry-info h3 {{
            margin-top: 0;
            color: #2c3e50;
            font-size: 16px;
            font-weight: 600;
        }}
        .expiry-info p {{
            margin-bottom: 0;
            color: #555;
            font-size: 14px;
        }}
        .timer {{
            display: inline-block;
            background: linear-gradient(90deg, #00ff8e 0%, #00c9ff 100%);
            color: white;
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 14px;
            margin: 10px 0;
        }}
        
        .help-section {{
            background-color: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            margin: 25px 0;
            text-align: left;
        }}
        
        .help-section h3 {{
            margin-top: 0;
            color: #2c3e50;
            font-size: 16px;
            font-weight: 600;
        }}
        
        .help-section p {{
            margin: 8px 0;
            color: #555;
            font-size: 14px;
        }}
        
        .help-section a {{
            color: #00c9ff;
            text-decoration: none;
        }}
        
        .help-section a:hover {{
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
        
        .highlight {{
            color: #00c9ff;
            font-weight: 600;
        }}
        
        .warning-text {{
            color: #dc3545;
            font-weight: 600;
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
            .otp-code {{
                font-size: 28px;
                letter-spacing: 4px;
            }}
            .otp-container {{
                padding: 20px;
            }}
        }}
    </style>
 </head>
 <body>
    <div class="email-container">
        <div class="header">
            <h1>
 🔐 Verification Code</h1>
            <p>Secure your account with OTP verification</p>
        </div>
        <div class="content">
            <div class="message">
                We received a request to verify your account. Please use the verification code below 
to complete the process.
            </div>
            <div class="otp-container">
                <div class="otp-label">Your Verification Code</div>
                <div class="otp-code">{otp}</div>
                <div class="otp-note">Enter this code to verify your account</div>
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
    """

    # Create a MIME message with HTML content
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = email
    msg['Subject'] = 'OTP Verification'
    msg.attach(MIMEText(html_message, 'html'))

    # Send the email
    server.sendmail(sender_email, email, msg.as_string())

    # Close the server connection
    server.quit()

    return jsonify({'message': f'OTP sent for verification {otp}'}), 200


def send_admin_details(html_message, email,cc1, subject):
    # sender_email = 'toggletimer@hansrajventures.com'
    # app_password = 'kumq amqj yfmw uldb'

    sender_email = 'toggletimer@gmail.com'
    app_password = 'tamf cwmj asxh fplk'
    server = SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(sender_email, app_password)

    # Create a MIME message with HTML content
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = email
    msg['Cc'] = f"{cc1}"
    msg['Subject'] = subject
    msg.attach(MIMEText(html_message, 'html'))

    # Send the email
    server.sendmail(sender_email, email, msg.as_string())

    # Close the server connection
    server.quit()

    return jsonify({'message': ' Email is send !!'}), 200

@email_send_app.route('/api/emails/recent', methods=['GET'])
@token_required_admin
def get_recent_emails(current_user):
    try:
        # Retrieve emails from the collection in descending order of timestamp
        emails = list(collection4.find({'company': current_user['company']}).sort('timestamp', pymongo.DESCENDING))
        
        # Convert ObjectId and datetime to strings for JSON serialization
        for email in emails:
            email['_id'] = str(email['_id'])
            email['employee_id'] = find_user_info(str(email['employee_id']))
            email['timestamp'] = email['timestamp'].isoformat()
        
        return jsonify({'data':emails, 'message': 'Emails retrieved successfully','status':True}), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@email_send_app.route('/api/emails/employee/<employee_id>', methods=['GET'])
@token_required_admin
def get_emails_by_employee(current_user, employee_id):
    try:
        # Retrieve emails for the specific employee from the collection in descending order of timestamp
        emails = list(collection4.find({'employee_id': employee_id, 'company': current_user['company']}).sort('timestamp', pymongo.DESCENDING))
        
        # Convert ObjectId and datetime to strings for JSON serialization
        for email in emails:
            email['_id'] = str(email['_id'])
            email['employee_id'] = find_user_info(str(email['employee_id']))
            email['timestamp'] = email['timestamp'].isoformat()
        
        return jsonify({'data': emails, 'message': 'Emails retrieved successfully', 'status': True}), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500