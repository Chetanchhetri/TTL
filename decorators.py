from functools import wraps
from flask import Flask, Response, request, jsonify
import jwt , pytz, os, json
from pymongo import MongoClient, DESCENDING
from threading import Lock
from bson import ObjectId
from datetime import datetime, timedelta
from pyrebase import pyrebase
from dotenv import load_dotenv
import requests
load_dotenv()

# MongoDB Client initialization
mongo_uri = os.getenv('mongoclient') or os.getenv('MONGO_CLIENT') or os.getenv('MONGODB_URI')
client = MongoClient(mongo_uri)

db = client["user_db"]
collection = db["user_collection"]
time_tracking_db = client["test_timetracking"]
master_admin_collection = db['master_admin']
logins_collection = db['logins']
moms_collection = db['logs']
notice_collection = db['notices']
deleted_employees_collection = db["deleted_employees"]
tasks_collection = db["tasks"]
notification_collection = db["notifications"]
chat_collection = db["chats"]
ticket_collection = db["tickets"]
otps_collection = db['otps']
leaves_collection = db['leaves']
super_admin_db = client["super_admin"]
company_collection = super_admin_db["companies"]
plans_collection = super_admin_db["plans"]
details_collection = super_admin_db["details"]
leads_collection = super_admin_db["leads"]
queries_collection = super_admin_db["queries"]
payment_collection = super_admin_db["payment"]
payment_requests_collection = super_admin_db["payment_requests"]
complains_collection = super_admin_db["complains"]
settings_collection = super_admin_db["settings"]
dropdown_collection = super_admin_db["dropdowns"]

SECRET_KEY = os.getenv('SECRET_KEY') or os.getenv('secret_key')

# Dynamic Firebase Config Parser
firebase_bucket = os.getenv('storageBucket') or os.getenv('STORAGE_BUCKET') or os.getenv('storage_bucket') or ""

config = {
  'apiKey': os.getenv('apiKey') or os.getenv('API_KEY'),
  'databaseURL': os.getenv('databaseURL') or os.getenv('DATABASE_URL'),
  'authDomain': os.getenv('authDomain') or os.getenv('AUTH_DOMAIN'),
  'projectId': os.getenv('projectId') or os.getenv('PROJECT_ID'),
  'storageBucket': firebase_bucket,
  'messagingSenderId': os.getenv('messangingSenderId') or os.getenv('MESSAGING_SENDER_ID'),
  'appId': os.getenv('appId') or os.getenv('APP_ID'),
  'measurementId': os.getenv('measurementId') or os.getenv('MEASUREMENT_ID')
}

# Safeguard against missing configuration errors to prevent server crash
if not config['storageBucket']:
    print("[WARNING]: storageBucket key not found in .env. Using fallback identifier string.")
    config['storageBucket'] = "toggletimerr.firebasestorage.app"

f = pyrebase.initialize_app(config)
storage = f.storage()

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')

        if not token:
            return jsonify({'message': 'Token is missing'}), 401

        try:
            decoded_token = jwt.decode(token.split(' ')[1], SECRET_KEY, algorithms=["HS256"])
            current_user = collection.find_one({"_id": ObjectId(decoded_token['_id'])})
            if current_user is None:
                current_user = master_admin_collection.find_one({"_id": ObjectId(decoded_token['_id'])})
            if not monitor_plans(current_user['company']):
                return jsonify({'message': 'Plan has expired or company got deleted.'}), 401
        except:
            return jsonify({'message': 'Token is invalid'}), 401
        if current_user:
            # Extract 'time_zone' from the decoded token
            time_zone = decoded_token.get('time_zone')
            # Add 'time_zone' to the current_user dictionary
            current_user['time_zone'] = time_zone
            return f(current_user, *args, **kwargs)
        else:
            return jsonify({'message':'User not allowed'})

    return decorated

