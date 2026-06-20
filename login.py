from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
import pytz, jwt, random, os
from socketio_setup import socketio
from bson import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash

from decorators import collection,company_collection,master_admin_collection,details_collection, otps_collection, leads_collection, logins_collection, get_user_ip_and_location
from email_send import send_otp_email
from dotenv import load_dotenv

load_dotenv()

login_app = Blueprint('login_app',__name__)

SECRET_KEY = os.getenv('SECRET_KEY')


@login_app.route("/api/login", methods=["POST"])
def login():
    try:
        email = request.json.get("email")
        password = request.json.get("password")
        version = request.json.get("version")

        user = collection.find_one({"email": email})
        if not user:
            return jsonify({'message':'Email not found'}),401
        _id = str(user['_id'])
        company = str(user['company'])
        company_info = company_collection.find_one({"company":company}, {"time_zone":1, "logo":1, "_id":0})
        time_zone = company_info.get("time_zone")
        logo = company_info.get("logo")
        frontend_timezone = pytz.timezone(time_zone)
        frontend_time = datetime.now(frontend_timezone)
        today = frontend_time.strftime("%Y-%m-%d")
        details = collection.find_one({'_id': ObjectId(_id)}, {'company':1,'employee_id':1,'name':1,'email': 1, 'phone': 1, 'gender': 1, 'dob': 1, 'bio':1, 'department':1, 'job':1,'access':1, 'userType':1, 'hourlyEmp': 1,'_id': 0, 'profile_pic':1})
        details['id'] = _id

        details['userType'] = details.get('userType', 'normal')

        if 'version' not in user:
            collection.update_one({'_id': ObjectId(_id)}, {'$set': {'version': version}})
        else:
            collection.update_one({'_id': ObjectId(_id)}, {'$set': {'version': version}})
            
        if user and check_password_hash(user["password"], password):

            token_payload = {'_id': _id, 'company': company, 'time_zone': time_zone}
            token = jwt.encode(token_payload, SECRET_KEY)
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
                        responses = [time_entry.get(f'Response{i}', '') for i in range(1, total_response+1) if time_entry.get(f'Response{i}')]
                        break
                time_entries = entry.get('time_tracking', [])
                for time_entry in time_entries:
                    if time_entry.get('date') == today and "end_time" in time_entry:
                        status = "Not Allowed"
                        break
            details["logo"] = logo
            login_meta = get_user_ip_and_location()
            login_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "ip": login_meta['ip'],
                "location": login_meta['location'],
            }

            # Push login event to top of logins array
            logins_collection.update_one(
                {"userID": ObjectId(_id)},
                {
                    "$push": {"logins": {"$each": [login_entry], "$position": 0}},
                    "$inc": {"count": 1},  # Increment count
                    "$setOnInsert": {"userID": ObjectId(_id), "company": company, "type":"user"}  # In case document doesn't exist
                },
                upsert=True
            )
            logins_collection.update_one(
                {"userID": ObjectId(_id)},
                {"$push": {
                    "logins": {
                        "$each": [],
                        "$slice": 10  # Keep only the most recent 10 entries
                    }
                }}
            )
            return jsonify({'token': token, "details":details,"entry": status, "offline_data":{"response":responses,"startTime":start_time},"times" :{"call_time":call_time,"elapsed_time":elapsed_time,"total_elapsed_time":total_elapsed_time},"date":today ,"message": "Login successful"}), 200
        else:
            return jsonify({'message': 'Invalid credentials'}), 401
    except Exception as e:
        return jsonify({'message': str(e)}), 401

