from flask import Blueprint, request, jsonify
import jwt
from socketio_setup import socketio
from bson import ObjectId
import pytz, random, json, requests, base64, hashlib, os
from datetime import datetime, timedelta
from pymongo import DESCENDING
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from dateutil.parser import parse

load_dotenv()

from decorators import payment_requests_collection,queries_collection ,otps_collection , db, master_admin_collection, company_collection, plans_collection, token_required_superadmin, upload_to_firebase, leads_collection, payment_collection, find_admin_info, generate_unique_lead_id, token_required_landing
from email_send import send_otp_email, send_admin_details

SECRET_KEY = os.getenv('SECRET_KEY')


landing_page_app = Blueprint('landing_page_app',__name__)

# Configuration variables (replace with your actual values)
MERCHANT_ID = os.getenv('MERCHANT_ID')
API_KEY_VALUE = os.getenv('API_KEY_VALUE')
API_KEY_INDEX = os.getenv('API_KEY_INDEX')
REDIRECT_URL = os.getenv('redirectUrl')
HOST_URL = 'https://api.phonepe.com/apis/hermes'
PAY_ENDPOINT = '/pg/v1/pay'
STATUS_ENDPOINT = '/pg/v1/status'

def generate_x_verify(payload, endpoint):
    base64_payload = base64.b64encode(json.dumps(payload).encode('utf-8')).decode('utf-8')
    x_verify = hashlib.sha256((base64_payload + endpoint + API_KEY_VALUE).encode('utf-8')).hexdigest() + '###' + API_KEY_INDEX
    return x_verify

def x_verify_for_status(merchant_transaction_id):
    url_segment = f"{STATUS_ENDPOINT}/{MERCHANT_ID}/{merchant_transaction_id}"
    x_verify = hashlib.sha256((url_segment + API_KEY_VALUE).encode('utf-8')).hexdigest() + '###' + API_KEY_INDEX
    return x_verify


@landing_page_app.route('/api/payment_status', methods=['GET'])
def payment_status():
    payment_id = request.args.get('merchantTransactionId')
    payment_type = request.args.get('paymentType')
    if payment_type == 'initial':
        try:
            x_verify = x_verify_for_status(payment_id)
            phonepe_url = f"{HOST_URL}{STATUS_ENDPOINT}/{MERCHANT_ID}/{payment_id}"
            headers= {
                'accept': 'application/json',
                'Content-Type': 'application/json',
                "X-MERCHANT-ID": MERCHANT_ID,
                "X-VERIFY": x_verify,
                    }
            response = requests.get(phonepe_url, headers=headers)
            payment_status = response.json()

            if payment_status and payment_status['code'] == "PAYMENT_SUCCESS":
                print(payment_status)
                payment_collection.update_one({'merchantTransactionId': payment_id},{'$set': {'responsePayload': payment_status, 'paymentDone': True}}) 
                payment_record = payment_collection.find_one({'merchantTransactionId': payment_id})
                if not payment_record:
                    return jsonify({'error': 'Payment record not found','status': False}), 404

                company_id = payment_record.get('company')
                plan_id = str(payment_record['contentData']['_id']) 

                company = company_collection.find_one({'company': company_id})
                if not company:
                    return jsonify({'error': 'Company not found','status': False}), 404

                selected_plan = plans_collection.find_one({'_id': ObjectId(plan_id)})
                if not selected_plan:
                    return jsonify({'error': 'Plan not found','status': False}), 404

                expiry_date = datetime.now() + timedelta(days=selected_plan['validity'])
                new_plan_entry = {
                    'status': 'Active',
                    'date_of_purchase': datetime.now().strftime('%Y-%m-%d'),
                    'date_of_expiry': expiry_date.strftime('%Y-%m-%d'),
                    'name': selected_plan['name'],
                    'plan_id': selected_plan['_id'],
                    'cost': selected_plan['cost'],
                    'validity': selected_plan['validity'],
                    'merchantTransactionId': payment_id,
                    'payment_mode': payment_status['data']['paymentInstrument']['type'],
                    'paid': payment_status['data']['amount'] / 100
                }

                company_collection.update_one({'company': company_id}, {'$push': {'plan_list': new_plan_entry}})
                admin = find_admin_info(company['admList'][0])
                html_message = f'''
                <html lang="en">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>Toggle Timer</title>
                    <style>
                        body {{
                            font-family: Arial, sans-serif;
                            margin: 0;
                            padding: 0;
                            background-color: #f9f9f9;
                        }}
                        .container {{
                            max-width: 600px;
                            margin: 20px auto;
                            background-color: #ffffff;
                            padding: 30px;
                            border-radius: 10px;
                            box-shadow: 0 0 20px rgba(0, 0, 0, 0.1);
                        }}
                        .header {{
                            text-align: center;
                            margin-bottom: 30px;
                        }}
                        .plan-details, .company-details, .admin-details {{
                            margin-bottom: 30px;
                        }}
                        .admin-details {{
                            background-color: #f5f5f5;
                            padding: 20px;
                            border-radius: 8px;
                        }}
                        h2, h3 {{
                            color: #333333;
                        }}
                        p {{
                            color: #666666;
                            margin-bottom: 10px;
                        }}
                        .button {{
                            display: inline-block;
                            background-color: #4CAF50;
                            color: white;
                            padding: 10px 20px;
                            text-align: center;
                            text-decoration: none;
                            border-radius: 5px;
                            margin-top: 20px;
                            transition: background-color 0.3s;
                        }}
                        .button:hover {{
                            background-color: #45a049;
                        }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h2>Plan Details</h2>
                        </div>
                        <div class="plan-details">
                            <h3>Plan Information:</h3>
                            <p><strong>Name:</strong> {selected_plan['name']}</p>
                            <p><strong>Maximum Employees:</strong> {selected_plan['maxEmp']}</p>
                            <p><strong>Maximum Admins:</strong> {selected_plan['maxAdm']}</p>
                        </div>
                        <div class="company-details">
                            <h3>Company Information:</h3>
                            <p><strong>Name:</strong> {company['name']}</p>
                            <p><strong>Type:</strong> {company['company_type']}</p>
                            <p><strong>Company Code:</strong> {company['company']}</p>
                            <p><strong>Description:</strong> {company['description']}</p>
                            <p><strong>Phone:</strong> {company['phone']}</p>
                            <p><strong>Address:</strong> {company['address']}</p>
                        </div>
                        <div class="admin-details">
                            <h3>Admin Login Credentials:</h3>
                            <p><strong>Email:</strong> Same As Your Landing Page Email.</p>
                            <p><strong>Password:</strong> Same As Your Landing Page Password.</p>
                        </div>
                        <p style="text-align: center;">Thanks for purchasing!</p>
                        <a href="https://application.toggletimer.com/application" class="button" style="display: block; margin: 0 auto;">Visit Our Website</a>
                    </div>
                </body>
                </html>
                '''

                send_admin_details(html_message, admin['email'], company['email'], "Toggle Timer")
            
                leads_collection.update_one({'email': admin['email']}, {'$set': {'not_lead': True}})
                return jsonify({'message': 'Payment status checked and invoice generated', 'data': payment_status, 'status': True}), 200
            else:
                payment_record = payment_collection.find_one({'merchantTransactionId': payment_id})
                payment_collection.update_one({'merchantTransactionId': payment_id},{'$set': {'responsePayload': payment_status, 'paymentDone': False}}) 
                if payment_record:
                    company_id = payment_record.get('company')
                    company_collection.delete_one({'company': company_id})
                    master_admin_collection.delete_one({'company': company_id})
                return jsonify({'error': 'Payment status check failed', 'status': False}), 400

        except Exception as e:
            return jsonify({'error': str(e),'status': False}), 500
    elif payment_type == 'already':
        try:
            x_verify = x_verify_for_status(payment_id)
            phonepe_url = f"{HOST_URL}{STATUS_ENDPOINT}/{MERCHANT_ID}/{payment_id}"
            headers= {
                'accept': 'application/json',
                'Content-Type': 'application/json',
                "X-MERCHANT-ID": MERCHANT_ID,
                "X-VERIFY": x_verify,
                    }
            response = requests.get(phonepe_url, headers=headers)
            payment_status = response.json()

            if payment_status and payment_status['code'] == "PAYMENT_SUCCESS" :
                payment_collection.update_one({'merchantTransactionId': payment_id},{'$set': {'responsePayload': payment_status, 'paymentDone': True}}) 
                payment_record = payment_collection.find_one({'merchantTransactionId': payment_id}) 
                if not payment_record:
                    return jsonify({'error': 'Payment record not found','status': False}), 404

                payment_record['responsePayload'] = payment_status
                company_id = payment_record.get('company')
                plan_id = str(payment_record['contentData']['_id']) 

                selected_plan = plans_collection.find_one({'_id': ObjectId(plan_id)})
                if not selected_plan:
                    return jsonify({'error': 'Plan not found','status': False}), 404

                # Find the company entry from company_collection
                company = company_collection.find_one({'company': company_id})
                if not company : 
                    return jsonify({'message':'You cannot buy this plan now.'})
                if company is None:
                    return jsonify({'message': 'Company not found!'}), 404

                frontend_timezone = pytz.timezone("Asia/Kolkata")
                frontend_time = datetime.now(frontend_timezone)

                # Check if there's any active plan
                active_plan = next((plan for plan in company['plan_list'] if plan['status'] == 'Active'), None)

                # Calculate the expiry date based on the active plan's expiry date if exists
                if active_plan:
                    latest_plan = max(company['plan_list'], key=lambda plan: datetime.strptime(plan['date_of_expiry'], '%Y-%m-%d'), default=None)
                    expiry_date = datetime.strptime(latest_plan['date_of_expiry'], '%Y-%m-%d') + timedelta(days=selected_plan['validity'])
                else:
                    expiry_date = frontend_time + timedelta(days=selected_plan['validity'])

                # Create the plan entry
                new_plan_entry = {
                    'status': "Active" if not active_plan else "Inactive",
                    'date_of_purchase': datetime.now().strftime('%Y-%m-%d'),
                    'date_of_expiry': expiry_date.strftime('%Y-%m-%d'),
                    'name': selected_plan['name'],
                    'cost': selected_plan['cost'],
                    'plan_id': selected_plan['_id'],
                    'validity': selected_plan['validity'],
                    'merchantTransactionId': payment_id,
                    'payment_mode': payment_status['data']['paymentInstrument']['type'],
                    'paid': payment_status['data']['amount'] / 100                    
                }

                # Append the plan to the plan list of the company
                company['plan_list'].append(new_plan_entry)

                company_collection.update_one({'company': company_id}, {'$set': {'plan_list': company['plan_list']}})

                admin = find_admin_info(company['admList'][0])
                html_message = f'''
                <html lang="en">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>Toggle Timer</title>
                    <style>
                        body {{
                            font-family: Arial, sans-serif;
                            margin: 0;
                            padding: 0;
                            background-color: #f9f9f9;
                        }}
                        .container {{
                            max-width: 600px;
                            margin: 20px auto;
                            background-color: #ffffff;
                            padding: 30px;
                            border-radius: 10px;
                            box-shadow: 0 0 20px rgba(0, 0, 0, 0.1);
                        }}
                        .header {{
                            text-align: center;
                            margin-bottom: 30px;
                        }}
                        .plan-details, .company-details, .admin-details {{
                            margin-bottom: 30px;
                        }}
                        .admin-details {{
                            background-color: #f5f5f5;
                            padding: 20px;
                            border-radius: 8px;
                        }}
                        h2, h3 {{
                            color: #333333;
                        }}
                        p {{
                            color: #666666;
                            margin-bottom: 10px;
                        }}
                        .button {{
                            display: inline-block;
                            background-color: #4CAF50;
                            color: white;
                            padding: 10px 20px;
                            text-align: center;
                            text-decoration: none;
                            border-radius: 5px;
                            margin-top: 20px;
                            transition: background-color 0.3s;
                        }}
                        .button:hover {{
                            background-color: #45a049;
                        }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h2>Plan Details</h2>
                        </div>
                        <div class="plan-details">
                            <h3>Plan Information:</h3>
                            <p><strong>Name:</strong> {selected_plan['name']}</p>
                            <p><strong>Maximum Employees:</strong> {selected_plan['maxEmp']}</p>
                            <p><strong>Maximum Admins:</strong> {selected_plan['maxAdm']}</p>
                        </div>
                        <div class="company-details">
                            <h3>Company Information:</h3>
                            <p><strong>Name:</strong> {company['name']}</p>
                            <p><strong>Type:</strong> {company['company_type']}</p>
                            <p><strong>Company Code:</strong> {company['company']}</p>
                            <p><strong>Description:</strong> {company['description']}</p>
                            <p><strong>Phone:</strong> {company['phone']}</p>
                            <p><strong>Address:</strong> {company['address']}</p>
                        </div>
                        <div class="admin-details">
                            <h3>Admin Login Credentials:</h3>
                            <p><strong>Email:</strong> Same As Your Landing Page Email.</p>
                            <p><strong>Password:</strong> Same As Your Landing Page Password.</p>
                        </div>
                        <p style="text-align: center;">Thanks for purchasing!</p>
                        <a href="https://application.toggletimer.com/application" class="button" style="display: block; margin: 0 auto;">Visit Our Website</a>
                    </div>
                </body>
                </html>
                '''

                send_admin_details(html_message, admin['email'], company['email'], "Toggle Timer")
            
                # leads_collection.delete_one({'email': admin['email']})
                return jsonify({'message': 'Payment status checked and invoice generated', 'data': payment_status, 'status': True}), 200
            else:
                payment_collection.update_one({'merchantTransactionId': payment_id},{'$set': {'responsePayload': payment_status, 'paymentDone': False}}) 
                return jsonify({'error': 'Payment status check failed', 'status': False}), 400

        except Exception as e:
            return jsonify({'error': str(e),'status': False}), 500
    return jsonify({'error': 'Input Valid Payment Type', 'status': False}), 404