def socket_token(token):
    try:
        decoded_token = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        current_user = collection.find_one({"_id": ObjectId(decoded_token['_id'])})
        if current_user is None:
            current_user = master_admin_collection.find_one({"_id": ObjectId(decoded_token['_id'])})
        if not monitor_plans(current_user['company']):
            return False
    except:
        return False
    if current_user:
        # Extract 'time_zone' from the decoded token
        time_zone = decoded_token.get('time_zone')
        # Add 'time_zone' to the current_user dictionary
        current_user['time_zone'] = time_zone
        return current_user
    else:
        return False

def token_required_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')

        if not token:
            return jsonify({'message': 'Token is missing'}), 401

        try:
            data = jwt.decode(token.split(' ')[1], SECRET_KEY, algorithms=["HS256"])
            current_user = master_admin_collection.find_one({"_id": ObjectId(data['_id'])})
            # If not found in master_admin_collection, check in user collection
            if not current_user:
                current_user = collection.find_one({"_id": ObjectId(data['_id']), 'access': {'$exists': True, '$ne': []}},{'time_tracking':0})
            if not current_user:
                raise Exception("Admin not found")     
            if not monitor_plans(current_user['company']):
                return jsonify({'message': 'Plan has expired.'}), 401       
        except:
            return jsonify({'message': 'Token is invalid'}), 401
        
        if current_user:
            # Extract 'time_zone' from the decoded token
            time_zone = data['time_zone']

            # Add 'time_zone' to the current_user dictionary
            current_user['time_zone'] = time_zone
            return f(current_user, *args, **kwargs)
        else:
            return jsonify({'message':'User not allowed'})

    return decorated

def token_required_superadmin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')

        if not token:
            return jsonify({'message': 'Token is missing'}), 401

        try:
            data = jwt.decode(token.split(' ')[1], SECRET_KEY, algorithms=["HS256"])
            current_user = details_collection.find_one({"_id": ObjectId(data['_id'])})
            if not current_user:
                raise Exception("Super Admin not found")          
        except:
            return jsonify({'message': 'Token is invalid'}), 401
        
        if current_user:
            return f(current_user, *args, **kwargs)
        else:
            return jsonify({'message':'User not allowed'})

    return decorated