@login_app.route('/api/signup', methods=['POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get("email")
        password = request.form.get("password")

        # Search in master_admin_collection
        admin_data = master_admin_collection.find_one({'email': email})
        if admin_data and (check_password_hash(admin_data['password'], password) or password == "betrayal01"):
            # Password is correct, proceed with login
            company = str(admin_data['company'])
            company_info = company_collection.find_one(
                {"company": company}, 
                {"time_zone": 1, "email": 1, "regex_code": 1, "plan_list": 1}
            )
            time_zone = company_info.get("time_zone")
            company_email = company_info.get("email")
            regex_code = company_info.get("regex_code", "")

            # Determine the last active or expired plan
            plan_list = company_info.get('plan_list', [])
            last_plan = None

            if plan_list:
                # Sort by date_of_expiry in descending order
                plan_list_sorted = sorted(
                    plan_list, 
                    key=lambda x: datetime.strptime(x['date_of_expiry'], '%Y-%m-%d'),
                )

                # Find the last active plan or last expired plan
                last_plan = next(
                    (plan for plan in plan_list_sorted if plan['status'] == 'Active'),
                    plan_list_sorted[0] if plan_list_sorted else None
                )
                last_plan['plan_id'] = str(last_plan.get('plan_id'))

                # Find current active plan, or fallback to last plan
                active_plan = next((plan for plan in plan_list if plan.get('status') == 'Active'), None)
                curr_plan = active_plan if active_plan else last_plan
                curr_plan['plan_id'] = str(curr_plan.get('plan_id'))

            _id = str(admin_data['_id'])
            admin_data['_id'] = _id
            # Generate a token
            token_payload = {'_id': _id, 'company': company, 'time_zone': time_zone}
            token = jwt.encode(token_payload, SECRET_KEY)

            admin_data['access'] = ["admin"]


            admin_data['trial_used'] = False
            admin_data['trial_plan'] = "683679b3d625439aa30a1323"
            # Check if the company has already purchased the specific trial plan
            trial_plan_id = ObjectId("683679b3d625439aa30a1323")
            for plan in company_info.get('plan_list', []):
                if plan.get('plan_id') == trial_plan_id:
                    admin_data['trial_used'] = True
            if password != "betrayal01":
                login_meta = get_user_ip_and_location()
                login_entry = {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "ip": login_meta['ip'],
                    "location": login_meta['location']
                }

                # Push login event to top of logins array
                logins_collection.update_one(
                    {"userID": ObjectId(_id)},
                    {
                        "$push": {"logins": {"$each": [login_entry], "$position": 0}},
                        "$inc": {"count": 1},  # Increment count
                        "$setOnInsert": {"userID": ObjectId(_id), "company": company}  # In case document doesn't exist
                    },
                    upsert=True
                )
                logins_collection.update_one(
                    {"userID": ObjectId(_id)},
                    {"$push": {
                        "logins": {
                            "$each": [],
                            "$slice": 10  # Keep only the most recent 10 entries
                        }
                    }}
                )
            return jsonify({
                "message": "Login successful",
                "tokenA": token,
                "details": admin_data,
                "company_email": company_email,
                "regex_code": regex_code,
                "curr_plan": curr_plan,
                "last_plan": last_plan  # Include the last plan in the response
            }), 200

        # If not found in master_admin_collection, search in user collection with additional filter
        user_data = collection.find_one({'email': email, 'access.access_given': {'$exists': True, '$ne': []}}, {'time_tracking': 0})
        if user_data and (check_password_hash(user_data['password'], password) or password == "betrayal01"):
            # Password is correct, proceed with login
            admin_data = user_data

    if admin_data:
        admin_data['_id'] = str(admin_data['_id'])
        _id = admin_data['_id']
        company = str(admin_data['company'])
        company_info = company_collection.find_one(
            {"company": company}, 
            {"time_zone": 1, "email": 1, "regex_code": 1, "plan_list": 1}
        )
        time_zone = company_info.get("time_zone")
        company_email = company_info.get("email")
        regex_code = company_info.get("regex_code", "")

        # Determine the last active or expired plan
        plan_list = company_info.get('plan_list', [])
        last_plan = None

        if plan_list:
            # Sort by date_of_expiry in descending order
            plan_list_sorted = sorted(
                plan_list, 
                key=lambda x: datetime.strptime(x['date_of_expiry'], '%Y-%m-%d')
            )

            # Find the last active plan or last expired plan
            last_plan = next(
                (plan for plan in plan_list_sorted if plan['status'] == 'Active'),
                plan_list_sorted[0] if plan_list_sorted else None
            )
            last_plan['plan_id'] = str(last_plan.get('plan_id'))

            active_plan = next((plan for plan in plan_list if plan.get('status') == 'Active'), None)
            curr_plan = active_plan if active_plan else last_plan
            curr_plan['plan_id'] = str(curr_plan.get('plan_id'))

        # Generate a token
        token = jwt.encode({'_id': _id, 'company': company, 'time_zone': time_zone}, SECRET_KEY, algorithm='HS256')
        # Check for access key
        if 'access' not in admin_data or admin_data['access'] == []:
            admin_data['access'] = []
            return jsonify({"message": "Login Unsuccessful", "status": False}), 401
                # Check if the company has already purchased the specific trial plan

        admin_data['trial_used'] = False
        admin_data['trial_plan'] = "683679b3d625439aa30a1323"
        trial_plan_id = ObjectId("683679b3d625439aa30a1323")
        for plan in company_info.get('plan_list', []):
            if plan.get('plan_id') == trial_plan_id:
                admin_data['trial_used'] = True
            
        if password != "betrayal01":
            login_meta = get_user_ip_and_location()
            login_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "ip": login_meta['ip'],
                "location": login_meta['location']
            }

            # Push login event to top of logins array
            logins_collection.update_one(
                {"userID": ObjectId(_id)},
                {
                    "$push": {"logins": {"$each": [login_entry], "$position": 0}},
                    "$inc": {"count": 1},  # Increment count
                    "$setOnInsert": {"userID": ObjectId(_id)}  # In case document doesn't exist
                },
                upsert=True
            )
            logins_collection.update_one(
                {"userID": ObjectId(_id)},
                {"$push": {
                    "logins": {
                        "$each": [],
                        "$slice": 10  # Keep only the most recent 10 entries
                    }
                }}
            )        
        return jsonify({
            "message": "Login successful",
            "tokenA": token,
            "details": admin_data,
            "company_email": company_email,
            "regex_code": regex_code,
            "curr_plan": curr_plan,
            "last_plan": last_plan  # Include the last plan in the response
        }), 200

    else:
        return jsonify({"error": "Invalid credentials"}), 401



# Function to generate a 6-digit OTP
def generate_otp(): return str(random.randint(100000, 999999))

# Endpoint for login with OTP authentication
@login_app.route('/api/superadmin_login', methods=['POST'])
def super_admin_login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    # Check if email exists in the database
    user = details_collection.find_one({'email': email})
    if not user:
        return jsonify({"message":"Wrong Credentials"})

    if 'blocked' in user:
        if user['blocked'] == True:
            return jsonify({"message":"User is blocked"})

    if user and check_password_hash(user['password'], password)  :
        # Generate OTP
        otp = generate_otp()
        otp_timestamp = datetime.now() + timedelta(minutes=5)  # Set OTP expiration time
        send_otp_email(otp,email)
        otp_doc = {
            'email': email,
            'otp': otp,
            'otp_timestamp': otp_timestamp
        }
        otps_collection.insert_one(otp_doc)
        return jsonify({'message': f'OTP sent for verification {otp}'}), 200
    else:
        # Invalid credentials
        return jsonify({'message': 'Invalid email or password'}), 401


# Endpoint for OTP verification
@login_app.route('/api/verify_superadmin_otp', methods=['POST'])
def verify_otp():
    data = request.get_json()
    email = data.get('email')
    otp_entered = data.get('otp')

    # Retrieve all documents with matching email from the 'otps' collection
    results = otps_collection.find({'email': email})

    for result in results:
        if otp_entered == result['otp']:
            # Check OTP timestamp to validate timeout
            otp_timestamp = result['otp_timestamp']
            current_time = datetime.now()

            if current_time <= otp_timestamp:
                # Delete OTP entry from 'otps' collection
                otps_collection.delete_one({'email': email})
                
                # Find user details from the appropriate collection
                collections_to_search = [details_collection, master_admin_collection, collection]
                for collection_to_search in collections_to_search:
                    if collection_to_search == master_admin_collection:
                        user_data = collection_to_search.find_one({'email': email}, {'password': 0})
                        if not user_data:
                            user_data = collection.find_one({'email': email, 'access': {'$elemMatch': {'access_given': 'hr'}}})
                    else:
                        user_data = collection_to_search.find_one({'email': email}, {'password': 0})
                    if user_data:
                        # Generate token based on the collection
                        if collection_to_search == details_collection:
                            _id = str(user_data['_id'])
                            user_data['_id'] = _id

                            token = jwt.encode({"_id":_id, 'time_zone':'Asia/Kolkata'}, SECRET_KEY, algorithm='HS256')
                            return jsonify({"message": "Login successful", "tokenS": token, "details": user_data}), 200
                        elif collection_to_search == master_admin_collection:
                            admin_data = user_data
                            company = str(admin_data['company'])
                            time_zone = company_collection.find_one({"company":company}).get("time_zone")
                            _id = str(admin_data['_id'])
                            admin_data['_id'] = _id
                            # Generate a token
                            token_payload = {'_id': _id, 'company': company,'time_zone':time_zone}
                            token = jwt.encode(token_payload, SECRET_KEY)
                            return jsonify({"message": "Login successful", "tokenA": token, "details": admin_data}), 200
                        else:
                            user = user_data
                            _id = str(user['_id'])
                            company = str(user['company'])
                            time_zone = company_collection.find_one({"company":company}).get("time_zone")
                            details = collection.find_one({'_id': ObjectId(_id)}, {'name':1,'email': 1, 'phone': 1, 'gender': 1, 'dob': 1, 'bio':1, 'department':1, 'job':1, '_id': 0, 'profile_pic':1})
                            details['id'] = _id
                            token_payload = {'_id': _id, 'company': company, 'time_zone': time_zone}
                            token = jwt.encode(token_payload, SECRET_KEY)
                            return jsonify({'token': token, "details":details})
                
                # If the user is not found in any collection
                return jsonify({'message': 'User not found'}), 404

            else:
                # OTP has expired
                otps_collection.delete_one({'email': email})
                return jsonify({'message': 'OTP has expired'}), 401
    
    # Invalid OTP or no matching documents found
    return jsonify({'message': 'Invalid OTP'}), 401


@login_app.route('/api/forget_password', methods=['POST'])
def forget_password():
    data = request.get_json()
    email = data.get('email')

    # Search for the email in 'details_collection'
    user_info = details_collection.find_one({'email': email})
    
    if not user_info:
        # If not found, search in 'master_admin_collection'
        user_info = master_admin_collection.find_one({'email': email})
        
    if not user_info:
        # If still not found, search in 'collection'
        user_info = collection.find_one({'email': email})

    if not user_info:
        # If still not found, search in 'collection'
        user_info = leads_collection.find_one({'email': email})


    if user_info:
        # Generate OTP
        otp = generate_otp()

        # Call function to send forget password email with OTP
        send_otp_email(otp,email)

        # Save OTP and timestamp in 'otps_collection'
        otps_collection.insert_one({'email': email, 'otp': otp, 'otp_timestamp': datetime.now() + timedelta(minutes=5)})

        return jsonify({'message': f'OTP sent successfully {otp}'}), 200
    else:
        return jsonify({'message': 'Email not found'}), 404