# @landing_page_app.route('/api/get_plan', methods=['POST'])
# def get_plan():
#     try:
#         name = request.form.get('name')
#         company_type = request.form.get('company_type')
#         description = request.form.get('description')
#         phone = request.form.get('phone')
#         address = request.form.get('address')
#         time_zone = request.form.get('time_zone', 'Asia/Kolkata')

#         email = request.form.get('company_email')
#         admin_email = request.form.get('admin_email')
#         plan_id = request.form.get('plan')

#         # Fetch user info and check if it exists
#         user_info = leads_collection.find_one({'email': admin_email})
#         if not user_info:
#             return jsonify({'error': 'Use the email you used for login!'}), 404

#         # Handle logo upload
#         if 'logo' in request.files:
#             profile_pic_file = request.files['logo']
#             file_name = f"{email}_{int(datetime.now().timestamp())}.{profile_pic_file.filename.split('.')[-1]}"
#             file_url = upload_to_firebase(profile_pic_file, 'profile_pic', file_name)
#         else:
#             file_url = "https://d1csarkz8obe9u.cloudfront.net/posterpreviews/company-logo-design-template-7c91d15837ad91ad70909087e4a2955d_screen.jpg?ts=1694257442"

#         # Find the selected plan
#         selected_plan = plans_collection.find_one({'_id': ObjectId(plan_id)})
#         if not selected_plan:
#             return jsonify({'message': 'Plan not found!'}), 404

#         # Check if company with the same email already exists and has plans
#         company = company_collection.find_one({'email': email})
#         if company and len(company.get('plan_list', [])) > 0:
#             return jsonify({'error': 'Please buy plan from application'}), 400
#         company_code = generate_new_company_code(company_collection)
#         # Check if admin with this email already exists
#         admin_exists = master_admin_collection.find_one({'email': admin_email})
#         if not admin_exists:
#             new_admin = master_admin_collection.insert_one({
#                 "email": admin_email,
#                 "password": user_info['password'],
#                 "company": company_code,
#                 "profile_pic": "https://th.bing.com/th/id/OIP.EYsBbvQxJK_0DhnzMap0ZAHaHa?rs=1&pid=ImgDetMain"
#             }).inserted_id
#         else:
#             new_admin = admin_exists['_id']

#         # Create new company if it doesn't exist
#         if not company:
#             company_collection.insert_one({
#                 "name": name,
#                 "maxEmp": selected_plan['maxEmp'],
#                 "maxAdm": selected_plan['maxAdm'],
#                 "empList": [],
#                 "admList": [new_admin],
#                 "email": email,
#                 "company": company_code,
#                 "time_zone": time_zone,
#                 "plan_list": [],
#                 "company_type": company_type,
#                 "description": description,
#                 "phone": phone,
#                 "address": address,
#                 "logo": file_url
#             })


#         company = company_collection.find_one({'email': email})
#         if not company:
#             return jsonify({'error': 'Company creation failed!'}), 500