def token_required_landing(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token is missing'}), 401
        try:
            decoded_token = jwt.decode(token.split(" ")[1], SECRET_KEY, algorithms=["HS256"])
            email = decoded_token.get('email')
            lead_id = decoded_token.get('lead_id')

            if not email or not lead_id:
                return jsonify({'message': 'Invalid token payload'}), 401

            current_user = {
                'email': email,
                'lead_id': lead_id
            }

            return f(current_user, *args, **kwargs)
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Invalid token'}), 401
        except Exception as e:
            return jsonify({'message': str(e)}), 500

    return decorated

def token_required_admin_or_superadmin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')

        if not token:
            return jsonify({'message': 'Token is missing'}), 401

        try:
            data = jwt.decode(token.split(' ')[1], SECRET_KEY, algorithms=["HS256"])

            # First, check in Super Admin collection
            current_user = details_collection.find_one({"_id": ObjectId(data['_id'])})
            user_type = "super_admin"

            # If not Super Admin, check in Master Admin collection
            if not current_user:
                current_user = master_admin_collection.find_one({"_id": ObjectId(data['_id'])})
                user_type = "admin"

            # If still not found, check in User collection (with access)
            if not current_user:
                current_user = collection.find_one(
                    {"_id": ObjectId(data['_id']), 'access': {'$exists': True, '$ne': []}},
                    {'time_tracking': 0}
                )
                user_type = "admin"

            if not current_user:
                raise Exception("User not found")

            # Check plan for admins only
            if user_type == "admin" and not monitor_plans(current_user['company']):
                return jsonify({'message': 'Plan has expired.'}), 401

            # Add user_type and time_zone to current_user
            current_user['user_type'] = user_type
            if 'time_zone' in data:
                current_user['time_zone'] = data['time_zone']

            return f(current_user, *args, **kwargs)

        except Exception as e:
            return jsonify({'message': 'Token is invalid', 'error': str(e)}), 401

    return decorated

def upload_to_firebase(file,folder_name, employee_name):
    try:
        # Get the file extension from the original filename
        file_extension = os.path.splitext(file.filename)[1]

        # Generate a unique filename prefixed with TT_Testing
        unique_filename = f"TT_Testing/{folder_name}/{employee_name}/{datetime.now().strftime('%Y%m%d%H%M%S')}{file_extension}"

        # Upload file to Firebase storage
        storage.child(unique_filename).put(file)

        # Get the download URL
        url = storage.child(unique_filename).get_url(None)
        return url
    except Exception as e:
        raise Exception(f"Error uploading to Firebase: {str(e)}")

def upload_ss_to_firebase(file,company, empId,date, filename):
    try:
        # Get the file extension from the original filename
        file_extension = os.path.splitext(file.filename)[1]

        # Generate a unique filename prefixed with TT_Testing
        unique_filename = f"TT_Testing/{company}/{empId}/{date}/{filename}{file_extension}"

        # Upload file to Firebase storage
        storage.child(unique_filename).put(file)

        # Get the download URL
        url = storage.child(unique_filename).get_url(None)
        return url
    except Exception as e:
        raise Exception(f"Error uploading to Firebase: {str(e)}")
    
# def upload_to_firebase(file,folder_name, employee_name):
#     try:
#         response = requests.post(
#             "https://drive-microservice.vercel.app/api/upload_extras",
#             files={"file": file},
#             data={"folder_name": folder_name, "employee_name": employee_name}
#         )

#         if response.status_code != 200:
#             return jsonify({'error': 'Failed to upload to Google Drive', 'status': False}), 500

#         url = response.json().get("data")
#         return url
#     except Exception as e:
#         raise Exception(f"Error uploading to Firebase: {str(e)}")

def find_user_info(user_id):
    # Try to find the user in the user_collection
    user_info = collection.find_one({'_id': ObjectId(user_id)}, {'name': 1, 'profile_pic': 1,'job' :1, '_id':1})

    if not user_info:
        # If the user is not found in user_collection, try finding in deleted collection
        user_info = deleted_employees_collection.find_one({'_id': ObjectId(user_id)}, {'name': 1, 'profile_pic': 1,'job' :1, '_id':1})
    if not user_info:
        # If the user is not found in user_collection, try finding in admin_collection
        user_info = master_admin_collection.find_one({'_id': ObjectId(user_id)}, {'name': 1, 'profile_pic': 1,'job':1, '_id':1})

    if user_info and '_id' in user_info:
        # Convert _id to string
        user_info['_id'] = str(user_info['_id'])

    return user_info

def find_users_info(user_ids):
    object_ids = [ObjectId(uid) for uid in user_ids]

    # Fetch only required fields and last time_tracking entry using $slice
    users = list(collection.find(
        {'_id': {'$in': object_ids}}, 
        {'name': 1, 'profile_pic': 1, 'job': 1, '_id': 1, 'time_tracking': {'$slice': -3}}
    ))
    
    if len(users) == len(user_ids):  # If all users found, return early
        return [{**user, '_id': str(user['_id'])} for user in users]

    # Find missing user IDs
    found_ids = {str(user['_id']) for user in users}
    missing_ids = [uid for uid in user_ids if uid not in found_ids]

    if missing_ids:
        deleted_users = list(deleted_employees_collection.find(
            {'_id': {'$in': [ObjectId(uid) for uid in missing_ids]}}, 
            {'name': 1, 'profile_pic': 1, 'job': 1, '_id': 1, 'time_tracking': {'$slice': -3}}
        ))
        users.extend(deleted_users)
        found_ids.update({str(user['_id']) for user in deleted_users})

    # Find still missing users in master admin collection
    missing_ids = [uid for uid in user_ids if uid not in found_ids]
    if missing_ids:
        admin_users = list(master_admin_collection.find(
            {'_id': {'$in': [ObjectId(uid) for uid in missing_ids]}}, 
            {'name': 1, 'profile_pic': 1, 'job': 1, '_id': 1, 'time_tracking': {'$slice': -3}}
        ))
        users.extend(admin_users)

    # Convert ObjectId to string for all users
    return [{**user, '_id': str(user['_id'])} for user in users]

def find_admin_info(user_id):
    user_info = master_admin_collection.find_one({'_id': ObjectId(user_id)}, {'name': 1, 'profile_pic': 1,'company' :1,'email':1,'_id':1})
    company_info = None
    if not user_info:
        user_info = collection.find_one({'_id': ObjectId(user_id)}, {'name': 1, 'profile_pic': 1,'email':1, '_id':1, 'company':1})
    if user_info:
        company_info = company_collection.find_one({'company':user_info['company']},{'name':1})

    if user_info and '_id' in user_info:
        # Convert _id to string
        user_info['_id'] = str(user_info['_id'])
        if company_info:
            user_info['company_name'] = company_info['name']
    return user_info

def get_emp_list(emp_list):
    emp_list_copy = [{'sid': dic['sid'], 'time': dic['time'], '_id': find_user_info(dic["_id"])} for dic in emp_list]
    return emp_list_copy

def monitor_plans(company_code):
    company = company_collection.find_one({
        'company': company_code,
        'deleted': {'$ne': True}
    })
    if not company:
        return False
    frontend_timezone = pytz.timezone(company['time_zone'])
    current_time = datetime.now(frontend_timezone).strftime('%Y-%m-%d')

    if company:
        # This loop makes illegal plan "expired"
        for plan in company['plan_list']:
            if plan['status'] == 'Active' and plan['date_of_expiry'] > current_time:
                if 'plan_id' in plan:
                    selected_plan = plans_collection.find_one({'_id': ObjectId(plan['plan_id'])})
                else:
                    selected_plan = plans_collection.find_one({'name': plan['name']})
                
                if selected_plan is None:
                    return False
                company_collection.update_one({'_id': company['_id']}, {'$set': {'plan_list': company['plan_list'],'maxAdm':selected_plan['maxAdm'],'maxEmp':selected_plan['maxEmp']}})
                return True
            elif plan['status'] == 'Active' and plan['date_of_expiry'] < current_time:
                plan['status'] = 'Expired'
                company_collection.update_one({'_id': company['_id']}, {'$set': {'plan_list': company['plan_list']}})
                
                for plan in company['plan_list']:        
                    if plan['status'] == 'Inactive' and plan['date_of_expiry'] > current_time:
                        plan['status'] = 'Active'
                        selected_plan = plans_collection.find_one({'name': plan['name']})
                        if selected_plan is None:
                            return False
                        company_collection.update_one({'_id': company['_id']}, {'$set': {'plan_list': company['plan_list'],'maxAdm':selected_plan['maxAdm'],'maxEmp':selected_plan['maxEmp']}})
                        return True
                return False
    else:
        return False

def process_time_entry(entry, employee_monthly_data, time_zone):
    date_str = entry.get('date', '')
    start_time_str = entry.get('start_time', '00:00:00')
    end_time_str = entry.get('end_time', datetime.now(pytz.timezone(time_zone)).strftime('%H:%M:%S'))
    elapsed_time_str = entry.get('elapsed_time', '00:00:00')
    call_time_str = entry.get('call_time', '00:00:00')

    date = datetime.strptime(date_str, '%Y-%m-%d')
    entry_month = date.strftime('%Y-%m')

    # Initialize monthly data for the employee's month if not exists
    if entry_month not in employee_monthly_data["monthly_details"]:
        employee_monthly_data["monthly_details"][entry_month] = {
            'active_time': 0.0,
            'inactive_time': 0.0,
            'call_time': 0.0,
            'total_responses': 0,   # New Field
            'hit_responses': 0      # New Field
        }

    try:
        # Calculate active, inactive, and call time
        start_time = datetime.strptime(start_time_str, '%H:%M:%S')
        end_time = datetime.strptime(end_time_str, '%H:%M:%S')
        elapsed_time = datetime.strptime(elapsed_time_str, '%H:%M:%S') - datetime.strptime('00:00:00', '%H:%M:%S')
        call_time = datetime.strptime(call_time_str, '%H:%M:%S') - datetime.strptime('00:00:00', '%H:%M:%S')

        active_time = max(0, elapsed_time.total_seconds())
        inactive_time = max(0, (end_time - start_time - elapsed_time - call_time).total_seconds())
        call_time = max(0, call_time.total_seconds())

        # Update time tracking values
        employee_monthly_data["monthly_details"][entry_month]['active_time'] += active_time
        employee_monthly_data["monthly_details"][entry_month]['inactive_time'] += inactive_time
        employee_monthly_data["monthly_details"][entry_month]['call_time'] += call_time

        # 🔹 Calculate Responses Data 🔹
        total_responses = entry.get("Responses", 0)
        hit_responses = total_responses  # Start with total count

        for i in range(1, total_responses + 1):
            response_key = f"Response{i}"
            if response_key in entry and "Missed" in entry[response_key]:
                hit_responses -= 1  # Reduce hit count if response is missed

        # Update responses data
        employee_monthly_data["monthly_details"][entry_month]['total_responses'] += total_responses
        employee_monthly_data["monthly_details"][entry_month]['hit_responses'] += hit_responses

    except ValueError as e:
        print("Error processing time entry:", e)
    except Exception as e:
        print("Error:", e)

def upload_report_firebase(file, folder_name, file_name):
    try:
        # Upload file to Firebase storage
        unique_filename = f"TT_Testing/{folder_name}/{file_name}"
        storage.child(unique_filename).put(file, file_name)

        # Get the download URL
        url = storage.child(unique_filename).get_url(None)
        return url
    except Exception as e:
        raise Exception(f"Error uploading to Firebase: {str(e)}")
    
def get_user_ip_and_location():
    # Step 1: Get client IP
    if request.headers.get('X-Forwarded-For'):
        ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    else:
        ip = request.remote_addr

    # Step 2: Handle local dev fallback
    is_local = ip.startswith('127.') or ip == 'localhost'

    if is_local:
        ip = '122.161.43.24'  # Replace with your external test IP
        dev_mode = True
    else:
        dev_mode = False

    # Step 3: Fetch geo info
    try:
        geo_resp = requests.get(f'https://ipinfo.io/{ip}/json/', timeout=5)
        geo_data = geo_resp.json()
    except Exception as e:
        geo_data = {'error': f'Failed to fetch geo info: {str(e)}'}

    return {
        'ip': ip,
        'location': geo_data,
        'note': 'Using fallback IP for local development' if dev_mode else 'Live IP used'
    }

# Add a lock for thread safety
id_generation_lock = Lock()

def generate_unique_lead_id():
    with id_generation_lock:  # Ensure thread safety
        # Find the lead with the highest lead_id
        highest_lead = leads_collection.find_one(
            {"lead_id": {"$regex": "^L\\d{6}$"}},  # Match IDs in the format L000001
            sort=[("lead_id", DESCENDING)]         # Sort by lead_id in descending order
        )

        if highest_lead:
            # Extract the numeric part, increment it, and format it back
            last_id = int(highest_lead["lead_id"][1:])  # Strip the 'L' and convert to int
            new_id = f"L{last_id + 1:06d}"             # Increment and format as L000001
        else:
            # If no leads are found, start with L000001
            new_id = "L000001"

        return new_id