#         amount = 100
#         payload = {
#             'merchantId': MERCHANT_ID,
#             'merchantTransactionId': '',
#             'merchantUserId': f"MUID{user_info['_id']}",
#             'amount': amount,
#             'redirectUrl': "REDIRECT_URL",  # Placeholder for now
#             'redirectMode': "REDIRECT",
#             'mobileNumber': phone,
#             'paymentInstrument': {
#                 'type': "PAY_PAGE"
#             }
#         }

#         payment_body = {
#             'userId': user_info['_id'],
#             'email': user_info['email'],
#             'merchantTransactionId': '',
#             'type': 'initial',
#             'company': company['company'],
#             'contentData': selected_plan,
#             'amount': amount / 100,
#             'paymentPayload': payload
#         }

#         # Insert payment body into payment collection
#         payment_result = payment_collection.insert_one(payment_body)
#         merchant_transaction_id = str(payment_result.inserted_id)

#         # Update merchantTransactionId in the payload and payment_body
#         payload['merchantTransactionId'] = merchant_transaction_id
#         payload['redirectUrl'] = f"{REDIRECT_URL}?merchantTransactionId={merchant_transaction_id}&paymentType=initial"
#         payment_collection.update_one({'_id': payment_result.inserted_id}, {'$set': {'merchantTransactionId': merchant_transaction_id, 'paymentPayload.merchantTransactionId': merchant_transaction_id, 'paymentPayload.redirectUrl': payload['redirectUrl']}})
        
#         base64_payload = base64.b64encode(json.dumps(payload).encode('utf-8')).decode('utf-8')
#         x_verify = generate_x_verify(payload, PAY_ENDPOINT)

#         headers = {
#             'accept': 'application/json',
#             'Content-Type': 'application/json',
#             'X-VERIFY': x_verify,
#         }

#         response = requests.post(f"{HOST_URL}{PAY_ENDPOINT}", headers=headers, json={'request': base64_payload})

#         if response.status_code == 200:
#             response_data = response.json()
#             url = response_data['data']['instrumentResponse']['redirectInfo']['url']

#             return jsonify({'status': True, 'data': url,'merchantTransactionId': merchant_transaction_id, 'msg': 'Payment initiation success'}), 200
#         else:
#             return jsonify({'status': False, 'data': response.json(), 'msg': 'Payment initiation failed'}), 404

#     except Exception as e:
#         return jsonify({'error': str(e)}), 500

@landing_page_app.route('/api/pre_get_plan', methods=['GET'])
def pre_get_plan():
    try:
        email = request.args.get('company_email')
        plan_id = request.args.get('plan')  # plan user is trying to purchase
        type = request.args.get('type')

        if not email or not plan_id:
            return jsonify({'error': 'company_email and plan are required'}), 400

        # Find the selected plan
        selected_plan = plans_collection.find_one({'_id': ObjectId(plan_id)})
        if not selected_plan:
            return jsonify({'message': 'Plan not found!'}), 404

        # Check if the company exists
        company = company_collection.find_one({'email': email})
        if not company:
            return jsonify({'error': 'Company not found'}), 404

        # Check if the company has already purchased the specific trial plan
        trial_plan_id = ObjectId("683679b3d625439aa30a1323")
        for plan in company.get('plan_list', []):
            if plan.get('plan_id') == trial_plan_id:
                return jsonify({'error': 'You have already purchased this plan and your trial is over.'}), 403

        if type == 'get_plan':
            # If company has purchased any other plans
            if len(company.get('plan_list', [])) > 0:
                return jsonify({'error': 'Please buy plan from the application'}), 400

        return jsonify({'message': 'Success!', "code": 200}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@landing_page_app.route('/api/get_plan', methods=['POST'])
def get_plan():
    try:
        name = request.form.get('name')
        company_type = request.form.get('company_type')
        description = request.form.get('description')
        phone = request.form.get('phone')
        address = request.form.get('address')
        time_zone = request.form.get('time_zone', 'Asia/Kolkata')

        email = request.form.get('company_email')
        admin_email = request.form.get('admin_email')
        plan_id = request.form.get('plan')
        transactionId = request.form.get('transactionId','')

        # Fetch user info and check if it exists
        user_info = leads_collection.find_one({'email': admin_email})
        if not user_info:
            return jsonify({'error': 'Use the email you used for login!'}), 404

        update_result = leads_collection.update_one(
            {'email': admin_email},  # Filter
            {'$set': {'lead_type': 2}}  # Update operation
        )

        # Find the selected plan
        selected_plan = plans_collection.find_one({'_id': ObjectId(plan_id)})
        if not selected_plan:
            return jsonify({'message': 'Plan not found!'}), 404

        if selected_plan['cost'] != 0 and 'proof' not in request.files:
            return jsonify({'message': 'Proof not found!'}), 404

        # Handle logo upload
        if 'logo' in request.files:
            profile_pic_file = request.files['logo']
            # file_name = f"{email}_{int(datetime.now().timestamp())}.{profile_pic_file.filename.split('.')[-1]}"
            file_url = upload_to_firebase(profile_pic_file, 'Company_Profile', email)
        else:
            file_url = "https://d1csarkz8obe9u.cloudfront.net/posterpreviews/company-logo-design-template-7c91d15837ad91ad70909087e4a2955d_screen.jpg?ts=1694257442"

        if 'proof' in request.files:
            proof = request.files['proof']
            # file_name = f"{email}_{int(datetime.now().timestamp())}.{proof.filename.split('.')[-1]}"
            proof_url = upload_to_firebase(proof, 'Payment_Proof', email)
        else:
            proof_url = ''


        # Check if company with the same email already exists and has plans
        company = company_collection.find_one({'email': email})
        if company and len(company.get('plan_list', [])) > 0:
            return jsonify({'error': 'Please buy plan from the application'}), 400

#         # Check if admin with this email already exists
        admin_exists = master_admin_collection.find_one({'email': admin_email})
        if admin_exists:
            return jsonify({'error': 'Admin with this email already exists'}), 400

        # Insert company and payment details into payment_requests_collection for admin approval
        payment_request_data = {
            "userId": str(user_info['_id']),
            "email": email,
            "name":name,
            "company_type": company_type,
            "description": description,
            "phone": phone,
            "address": address,
            "time_zone": time_zone,
            "admin_email": admin_email,
            "password": user_info['password'],
            "logo": file_url,
            "contentData": selected_plan,
            "amount": selected_plan['cost'],
            "request_status": "pending",  # Mark as pending for admin approval
            "type":"initial",
            "proof": proof_url,
            "transactionId": transactionId,
            "created_at": datetime.now(),
        }

        # Insert into payment_requests_collection
        payment_request_id = payment_requests_collection.insert_one(payment_request_data).inserted_id
        html_message = f'''
 <html lang="en">
	<head>
	   <meta charset="UTF-8">
	   <meta name="viewport" content="width=device-width, initial-scale=1.0">
	   <title>Account Creation</title>
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
			   padding: 40px 30px 0;
			   text-align: left;
		   }}
		   .message {{
			   font-size: 18px;
			   color: #2c3e50;
			   margin-bottom: 30px;
			   line-height: 1.7;
		   }}
		   .status-container {{
			   background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
			   border: 2px solid #00c9ff;
			   border-radius: 12px;
			   padding: 30px;
			   margin: 30px 0;
			   position: relative;
			   overflow: hidden;
		   }}
		   .status-container::before {{
			   content: '';
			   position: absolute;
			   top: 0;
			   left: 0;
			   right: 0;
			   height: 4px;
			   background: linear-gradient(90deg, #00ff8e 0%, #00c9ff 100%);
		   }}
		   .status-icon {{
			   font-size: 48px;
			   margin-bottom: 15px;
		   }}
		   .status-text {{
			   font-size: 20px;
			   font-weight: 600;
			   color: #00c9ff;
			   margin-bottom: 10px;
		   }}
		   .status-detail {{
			   font-size: 16px;
			   color: #6c757d;
			   margin: 10px 0;
		   }}
		   .timeline {{
			   background-color: #f8f9fa;
			   border-radius: 8px;
			   padding: 20px;
			   margin: 25px 0;
			   border-left: 4px solid #00ff8e;
		   }}
		   .timeline-item {{
			   display: flex;
			   align-items: center;
			   margin: 15px 0;
		   }}
		   .timeline-icon {{
			   width: 30px;
			   height: 30px;
			   background: linear-gradient(90deg, #00ff8e 0%, #00c9ff 100%);
			   border-radius: 50%;
			   display: flex;
			   align-items: center;
			   justify-content: center;
			   margin-right: 15px;
			   color: white;
			   font-weight: 600;
			   font-size: 14px;
		   }}
		   .timeline-text {{
			   color: #555;
			   font-size: 16px;
		   }}
		   .appreciation {{
			   background: linear-gradient(135deg, #e8f5e8 0%, #f0f9ff 100%);
			   border-radius: 12px;
			   padding: 25px;
			   margin: 25px 0;
			   border: 1px solid #00ff8e;
		   }}
		   .appreciation-text {{
			   font-size: 18px;
			   font-weight: 600;
			   color: #00c9ff;
			   margin: 0;
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
			   .status-container {{
				   padding: 20px;
			   }}
			   .status-icon {{
				   font-size: 36px;
			   }}
			   .status-text {{
				   font-size: 18px;
			   }}
		   }}
	   </style>
	</head>
	<body>
	   <div class="email-container">
		   <div class="header">
			   <h1>
	🎉 Account Creation</h1>
			   <p>We're setting up your account</p>
		   </div>
		   <div class="content">
			   <div class="message">
				   We are currently in the process of activating your company profile. You will receive a 
   confirmation email within the next 24 hours once the setup is complete. We're excited to have 
   your company on board and look forward to working with you. If you have any questions in the 
   meantime, feel free to reach out.
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

        send_admin_details(html_message, admin_email, email, "Account Creation")
        return jsonify({'status': True, 'message': 'Payment request submitted successfully, awaiting admin approval', 'requestId': str(payment_request_id)}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@landing_page_app.route('/api/confirm_initial_payment', methods=['POST'])
@token_required_superadmin
def confirm_initial_payment(current_user):
    try:
        # Fetch the payment request details
        data = request.get_json()
        payment_request_id = data.get('paymentId')
        payment_request = payment_requests_collection.find_one({'_id': ObjectId(payment_request_id)})

        if not payment_request:
            return jsonify({'error': 'Payment request not found!'}), 404

        if payment_request['request_status'] != 'pending':
            return jsonify({'error': 'Payment request has already been processed!'}), 400

        # Generate company code at this point after admin confirmation
        company_code = generate_new_company_code(company_collection)

        new_admin = master_admin_collection.insert_one({
            "email": payment_request['admin_email'],
            "password": payment_request['password'],
            "company": company_code,
            "profile_pic": "https://th.bing.com/th/id/OIP.EYsBbvQxJK_0DhnzMap0ZAHaHa?rs=1&pid=ImgDetMain"
        }).inserted_id

        # Add the plan to the company's plan list
        plan_id = str(payment_request['contentData']['_id'])
        selected_plan = plans_collection.find_one({'_id': ObjectId(plan_id)})

        if not selected_plan:
            return jsonify({'error': 'Plan not found', 'status': False}), 404
        created_at = payment_request['created_at']
        if isinstance(created_at, str):
            created_at = parse(created_at)
        elif isinstance(created_at, dict) and '$date' in created_at:
            created_at = parse(created_at['$date'])
        expiry_date = datetime.now() + timedelta(days=int(selected_plan['validity']))
        new_plan_entry = {
            'status': 'Active',
            'date_of_purchase': payment_request['created_at'].strftime('%Y-%m-%d'),
            'date_of_expiry': expiry_date.strftime('%Y-%m-%d'),
            'name': selected_plan['name'],
            'plan_id': selected_plan['_id'],
            'cost': selected_plan['cost'],
            'validity': selected_plan['validity'],
            'payment_mode':"Manual",
            'paid': payment_request['amount']
        }

        company_data = {
            "name": payment_request['name'],
            "maxEmp": payment_request['contentData']['maxEmp'],
            "maxAdm": payment_request['contentData']['maxAdm'],
            "empList": [],
            "admList": [new_admin],
            "email": payment_request['email'],
            "company": company_code,
            "time_zone": payment_request['time_zone'],
            "plan_list": [new_plan_entry],
            "company_type": payment_request['company_type'],
            "description": payment_request['description'],
            "phone": payment_request['phone'],
            "address": payment_request['address'],
            "logo": payment_request['logo'],
        }

        company_id = company_collection.insert_one(company_data).inserted_id
        company = company_collection.find_one({'_id': ObjectId(company_id)})

        # Insert the confirmed payment details into payment_collection
        payment_data = {
            "userId": payment_request['userId'],
            "email": payment_request['email'],
            "type": "initial",  # Mark the type of payment
            "company": company_code,
            "contentData": payment_request['contentData'],
            "amount": payment_request['amount'],
            "proof": payment_request['proof'],
        }

        payment_collection.insert_one(payment_data)

        # Update the payment request as confirmed
        payment_requests_collection.update_one(
            {'_id': ObjectId(payment_request_id)},
            {'$set': {'request_status': 'confirmed', 'confirmed_at': datetime.now()}}
        )
        admin = find_admin_info(company['admList'][0])
        html_message = f'''
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Your Toggle Timer Subscription is Active!</title>
    <style>
        body {{
            margin: 0;
            padding: 0;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #f5f7fa;
            color: #333;
            line-height: 1.6;
        }}
        
        .email-container {{
            max-width: 600px;
            margin: 20px auto;
            background: #ffffff;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #7CE393 0%, #09B9E1 100%);
            padding: 40px 30px;
            text-align: center;
            color: white;
        }}
        
        .header h1 {{
            margin: 0;
            font-size: 28px;
            font-weight: 600;
            text-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
        }}
        
        .welcome-text {{
            font-size: 16px;
            margin: 10px 0 0 0;
            opacity: 0.9;
        }}
        
        .content {{
            padding: 40px 30px;
        }}
        
        .greeting {{
            font-size: 18px;
            color: #2c3e50;
            margin-bottom: 20px;
            font-weight: 500;
        }}
        
        .message {{
            font-size: 16px;
            color: #555;
            margin-bottom: 25px;
        }}
        
        .subscription-info {{
            background: linear-gradient(135deg, #f0fdf4 0%, #e0f7fa 100%);
            border-left: 4px solid #7CE393;
            padding: 20px;
            margin: 25px 0;
            border-radius: 8px;
        }}
        
        .subscription-info h3 {{
            margin: 0 0 15px 0;
            color: #2c3e50;
            font-size: 18px;
        }}
        
        .login-section {{
            background: #fff5f5;
            border-radius: 8px;
            padding: 20px;
            margin: 25px 0;
            border: 1px solid #e2e8f0;
        }}
        
        .login-section h3 {{
            margin: 0 0 15px 0;
            color: #2c3e50;
            font-size: 18px;
        }}
        
        .dashboard-link {{
            background: linear-gradient(135deg, #7CE393 0%, #09B9E1 100%);
            color: white;
            text-decoration: none;
            padding: 12px 25px;
            border-radius: 8px;
            display: inline-block;
            font-weight: 600;
            margin: 10px 0;
            transition: transform 0.2s ease;
        }}
        
        .dashboard-link:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(124, 227, 147, 0.3);
        }}
        
        .credentials {{
            background: #f8f9fa;
            border-radius: 6px;
            padding: 15px;
            margin: 15px 0;
            border: 1px solid #dee2e6;
            font-family: 'Courier New', monospace;
        }}
        
        .credential-item {{
            margin-bottom: 8px;
        }}
        
        .credential-item:last-child {{
            margin-bottom: 0;
        }}
        
        .credential-label {{
            font-weight: 600;
            color: #495057;
            width: 100px;
            display: inline-block;
        }}
        
        .about-section {{
            background: #f8f9ff;
            border-radius: 8px;
            padding: 20px;
            margin: 25px 0;
            border: 1px solid #e9ecef;
        }}
        
        .about-section h3 {{
            margin: 0 0 15px 0;
            color: #2c3e50;
            font-size: 18px;
        }}
        
        .video-link {{
            background: #7CE393;
            color: white;
            text-decoration: none;
            padding: 10px 20px;
            border-radius: 6px;
            display: inline-block;
            font-weight: 500;
            margin: 10px 0;
        }}
        
        .video-link:hover {{
            background: #6BD987;
        }}
        
        .next-steps {{
            background: linear-gradient(135deg, #f0fdf4 0%, #e0f7fa 100%);
            border-radius: 8px;
            padding: 20px;
            margin: 25px 0;
            border-left: 4px solid #09B9E1;
        }}
        
        .next-steps h3 {{
            margin: 0 0 15px 0;
            color: #2c3e50;
            font-size: 18px;
        }}
        
        .steps-list {{
            margin: 15px 0;
            padding-left: 0;
        }}
        
        .step-item {{
            background: white;
            margin: 8px 0;
            padding: 12px 15px;
            border-radius: 6px;
            border-left: 3px solid #7CE393;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        }}
        
        .help-center {{
            text-align: center;
            margin: 25px 0;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
        }}
        
        .help-link {{
            color: #09B9E1;
            text-decoration: none;
            font-weight: 600;
        }}
        
        .help-link:hover {{
            text-decoration: underline;
        }}
        
        .footer {{
            background: #2c3e50;
            color: white;
            text-align: center;
            padding: 30px;
        }}
        
        .footer p {{
            margin: 0;
            font-size: 16px;
            font-weight: 500;
        }}
        
        .company-name {{
            color: #7CE393;
            font-weight: 600;
        }}
        
        /* Responsive design */
        @media (max-width: 600px) {{
            .email-container {{
                margin: 10px;
                border-radius: 8px;
            }}
            
            .header, .content, .footer {{
                padding: 25px 20px;
            }}
            
            .header h1 {{
                font-size: 24px;
            }}
            
            .dashboard-link, .video-link {{
                display: block;
                text-align: center;
                margin: 15px 0;
            }}
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <h1>🎉 Your Subscription is Active!</h1>
            <p class="welcome-text">Welcome to Toggle Timer - Let's boost your productivity</p>
        </div>
        
        <div class="content">
            <div class="greeting">
                Dear {company["name"]},
            </div>
            
            <div class="message">
                I am pleased to inform you that your subscription <strong>{selected_plan["name"]}</strong> is now active.
            </div>
            
            <div class="login-section">
                <h3>🚀 Access Your Dashboard</h3>
                <p>Please login to the company dashboard with the link below:</p>
                <a href="https://application.toggletimer.com/" class="dashboard-link">Access Toggle Timer Dashboard</a>
                
                <p><strong>Here are your login credentials to get started:</strong></p>
                <div class="credentials">
                    <div class="credential-item">
                        <span class="credential-label">Username:</span> {payment_request["admin_email"]}
                    </div>
                    <div class="credential-item">
                        <span class="credential-label">Password:</span> {payment_request["password"]}
                    </div>
                </div>
            </div>
            
            <div class="about-section">
                <h3>Let's get you started! 💪</h3>
                <p>Toggle Timer is a user-friendly time-tracking software designed to streamline workforce management by reducing errors and offering real-time insights. Ideal for businesses of all sizes, it helps track active work, assign prioritized tasks, upload daily reports, and capture key meeting points to keep teams aligned.</p>
                
                <p><strong>Feel free to explore our guided tour for a quick overview:</strong></p>
                <a href="https://firebasestorage.googleapis.com/v0/b/toggletimerr.firebasestorage.app/o/LandingPage%2FToggleTimer_video.mp4?alt=media&token=5778aafc-3652-4bb1-991a-8f6888c34a86" class="video-link">📹 Watch Guided Tour</a>
            </div>
            
            <div class="next-steps">
                <h3>What's next? 📋</h3>
                <p><strong>Steps to start with Toggle Timer:</strong></p>
                <div class="steps-list">
                    <div class="step-item">📱 Downloading the app</div>
                    <div class="step-item">⚙️ Setting up a profile</div>
                    <div class="step-item">👥 Adding team members</div>
                </div>
            </div>
            
            <div class="help-center">
                <p>Feel free to reach out or visit our help center:</p>
                <a href="https://www.toggletimer.com/" class="help-link">Visit Help Center</a>
            </div>
        </div>
        
        <div class="footer">
            <p>Best regards,<br>
            <span class="company-name">Hansraj Ventures Team</span></p>
        </div>
    </div>
</body>
</html>
        '''

        send_admin_details(html_message, admin['email'], company['email'],"Your Toggle Timer Subscription is Active!")
    
        leads_collection.update_one({'email': admin['email']}, {'$set': {'not_lead': True}})
        return jsonify({'status': True, 'message': 'Payment confirmed and company activated'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# @landing_page_app.route('/api/buy_plan', methods=['POST'])
# def buy_plan():
#     data = request.get_json()
#     email = data.get('email')
#     plan_id = data.get('plan')
#     admin_id = data.get('adminId') 
#     user_info = find_admin_info(admin_id)

#     company = company_collection.find_one({'email': email})
#     if not company:
#         return jsonify({'error': 'Company not found!'}), 500

#     # Find the selected plan
#     selected_plan = plans_collection.find_one({'_id': ObjectId(plan_id)})
#     if not selected_plan:
#         return jsonify({'message': 'Plan not found!'}), 404

#     amount = 100
#     payload = {
#         'merchantId': MERCHANT_ID,
#         'merchantTransactionId': '',
#         'merchantUserId': f"MUID{user_info['_id']}",
#         'amount': amount,
#         'redirectUrl': "",  # Placeholder for now
#         'redirectMode': "REDIRECT",
#         'paymentInstrument': {
#             'type': "PAY_PAGE"
#         }
#     }

#     payment_body = {
#         'userId': user_info['_id'],
#         'email': user_info['email'],
#         'merchantTransactionId': '',
#         'type': 'already',
#         'company': user_info['company'],
#         'contentData': selected_plan,
#         'amount': amount / 100,
#         'paymentPayload': payload
#     }

#     # Insert payment body into payment collection
#     payment_result = payment_collection.insert_one(payment_body)
#     merchant_transaction_id = str(payment_result.inserted_id)

#     # Update merchantTransactionId in the payload and payment_body
#     payload['merchantTransactionId'] = merchant_transaction_id
#     payload['redirectUrl'] = f"{REDIRECT_URL}?merchantTransactionId={merchant_transaction_id}&paymentType=already"
#     payment_collection.update_one({'_id': payment_result.inserted_id}, {'$set': {'merchantTransactionId': merchant_transaction_id, 'paymentPayload.merchantTransactionId': merchant_transaction_id, 'paymentPayload.redirectUrl': payload['redirectUrl']}})
    
#     base64_payload = base64.b64encode(json.dumps(payload).encode('utf-8')).decode('utf-8')
#     x_verify = generate_x_verify(payload, PAY_ENDPOINT)

#     headers = {
#         'accept': 'application/json',
#         'Content-Type': 'application/json',
#         'X-VERIFY': x_verify,
#     }

#     response = requests.post(f"{HOST_URL}{PAY_ENDPOINT}", headers=headers, json={'request': base64_payload})

#     if response.status_code == 200:
#         response_data = response.json()
#         url = response_data['data']['instrumentResponse']['redirectInfo']['url']

#         return jsonify({'status': True, 'data': url, 'merchantTransactionId': merchant_transaction_id,'msg': 'Payment initiation success'}), 200
#     else:
#         return jsonify({'status': False, 'data': response.json(), 'msg': 'Payment initiation failed'}), 404


@landing_page_app.route('/api/buy_plan', methods=['POST'])
def buy_plan():
    try:
        email = request.form.get('email')
        plan_id = request.form.get('plan')
        admin_id = request.form.get('adminId')
        transactionId = request.form.get('transactionId','')
        
        # Find admin info
        user_info = find_admin_info(admin_id)
        if not user_info:
            return jsonify({'error': 'Admin not found!'}), 500

        # Check if the company exists
        company = company_collection.find_one({'email': email})
        if not company:
            return jsonify({'error': 'Company not found!'}), 500

        if 'proof' in request.files:
            proof = request.files['proof']
            # file_name = f"{email}_{int(datetime.now().timestamp())}.{proof.filename.split('.')[-1]}"
            proof_url = upload_to_firebase(proof, 'Payment_Proof', email)
        else:
            proof_url = ''

        # Find the selected plan
        selected_plan = plans_collection.find_one({'_id': ObjectId(plan_id)})
        if not selected_plan:
            return jsonify({'message': 'Plan not found!'}), 404

        payment_request_data = {
            'userId': user_info['_id'],
            'email': user_info['email'],
            'type': 'already',
            'company': user_info['company'],
            'contentData': selected_plan,
            'amount': selected_plan['cost'],
            'request_status': 'pending',  # Mark the payment as pending for admin approval
            'proof': proof_url,
            'transactionId': transactionId,
            'created_at': datetime.now()
        }

        # Insert the payment request into payment_requests_collection
        payment_request_result = payment_requests_collection.insert_one(payment_request_data)
        payment_request_id = str(payment_request_result.inserted_id)

        html_message = f'''
 <html lang="en">
	<head>
	   <meta charset="UTF-8">
	   <meta name="viewport" content="width=device-width, initial-scale=1.0">
	   <title>Account Creation</title>
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
			   padding: 40px 30px 0;
			   text-align: left;
		   }}
		   .message {{
			   font-size: 18px;
			   color: #2c3e50;
			   margin-bottom: 30px;
			   line-height: 1.7;
		   }}
		   .status-container {{
			   background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
			   border: 2px solid #00c9ff;
			   border-radius: 12px;
			   padding: 30px;
			   margin: 30px 0;
			   position: relative;
			   overflow: hidden;
		   }}
		   .status-container::before {{
			   content: '';
			   position: absolute;
			   top: 0;
			   left: 0;
			   right: 0;
			   height: 4px;
			   background: linear-gradient(90deg, #00ff8e 0%, #00c9ff 100%);
		   }}
		   .status-icon {{
			   font-size: 48px;
			   margin-bottom: 15px;
		   }}
		   .status-text {{
			   font-size: 20px;
			   font-weight: 600;
			   color: #00c9ff;
			   margin-bottom: 10px;
		   }}
		   .status-detail {{
			   font-size: 16px;
			   color: #6c757d;
			   margin: 10px 0;
		   }}
		   .timeline {{
			   background-color: #f8f9fa;
			   border-radius: 8px;
			   padding: 20px;
			   margin: 25px 0;
			   border-left: 4px solid #00ff8e;
		   }}
		   .timeline-item {{
			   display: flex;
			   align-items: center;
			   margin: 15px 0;
		   }}
		   .timeline-icon {{
			   width: 30px;
			   height: 30px;
			   background: linear-gradient(90deg, #00ff8e 0%, #00c9ff 100%);
			   border-radius: 50%;
			   display: flex;
			   align-items: center;
			   justify-content: center;
			   margin-right: 15px;
			   color: white;
			   font-weight: 600;
			   font-size: 14px;
		   }}
		   .timeline-text {{
			   color: #555;
			   font-size: 16px;
		   }}
		   .appreciation {{
			   background: linear-gradient(135deg, #e8f5e8 0%, #f0f9ff 100%);
			   border-radius: 12px;
			   padding: 25px;
			   margin: 25px 0;
			   border: 1px solid #00ff8e;
		   }}
		   .appreciation-text {{
			   font-size: 18px;
			   font-weight: 600;
			   color: #00c9ff;
			   margin: 0;
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
			   .status-container {{
				   padding: 20px;
			   }}
			   .status-icon {{
				   font-size: 36px;
			   }}
			   .status-text {{
				   font-size: 18px;
			   }}
		   }}
	   </style>
	</head>
	<body>
	   <div class="email-container">
		   <div class="header">
			   <h1>
	🎉 Account Creation</h1>
			   <p>We're setting up your account</p>
		   </div>
		   <div class="content">
			   <div class="message">
				   We are currently in the process of activating your company profile. You will receive a 
   confirmation email within the next 24 hours once the setup is complete. We're excited to have 
   your company on board and look forward to working with you. If you have any questions in the 
   meantime, feel free to reach out.
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

        send_admin_details(html_message, user_info['email'], email,"Account Creation")
        # Return response to indicate that the payment request is submitted
        return jsonify({
            'status': True, 
            'data': {'paymentRequestId': payment_request_id}, 
            'message': 'Payment request created successfully, awaiting admin approval'
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@landing_page_app.route('/api/confirm_already_payment', methods=['POST'])
@token_required_superadmin
def confirm_already_payment(current_user):
    data = request.get_json()
    payment_request = data.get('paymentId')

    # Find payment record
    payment_record = payment_requests_collection.find_one({'_id': ObjectId(payment_request)})
    if not payment_record:
        return jsonify({'message': 'Payment record not found', 'status': False}), 404

    # Get company and plan details
    company_id = payment_record.get('company')
    plan_id = str(payment_record['contentData']['_id']) 

    selected_plan = plans_collection.find_one({'_id': ObjectId(plan_id)})
    if not selected_plan:
        return jsonify({'error': 'Plan not found', 'status': False}), 404

    # Find the company entry
    company = company_collection.find_one({'company': company_id})
    if not company:
        return jsonify({'message': 'Company not found!', 'status': False}), 404

    frontend_timezone = pytz.timezone(current_user.get('time_zone', 'Asia/Kolkata'))
    frontend_time = datetime.now(frontend_timezone)

    # Check if there's any active plan
    active_plan = next((plan for plan in company['plan_list'] if plan['status'] == 'Active'), None)

    # Calculate the expiry date based on the active plan's expiry date if exists
    if active_plan:
        latest_plan = max(company['plan_list'], key=lambda plan: datetime.strptime(plan['date_of_expiry'], '%Y-%m-%d'), default=None)
        expiry_date = datetime.strptime(latest_plan['date_of_expiry'], '%Y-%m-%d') + timedelta(days=selected_plan['validity'])
    else:
        expiry_date = frontend_time + timedelta(days=selected_plan['validity'])

    # Create the plan entry
    new_plan_entry = {
        'status': "Active" if not active_plan else "Inactive",
        'date_of_purchase': datetime.now().strftime('%Y-%m-%d'),
        'date_of_expiry': expiry_date.strftime('%Y-%m-%d'),
        'name': selected_plan['name'],
        'cost': selected_plan['cost'],
        'plan_id': selected_plan['_id'],
        'validity': selected_plan['validity'],
        'payment_mode': 'Manual',
        'paid': payment_record['amount']               
    }

    # Append the plan to the plan list of the company
    company['plan_list'].append(new_plan_entry)

    # Update the company's plan list in the database
    company_collection.update_one({'company': company_id}, {'$set': {'plan_list': company['plan_list']}})

    # Send confirmation email to the admin
    admin = find_admin_info(company['admList'][0])
    html_message = f'''
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Your Toggle Timer Subscription is Active!</title>
    <style>
        body {{
            margin: 0;
            padding: 0;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #f5f7fa;
            color: #333;
            line-height: 1.6;
        }}
        
        .email-container {{
            max-width: 600px;
            margin: 20px auto;
            background: #ffffff;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #7CE393 0%, #09B9E1 100%);
            padding: 40px 30px;
            text-align: center;
            color: white;
        }}
        
        .header h1 {{
            margin: 0;
            font-size: 28px;
            font-weight: 600;
            text-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
        }}
        
        .welcome-text {{
            font-size: 16px;
            margin: 10px 0 0 0;
            opacity: 0.9;
        }}
        
        .content {{
            padding: 40px 30px;
        }}
        
        .greeting {{
            font-size: 18px;
            color: #2c3e50;
            margin-bottom: 20px;
            font-weight: 500;
        }}
        
        .message {{
            font-size: 16px;
            color: #555;
            margin-bottom: 25px;
        }}
        
        .subscription-info {{
            background: linear-gradient(135deg, #f0fdf4 0%, #e0f7fa 100%);
            border-left: 4px solid #7CE393;
            padding: 20px;
            margin: 25px 0;
            border-radius: 8px;
        }}
        
        .subscription-info h3 {{
            margin: 0 0 15px 0;
            color: #2c3e50;
            font-size: 18px;
        }}
        
        .login-section {{
            background: #fff5f5;
            border-radius: 8px;
            padding: 20px;
            margin: 25px 0;
            border: 1px solid #e2e8f0;
        }}
        
        .login-section h3 {{
            margin: 0 0 15px 0;
            color: #2c3e50;
            font-size: 18px;
        }}
        
        .dashboard-link {{
            background: linear-gradient(135deg, #7CE393 0%, #09B9E1 100%);
            color: white;
            text-decoration: none;
            padding: 12px 25px;
            border-radius: 8px;
            display: inline-block;
            font-weight: 600;
            margin: 10px 0;
            transition: transform 0.2s ease;
        }}
        
        .dashboard-link:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(124, 227, 147, 0.3);
        }}
        
        .credentials {{
            background: #f8f9fa;
            border-radius: 6px;
            padding: 15px;
            margin: 15px 0;
            border: 1px solid #dee2e6;
            font-family: 'Courier New', monospace;
        }}
        
        .credential-item {{
            margin-bottom: 8px;
        }}
        
        .credential-item:last-child {{
            margin-bottom: 0;
        }}
        
        .credential-label {{
            font-weight: 600;
            color: #495057;
            width: 100px;
            display: inline-block;
        }}
        
        .about-section {{
            background: #f8f9ff;
            border-radius: 8px;
            padding: 20px;
            margin: 25px 0;
            border: 1px solid #e9ecef;
        }}
        
        .about-section h3 {{
            margin: 0 0 15px 0;
            color: #2c3e50;
            font-size: 18px;
        }}
        
        .video-link {{
            background: #7CE393;
            color: white;
            text-decoration: none;
            padding: 10px 20px;
            border-radius: 6px;
            display: inline-block;
            font-weight: 500;
            margin: 10px 0;
        }}
        
        .video-link:hover {{
            background: #6BD987;
        }}
        
        .next-steps {{
            background: linear-gradient(135deg, #f0fdf4 0%, #e0f7fa 100%);
            border-radius: 8px;
            padding: 20px;
            margin: 25px 0;
            border-left: 4px solid #09B9E1;
        }}
        
        .next-steps h3 {{
            margin: 0 0 15px 0;
            color: #2c3e50;
            font-size: 18px;
        }}
        
        .steps-list {{
            margin: 15px 0;
            padding-left: 0;
        }}
        
        .step-item {{
            background: white;
            margin: 8px 0;
            padding: 12px 15px;
            border-radius: 6px;
            border-left: 3px solid #7CE393;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        }}
        
        .help-center {{
            text-align: center;
            margin: 25px 0;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
        }}
        
        .help-link {{
            color: #09B9E1;
            text-decoration: none;
            font-weight: 600;
        }}
        
        .help-link:hover {{
            text-decoration: underline;
        }}
        
        .footer {{
            background: #2c3e50;
            color: white;
            text-align: center;
            padding: 30px;
        }}
        
        .footer p {{
            margin: 0;
            font-size: 16px;
            font-weight: 500;
        }}
        
        .company-name {{
            color: #7CE393;
            font-weight: 600;
        }}
        
        /* Responsive design */
        @media (max-width: 600px) {{
            .email-container {{
                margin: 10px;
                border-radius: 8px;
            }}
            
            .header, .content, .footer {{
                padding: 25px 20px;
            }}
            
            .header h1 {{
                font-size: 24px;
            }}
            
            .dashboard-link, .video-link {{
                display: block;
                text-align: center;
                margin: 15px 0;
            }}
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <h1>🎉 Your Subscription is Active!</h1>
            <p class="welcome-text">Welcome Back to Toggle Timer - Let's boost your productivity</p>
        </div>
        
        <div class="content">
            <div class="greeting">
                Dear {company["name"]},
            </div>
            
            <div class="message">
                I am pleased to inform you that your subscription <strong>{selected_plan['name']}</strong> is now active.
            </div>
            
            <div class="login-section">
                <h3>🚀 Access Your Dashboard</h3>
                <p>Please login to the company dashboard with the link below:</p>
                <a href="https://application.toggletimer.com/" class="dashboard-link">Access Toggle Timer Dashboard</a>
                <p><strong>The credentials are the same as those you used to log in to the landing page.</strong></p>
            </div>
            
            <div class="about-section">
                <h3>Let's get you started! 💪</h3>
                <p>Toggle Timer is a user-friendly time-tracking software designed to streamline workforce management by reducing errors and offering real-time insights. Ideal for businesses of all sizes, it helps track active work, assign prioritized tasks, upload daily reports, and capture key meeting points to keep teams aligned.</p>
            </div>
            
            <div class="next-steps">
                <h3>What's next? 📋</h3>
                <p><strong>Steps to start with Toggle Timer:</strong></p>
                <div class="steps-list">
                    <div class="step-item">📱 Downloading the app</div>
                    <div class="step-item">⚙️ Setting up a profile</div>
                    <div class="step-item">👥 Adding team members</div>
                </div>
            </div>
            
            <div class="help-center">
                <p>Feel free to reach out or visit our help center:</p>
                <a href="https://www.toggletimer.com/" class="help-link">Visit Help Center</a>
            </div>
        </div>
        
        <div class="footer">
            <p>Best regards,<br>
            <span class="company-name">Hansraj Ventures Team</span></p>
        </div>
    </div>
</body>
</html>
    '''
    send_admin_details(html_message, admin['email'], company['email'],"Your Subscription is Active!")
    payment_requests_collection.update_one(
        {'_id': ObjectId(payment_request)},
        {'$set': {'request_status': 'confirmed', 'confirmed_at': datetime.now()}}
    )
    # Return success message
    return jsonify({'message': 'Payment confirmed and plan activated/added', 'status': True}), 200

@landing_page_app.route('/api/payment_requests', methods=['GET'])
@token_required_superadmin
def get_payment_requests(current_user):
    # Get the filters from query parameters
    request_type = request.args.get('type')
    request_status = request.args.get('request_status')

    # Ensure that the 'type' filter is provided
    if not request_type:
        return jsonify({'message': "'type' filter is required", 'status': False}), 400

    # Build the query based on the filters
    query = {'type': request_type}

    # If 'request_status' is provided, add it to the query
    if request_status:
        query['request_status'] = request_status

    # Fetch the payment requests from the collection in descending order of 'created_at'
    payment_requests = list(payment_requests_collection.find(query).sort('created_at', DESCENDING))

    # Convert MongoDB objects to JSON serializable format if needed
    for payment_request in payment_requests:
        payment_request['_id'] = str(payment_request['_id'])
        payment_request['contentData']['_id'] = str(payment_request['contentData']['_id'])

    return jsonify({
        'message': 'Payment requests fetched successfully',
        'data': payment_requests,
        'status': True
    }), 200

def generate_new_company_code(company_collection):
    # Find the last company document based on the "_id" field in descending order
    last_company = company_collection.find_one({}, sort=[("_id", -1)])

    if last_company:
        last_company_code = last_company["company"]
        # Extract the numeric part of the company code
        code_prefix = last_company_code[:-3]
        code_suffix = int(last_company_code[-3:]) + 1
        new_company_code = f"{code_prefix}{code_suffix:03d}"
    else:
        # If there are no existing companies, start with a default code
        new_company_code = "CM001"

    return new_company_code

def generate_otp(): return str(random.randint(100000, 999999))

@landing_page_app.route('/api/new_signup', methods=['POST'])
def new_signup():
    try:
        # Get user data from request
        data = request.json
        email = data.get('email')

        # Check if email already exists
        if leads_collection.find_one({'email': email}) or company_collection.find_one({'company': email}) or master_admin_collection.find_one({'email': email}):
            return jsonify({'error': 'Email already exists'}), 400

        otp = generate_otp()
        otp_timestamp = datetime.now() + timedelta(minutes=5)

        send_otp_email(otp,email)
        otp_doc = {
            'email': email,
            'otp': otp,
            'otp_timestamp': otp_timestamp
        }
        otps_collection.insert_one(otp_doc)
        return jsonify({'message': f'OTP sent for verification {otp}'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@landing_page_app.route('/api/new_verify_otp', methods=['POST'])
def new_verify_otp():
    data = request.get_json()
    email = data.get('email')
    otp_entered = data.get('otp')
    password = data.get('password')
    name = data.get('name')
    type = data.get('type')

    # Retrieve all documents with matching email from the 'otps' collection
    results = otps_collection.find({'email': email})

    if type == 'Signup':
        for result in results:
            if otp_entered == result['otp']:
                # Check OTP timestamp to validate timeout
                otp_timestamp = result['otp_timestamp']
                current_time = datetime.now()

                if current_time <= otp_timestamp:
                    db['otps'].delete_one({'email': email})
                    lead_id = generate_unique_lead_id()
                    leads_collection.insert_one({'email':email, 'name':name, 'password': generate_password_hash(password), 'lead_id':lead_id, 'datetime': datetime.now(), 'not_lead':False, 'lead_type':1, 'source':'Website'})
                    user_data = leads_collection.find_one({'email': email})
                    _id = str(user_data['_id'])
                    user_data['_id'] = _id
                    user_data['trial_plan'] = "683679b3d625439aa30a1323"
                    user_data['trial_used'] = False
                    admin = master_admin_collection.find_one({'email': email}) 
                    if admin:    
                        company = company_collection.find_one({'company': admin['company']})
                        # Check if the company has already purchased the specific trial plan
                        trial_plan_id = ObjectId("683679b3d625439aa30a1323")
                        for plan in company.get('plan_list', []):
                            if plan.get('plan_id') == trial_plan_id:
                                user_data['trial_used'] = True
                    return jsonify({"message": "Login successful", "details": user_data}), 200

                else:
                    otps_collection.delete_one({'email': email})
                    return jsonify({'message': 'OTP has expired'}), 401
    elif type == 'Login':
        for result in results:
            if otp_entered == result['otp']:
                # Check OTP timestamp to validate timeout
                otp_timestamp = result['otp_timestamp']
                current_time = datetime.now()

                if current_time <= otp_timestamp:
                    db['otps'].delete_one({'email': email})
                
                    # Fetch user
                    user_data = leads_collection.find_one({'email': email})
                    if not user_data:
                        return jsonify({'message': 'User not found'}), 404

                    # Update password if new password is passed
                    if password:
                        leads_collection.update_one(
                            {'email': email},
                            {'$set': {'password': generate_password_hash(password)}}
                        )

                    user_data = leads_collection.find_one({'email': email})
                    user_data['_id'] = str(user_data['_id'])
                    user_data['trial_plan'] = "683679b3d625439aa30a1323"
                    user_data['trial_used'] = False
                    
                    admin = master_admin_collection.find_one({'email': email})
                    if admin: 
                        company = company_collection.find_one({'company': admin['company']})
                        # Check if the company has already purchased the specific trial plan
                        trial_plan_id = ObjectId("683679b3d625439aa30a1323")
                        for plan in company.get('plan_list', []):
                            if plan.get('plan_id') == trial_plan_id:
                                user_data['trial_used'] = True
                    return jsonify({"message": "Login successful", "details": user_data}), 200

                else:
                    otps_collection.delete_one({'email': email})
                    return jsonify({'message': 'OTP has expired'}), 4
    # Invalid OTP or no matching documents found
    return jsonify({'message': 'Invalid OTP'}), 401

@landing_page_app.route('/api/new_login_app', methods=['POST'])
def new_login_app():
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')

        user_data = leads_collection.find_one({'email': email})
        if not user_data:
            return jsonify({'message': 'Invalid email or password'}), 401

        # Validate password
        if not check_password_hash(user_data["password"], password):
            return jsonify({'message': 'Invalid email or password'}), 401

        _id = str(user_data['_id'])
        user_data['_id'] = _id

        user_data['trial_plan'] = "683679b3d625439aa30a1323"
        user_data['trial_used'] = False

        # Check trial status
        admin = master_admin_collection.find_one({'email': email})
        if admin:
            company = company_collection.find_one({'company': admin.get('company')})
            trial_plan_id = ObjectId("683679b3d625439aa30a1323")
            for plan in company.get('plan_list', []):
                if plan.get('plan_id') == trial_plan_id:
                    user_data['trial_used'] = True

        # Generate JWT token
        token_payload = {
            '_id': _id,
            'email': email,
            'lead_id': user_data.get('lead_id'),
            'exp': datetime.utcnow() + timedelta(days=3)  # Token valid for 3 days
        }
        token = jwt.encode(token_payload, SECRET_KEY, algorithm="HS256")

        return jsonify({
            'message': 'Login successful',
            'details': user_data,
            'token': token
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@landing_page_app.route('/api/update_leads_password', methods=['POST'])
@token_required_landing
def update_leads_password(current_user):
    try:
        data = request.json
        email = current_user['email']
        old_password = data.get("password")
        new_password = data.get('newPassword')

        if not email or not old_password or not new_password:
            return jsonify({'message': 'Missing required fields'}), 400

        admin_data = master_admin_collection.find_one({'email': email})
        lead_data  = leads_collection.find_one({'email': email})
        
        # Helper function to check if the password matches
        def verify_password(stored_hash, provided_password):
            return check_password_hash(stored_hash, provided_password) or stored_hash == provided_password

        if admin_data and verify_password(admin_data['password'], old_password):
            result = master_admin_collection.update_one(
                {'email': email},
                {'$set': {'password': generate_password_hash(new_password)}}
            )
        elif lead_data and verify_password(lead_data['password'], old_password):
            result = leads_collection.update_one(
                {'email': email},
                {'$set': {'password': generate_password_hash(new_password)}}
            )
        else:
            return jsonify({'message': 'Invalid email or password'}), 401
        
        if result.modified_count > 0:
            return jsonify({'message': 'Credentials updated successfully'}), 200
        else:
            return jsonify({'message': 'Failed to update credentials'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    

@landing_page_app.route('/api/update_leads', methods=['PUT'])
@token_required_landing
def update_lead_profile(current_user):
    try:
        email = current_user.get('email')
        if not email:
            return jsonify({'error': 'Email not found in user data'}), 400

        name = request.form.get('name')
        file = request.files.get('profile_pic')  # Expected field name from frontend

        update_fields = {}

        if name:
            update_fields['name'] = name

        if file:
            # Upload to Firebase
            profile_pic_url = upload_to_firebase(file, 'Lead_Profile_Pic', email)
            update_fields['profile_pic'] = profile_pic_url

        if not update_fields:
            return jsonify({'error': 'No data to update'}), 400

        result = leads_collection.update_one(
            {'email': email},
            {'$set': update_fields}
        )

        if result.matched_count == 0:
            return jsonify({'error': 'Lead not found'}), 404

        return jsonify({'message': 'Profile updated successfully', 'status': True}), 200

    except Exception as e:
        return jsonify({'error': str(e), 'status': False}), 500


@landing_page_app.route('/api/contact_us_query', methods=['POST'])
def add_query():
    try:
        # Extract data from the request
        email = request.json.get('email')
        message = request.json.get('message')
        name = request.json.get('name')
        phone = request.json.get('phone')
        
        # Validate input data
        if not email or not message:
            return jsonify({"error": "Email and message are required"}), 400
        
        # Current time in user's timezone
        time_zone = 'Asia/Kolkata'
        frontend_timezone = pytz.timezone(time_zone)
        query_time = datetime.now(frontend_timezone)
        
        # Construct query data
        query_data = {
            'email': email,
            'message': message,
            'sender_ip': request.remote_addr,
            'phone': phone,
            'sender':name,
            'submitted_at': query_time
        }
        
        # Insert query data into the queries collection
        result = queries_collection.insert_one(query_data)
        
        if result.inserted_id:
            return jsonify({"message": "Query added successfully", "query_id": str(result.inserted_id)}), 201
        else:
            return jsonify({"error": "Failed to add query"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@landing_page_app.route('/api/contact_us_results', methods=['GET'])
def get_queries():
    try:
        query_id = request.args.get('query_id')  # Fetch by query ID if provided
        email = request.args.get('email')  # Fetch by email if provided
        page = int(request.args.get('page', 1))  # Default to page 1
        page_size = int(request.args.get('page_size', 10))  # Default page size = 10

        if page < 1 or page_size < 1:
            return jsonify({"error": "page and page_size must be positive integers"}), 400

        query_filter = {}
        if query_id:
            try:
                query_filter['_id'] = ObjectId(query_id)
            except Exception:
                return jsonify({"error": "Invalid query_id format"}), 400
        if email:
            query_filter['email'] = email

        # Count total matching records
        total_records = queries_collection.count_documents(query_filter)

        # Fetch paginated queries sorted by submitted_at (newest first)
        queries = (queries_collection.find(query_filter)
                   .sort("submitted_at", -1)
                   .skip((page - 1) * page_size)
                   .limit(page_size))

        result = []
        for query in queries:
            query['_id'] = str(query['_id'])  # Convert ObjectId to string
            query['submitted_at'] = query['submitted_at'].isoformat()  # Format datetime
            result.append(query)

        return jsonify({
            "message": "Queries fetched successfully",
            "total_records": total_records,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_records + page_size - 1) // page_size,  # Calculate total pages
            "data": result
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

@landing_page_app.route('/api/phonepe/health', methods=['GET'])
def phonepe_health_check():
    try:
        # Construct X-VERIFY
        path = f"/v1/pg/merchants/{MERCHANT_ID}/health"
        raw_string = path + API_KEY_VALUE
        sha256_hash = hashlib.sha256(raw_string.encode('utf-8')).hexdigest()
        x_verify = f"{sha256_hash}###${API_KEY_INDEX}"

        url = f"https://uptime.phonepe.com{path}"

        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "X-VERIFY": x_verify
        }

        response = requests.get(url, headers=headers)
        response.raise_for_status()

        return jsonify({
            "status": True,
            "data": response.json()
        }), 200

    except requests.exceptions.HTTPError as http_err:
        return jsonify({
            "status": False,
            "error": f"HTTP error occurred: {str(http_err)}"
        }), 500
    except Exception as err:
        return jsonify({
            "status": False,
            "error": f"Error: {str(err)}"
        }), 500