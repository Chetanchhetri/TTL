from flask import Blueprint, request, jsonify
from socketio_setup import socketio
from bson import ObjectId
import pytz, json
from datetime import datetime,timezone, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

from decorators import token_required_superadmin, details_collection, dropdown_collection, company_collection, plans_collection, leads_collection, monitor_plans, upload_to_firebase, find_admin_info, settings_collection, storage, logins_collection

super_admin_app = Blueprint('super_admin_app',__name__)

@super_admin_app.route('/api/fetch_companies', methods=['GET'])
@token_required_superadmin
def fetch_companies(current_user):
    try:
        filter_type = request.args.get('filter', 'all')

        # Pagination params
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        skip = (page - 1) * limit

        # Fetch all unique plan names
        plan_names = plans_collection.distinct('name')

        companies = []
        leads = []

        # Handle leads1
        if filter_type == 'leads1':
            cursor = leads_collection.find({
                '$and': [
                    {'$or': [{'lead_type': {'$exists': False}}, {'lead_type': 1}]},
                    {'$or': [{'not_lead': {'$exists': False}}, {'not_lead': False}]}
                ]
            }).skip(skip).limit(limit)

            for lead in cursor:
                leads.append({
                    '_id': str(lead['_id']),
                    'name': lead.get('name'),
                    'email': lead.get('email'),
                    'lead_type': lead.get('lead_type'),
                    'source': lead.get('source', ''),
                    'datetime': lead.get('datetime', '')
                })

        # Handle leads2
        elif filter_type == 'leads2':
            cursor = leads_collection.find({
                '$and': [
                    {'lead_type': 2},
                    {'$or': [{'not_lead': {'$exists': False}}, {'not_lead': False}]}
                ]
            }).skip(skip).limit(limit)

            for lead in cursor:
                leads.append({
                    '_id': str(lead['_id']),
                    'name': lead.get('name'),
                    'email': lead.get('email'),
                    'lead_type': lead.get('lead_type'),
                    'source': lead.get('source', ''),
                    'datetime': lead.get('datetime', '')
                })

        # Handle companies
        else:
            cursor = company_collection.find().skip(skip).limit(limit)
            for company in cursor:
                plan_details = None
                active_plan = next((plan for plan in company['plan_list'] if plan['status'] == 'Active'), None)

                if active_plan:
                    plan_details = {
                        'plan_name': active_plan['name'],
                        'date_of_purchase': active_plan['date_of_purchase'],
                        'status': active_plan['status'],
                        'plan_id': str(active_plan['plan_id']),
                        'date_of_expiry': active_plan['date_of_expiry'],
                        'cost': active_plan['cost']
                    }
                elif company['plan_list']:
                    last_plan = company['plan_list'][-1]
                    plan_details = {
                        'plan_name': last_plan['name'],
                        'date_of_purchase': last_plan['date_of_purchase'],
                        'status': last_plan['status'],
                        'plan_id': str(last_plan['plan_id']),
                        'date_of_expiry': last_plan['date_of_expiry'],
                        'cost': last_plan['cost']
                    }

                if plan_details:
                    plan_description = plans_collection.find_one(
                        {'_id': ObjectId(plan_details['plan_id'])},
                        {'_id': 0, 'bio': 1}
                    )

                if filter_type == 'all' or filter_type == '' or (plan_details and filter_type.lower() == plan_details['plan_name'].lower()):
                    companies.append({
                        '_id': str(company['_id']),
                        'name': company['name'],
                        'company': company['company'],
                        'status': 'Active' if monitor_plans(company['company']) else 'Expired',
                        'logo': company['logo'],
                        'email': company['email'],
                        'address': company['address'],
                        'maxEmp': company['maxEmp'],
                        'currEmp': len(company['empList']),
                        'maxAdm': company['maxAdm'],
                        'currAdm': len(company['admList']),
                        'phone': company['phone'],
                        'company_type': company['company_type'],
                        'plan_name': plan_details['plan_name'] if plan_details else None,
                        'plan_description': plan_description['bio'] if plan_description else None,
                        'date_of_purchase': plan_details['date_of_purchase'] if plan_details else None,
                        'date_of_expiry': plan_details['date_of_expiry'] if plan_details else None,
                        'cost': plan_details['cost'] if plan_details else None,
                        'plan_id': plan_details['plan_id'] if plan_details else None,
                    })

        return jsonify({
            'companies': companies,
            'leads': leads,
            'plan_names': plan_names,
            'pagination': {
                'page': page,
                'limit': limit,
                'has_more': len(companies) == limit or len(leads) == limit
            }
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@super_admin_app.route('/api/company_plan_details', methods=['GET'])
@token_required_superadmin
def company_plan_details(current_user):
    company_code = request.args.get('company_code')

    company = company_collection.find_one({'company': company_code})
    if company:
        active_plan = next((plan for plan in company['plan_list'] if plan['status'] == 'Active'), None)
        
        if active_plan:
            if active_plan.get('plan_id') :
                active_plan['plan_id'] = str(active_plan['plan_id'])
            if active_plan.get('_id'):    
                active_plan['_id'] = str(active_plan['_id'])

            plan_id = active_plan.get('plan_id')
            if plan_id:
                plan_details = plans_collection.find_one({'_id': ObjectId(plan_id)}, {'_id': 0})
            else:
                plan_name = active_plan['name']
                plan_details = plans_collection.find_one({'name': plan_name}, {'_id': 0})

            if plan_details:
                return jsonify({
                    '_id': str(company['_id']),
                    'name': company['name'],
                    'status': 'Active' if monitor_plans(company['company']) else 'Expired',
                    'company': company['company'],
                    'logo': company['logo'],
                    'email': company['email'],
                    'password': company['password'] if 'password' in company else '',
                    'address': company['address'],
                    'phone': company['phone'],
                    'company_type': company['company_type'],
                    'description': company['description'],
                    'active_plan': plan_details,
                    'purchase_details': active_plan
                }), 200
            else:
                return jsonify({"error": "Plan details not found"}), 404
        else:
            if company['plan_list']:
                last_plan = company['plan_list'][-1]
                plan_id = last_plan.get('plan_id')
                if plan_id:
                    plan_details = plans_collection.find_one({'_id': ObjectId(plan_id)}, {'_id': 0})
                else:
                    plan_name = last_plan['name']
                    plan_details = plans_collection.find_one({'name': plan_name}, {'_id': 0})

                if plan_details:
                    return jsonify({
                        '_id': str(company['_id']),
                        'name': company['name'],
                        'status': 'Active' if monitor_plans(company['company']) else 'Expired',
                        'company': company['company'],
                        'logo': company['logo'],
                        'email': company['email'],
                        'password': company['password'] if 'password' in company else '',
                        'address': company['address'],
                        'phone': company['phone'],
                        'company_type': company['company_type'],
                        'description': company['description'],
                        'active_plan': plan_details,
                        'purchase_details': last_plan
                    }), 200
                else:
                    return jsonify({"error": "Plan details not found"}), 404
            else:
                return jsonify({"error": "No plans available for this company"}), 404
    else:
        return jsonify({"error": "Company not found"}), 404

@super_admin_app.route('/api/company_all_plans', methods=['GET'])
@token_required_superadmin
def company_all_plans(current_user):
    company_code = request.args.get('company_code')
    filter_type = request.args.get('filter', 'All')  # Default to 'All' if no filter is provided
    page = int(request.args.get('page', 1))  # Default to page 1 if not provided
    per_page = int(request.args.get('per_page', 10))  # Default to 10 items per page

    query = {}  # Base query for companies
    if company_code:
        query['company'] = company_code  # Filter for a specific company if provided

    # companies = company_collection.find(query)
    
    # Pagination
    total_companies = company_collection.count_documents(query)
    total_pages = (total_companies + per_page - 1) // per_page  # Calculate total pages
    companies = company_collection.find(query).skip((page - 1) * per_page).limit(per_page)

    all_companies_plans = []
    for company in companies:
        company_plans = []
        for plan in company.get('plan_list', []):
            plan_id = plan.get('plan_id')
            plan_name = plan.get('name')
            if '_id' in plan:
                plan['_id'] = str(plan['_id'])
            if 'plan_id' in plan:
                plan['plan_id'] = str(plan['plan_id'])
            if plan_id:
                plan_details = plans_collection.find_one({'_id': ObjectId(plan_id)})
            else:
                plan_details = plans_collection.find_one({'name': plan_name})

            if plan_details:
                plan_details['_id'] = str(plan_details.get('_id'))
                plan_id = str(plan_details.get('_id'))
                plan_status = plan.get('status')

                # Apply filters for plan status
                if filter_type == 'Active' and plan_status not in ['Active', 'Inactive']:
                    continue
                if filter_type == 'Expired' and plan_status != 'Expired':
                    continue

                company_plans.append({
                    'plan_id': plan_id,
                    'purchase_details': plan,
                    'plan_details': plan_details
                })

        # Sort the plans in decreasing order of date
        company_plans.sort(key=lambda x: x['purchase_details'].get('date', ''), reverse=True)

        # Append company info and its plans
        all_companies_plans.append({
            'company_details': {
                'email': company.get('email'),
                'name': company.get('name'),
                'company': company.get('company'),
                'logo': company.get('logo')
            },
            'plans': company_plans
        })

    return jsonify({
        'status': True,
        'companies': all_companies_plans,
        'pagination': {
            'current_page': page,
            'total_pages': total_pages,
            'total_companies': total_companies,
            'per_page': per_page
        }
    }), 200


@super_admin_app.route('/api/update_superadmin_password', methods=['POST'])
@token_required_superadmin
def update_superadmin_password(current_user):
    _id = str(current_user['_id'])
    old_password = request.form.get("password")
    admin_data = details_collection.find_one({'_id': ObjectId(_id)})
    new_password = request.form['newPassword']
    if admin_data and check_password_hash(admin_data['password'],old_password):
        result = details_collection.update_one(
            {'_id': ObjectId(_id)},
            {
                '$set': {
                    'password': generate_password_hash(new_password)
                }
            }
        )
    else:
        return jsonify({'message':'Wrong password'})
    if result.modified_count > 0:
        return jsonify({'message': 'Credentials updated successfully'})
    else:
        return jsonify({'message': 'Failed to update credentials'})


@super_admin_app.route('/api/update_SA_profile_pic',methods=['POST'])
@token_required_superadmin
def update_SA_profile_pic(current_user):
    _id = str(current_user['_id'])
    image = request.files.get("image")
    if not image:
        return jsonify({'message':'Nothing Happened'})
    url = upload_to_firebase(image,'SuperAdmin_Profile_Pic',str(_id))
    admin_data = details_collection.find_one({'_id': ObjectId(_id)})
    if admin_data:
        result = details_collection.update_one(
            {'_id': ObjectId(_id)},
            {
                '$set': {
                    'profile_pic': url
                }
            }
        )
    else:
        return jsonify({'message':'Admin not found'})    
    if result.modified_count > 0:
        return jsonify({'message': 'Credentials updated successfully'})
    else:
        return jsonify({'message': 'Failed to update credentials'})        


@super_admin_app.route('/api/update_superadmin_details', methods=['POST'])
@token_required_superadmin
def update_superadmin_details(current_user):
    if request.method == 'POST':
        data = request.get_json() 
        
        if data.get("_id"):
            _id = data.get("_id")
        else:
            _id = str(current_user["_id"])
        
        name = data.get("name")
        new_username = data.get("username")
        email = data.get("email")
        phone = data.get("phone")
        language = data.get("language")
        dob = data.get("dob")
        country = data.get("country")
        city = data.get("city")
        bio = data.get("bio")
        address = data.get("address")
        department = data.get("department")

        user_to_update = details_collection.find_one({'_id':ObjectId(_id)})

        if new_username:  user_to_update['username'] = new_username       
        if name: user_to_update['name'] = name
        if email: user_to_update['email'] = email
        if phone: user_to_update['phone'] = phone
        if language: user_to_update['language'] = language.split(",")
        if dob: user_to_update['dob'] = dob
        if country: user_to_update['country'] = country
        if city: user_to_update['city'] = city
        if bio: user_to_update['bio'] = bio
        if address: user_to_update['address'] = address
        if department: user_to_update['department'] = department.split(",")

        # Perform the update operation
        details_collection.update_one({'_id':ObjectId(_id)}, {"$set": user_to_update})

        return jsonify({'message': 'Admin data updated successfully'})
    return jsonify({"message":"Something went wrong"})

@super_admin_app.route('/api/all_plans', methods=['GET'])
@token_required_superadmin
def get_plans(current_user):
    filter_option = request.args.get('filter')

    projection = {'_id': 0}  # Exclude the _id field from the returned documents

    plans_count = {}
    for plan in plans_collection.find({}, projection):
        plan_name = plan['name']
        plans_count[plan_name] = 0  # Initialize the count to 0 for each plan

    # Update the count based on the plan_list in company_collection
    companies = company_collection.find({})
    for company in companies:
        for plan_entry in company['plan_list']:
            plan_name = plan_entry['name']
            if plan_name in plans_count:
                plans_count[plan_name] += 1

    if filter_option == 'specified':
        plans = list(plans_collection.find({
            'specified': {'$exists': True},
            '$expr': {'$gt': [{'$size': '$specified'}, 0]}
        }, projection))
    elif filter_option == 'not_specified':
        plans = list(plans_collection.find({
            '$or': [
                {'specified': {'$exists': False}},
                {'specified': {'$size': 0}}
            ]
        }, projection))
    else:
        plans = list(plans_collection.find({}, projection))

    # Append the plans_count information to each plan
    for plan in plans:
        plan_name = plan['name']
        plan_details = None
        if 'plan_id' in plan:
            plan_details = plans_collection.find_one({'_id': ObjectId(plan['plan_id'])})
        else:
            plan_details = plans_collection.find_one({'name': plan_name})
            if plan_details:
                plan['plan_id'] = str(plan_details.get('_id'))

        if plan_details:
            plan['bought_count'] = plans_count.get(plan_name, 0)

    return jsonify(plans), 200


@super_admin_app.route('/api/add_plan', methods=['POST'])
@token_required_superadmin
def add_plan(current_user):
    new_plan_data = request.json

    # Insert the new plan into the plans collection
    result = plans_collection.insert_one(new_plan_data)

    if result.inserted_id:
        return jsonify({"message": "Plan added successfully", "plan_id": str(result.inserted_id)}), 201
    else:
        return jsonify({"error": "Failed to add plan"}), 500

@super_admin_app.route('/api/delete_plan', methods=['DELETE'])
@token_required_superadmin
def delete_plan(current_user):
    try:
        # Get the plan_id from the request data
        plan_id = request.json.get('plan_id')

        if not plan_id:
            return jsonify({"error": "Plan ID is required"}), 400

        # Check if the plan is active in any company's plan_list
        active_plan = company_collection.find_one(
            {'plan_list.plan_id': ObjectId(plan_id), 'plan_list.status': 'Active'}
        )
        
        if active_plan:
            return jsonify({"error": "Cannot delete plan. The plan is currently active in at least one company."}), 400
        
        # Proceed to delete the plan from the plans collection
        result = plans_collection.delete_one({'_id': ObjectId(plan_id)})

        if result.deleted_count == 1:
            return jsonify({"message": "Plan deleted successfully"}), 200
        else:
            return jsonify({"error": "Plan not found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@super_admin_app.route('/api/edit_plan', methods=['PUT'])
@token_required_superadmin
def edit_plan(current_user):
    try:
        plan_id = request.json.get('_id')
        if not plan_id:
            return jsonify({'error': 'Plan _id is required'}), 400

        updated_plan_data = request.json

        # Convert necessary fields to int safely
        for key in ['cost', 'maxEmp', 'maxAdm', 'validity']:
            if key in updated_plan_data:
                try:
                    updated_plan_data[key] = int(updated_plan_data[key])
                except ValueError:
                    return jsonify({'error': f'{key} must be an integer'}), 400

        # Remove _id from data to be updated
        updated_plan_data.pop('_id', None)

        result = plans_collection.update_one({'_id': ObjectId(plan_id)}, {'$set': updated_plan_data})

        if result.modified_count > 0:
            return jsonify({"message": "Plan updated successfully", "plan": updated_plan_data}), 200
        else:
            return jsonify({"error": "Failed to update plan"}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@super_admin_app.route('/api/get_plan_dropdown', methods=['GET'])
@token_required_superadmin
def get_plan_dropdown(current_user):
    features = list(dropdown_collection.find({"_id":ObjectId("683d428d1304834fc48ec1ea")}, {"_id":0,"features":1}))
    return jsonify({"data":features,"status":200}), 200

@super_admin_app.route('/api/edit_plan_dropdown', methods=['POST'])
@token_required_superadmin
def edit_plan_dropdown(current_user):
    updated_dropdown_data = request.json

    # Trim extra spaces from each feature string
    if 'features' in updated_dropdown_data and isinstance(updated_dropdown_data['features'], list):
        updated_dropdown_data['features'] = [feature.strip() for feature in updated_dropdown_data['features'] if isinstance(feature, str)]

    # Update the plan in the plans collection based on the plan name
    result = dropdown_collection.update_one(
        {'_id': ObjectId("683d428d1304834fc48ec1ea")},
        {'$set': updated_dropdown_data}
    )


    if result.modified_count > 0:
        return jsonify({"message": "Drop Down updated successfully","plan":updated_dropdown_data}), 200
    else:
        return jsonify({"error": "Failed to update plan"}), 404

@super_admin_app.route('/api/add_emp_department', methods=['POST'])
def create_department():
    # Retrieve form-data inputs
    email = request.form.get('email')
    password = request.form.get('password')
    address = request.form.get('address','')
    bio = request.form.get('bio','')
    city = request.form.get('city','')
    country = request.form.get('country','')
    dob = request.form.get('dob','')
    language = request.form.get('language','')
    name = request.form.get('name')
    phone = request.form.get('phone')
    username = request.form.get('username')
    department = request.form.get('department')

    # check user already exist
    existing_user = details_collection.find_one({'email': email})
    if existing_user:
        return jsonify({"error": "User already exists with this email"}), 400


    # Check if 'profile_pic' is in the request.files
    if 'profile_pic' in request.files:
        profile_pic_file = request.files['profile_pic']
        # Generate a unique filename for the profile pic using the employee's email and current timestamp
        # file_name = f"{email}_{int(datetime.now().timestamp())}.{profile_pic_file.filename.split('.')[-1]}"
        # Upload the profile pic to S3 and get the file URL
        file_url = upload_to_firebase(profile_pic_file,'Department',name)
    else:
        file_url = "https://th.bing.com/th/id/OIP.EYsBbvQxJK_0DhnzMap0ZAHaHa?rs=1&pid=ImgDetMain"

    # Check required fields
    if not all([email, password, country, dob, language, name, phone, username]):
        return jsonify({'status': False, 'message': 'All fields are required.'}), 400

    # Create the department document
    department_data = {
        'email': email,
        'password': generate_password_hash(password),
        'address': address,
        'bio': bio,
        'city': city,
        'country': country,
        'dob': dob,
        'language': language.split(','),
        'name': name,
        'phone': phone,
        'username': username,
        'profile_pic': file_url,
        'department': department.split(','),
        'blocked': False,
        'created_at': datetime.now(),
    }

    # Insert the department document into the departments_collection
    department_id = details_collection.insert_one(department_data).inserted_id

    return jsonify({
        'status': True,
        'message': 'Department created successfully.',
        'data': str(department_id)
    }), 201

@super_admin_app.route('/api/block_super_admin', methods=['POST'])
def block_super_admin():
    data = request.get_json()
    _id = data.get('_id')
    block_action = data.get('block')  # Boolean: True to block, False to unblock

    # Check if email and block_action are provided
    if not _id or block_action is None:
        return jsonify({"status": False, "message": "Email and block action are required"}), 400

    # Find the super admin user by email
    user = details_collection.find_one({'_id': ObjectId(_id)})
    if not user:
        return jsonify({"status": False, "message": "User not found"}), 404

    # Update the user's blocked status
    details_collection.update_one(
        {'_id': ObjectId(_id)},
        {'$set': {'blocked': block_action}}
    )

    status_message = "blocked" if block_action else "unblocked"
    return jsonify({
        "status": True,
        "message": f"User {status_message} successfully",
        "data": {
            "blocked": block_action
        }
    }), 200


@super_admin_app.route('/api/update_settings', methods=['POST'])
@token_required_superadmin
def update_settings(current_user):
    try:
        user_id = str(current_user["_id"])
        settings_data = request.json

        if not isinstance(settings_data, dict):
            return jsonify({"status": "error", "message": "Invalid settings format"}), 400

        # Create new dict for insertion with ObjectId and timestamp
        db_entry = dict(settings_data)
        db_entry["user_id"] = ObjectId(user_id)
        db_entry["timestamp"] = datetime.utcnow()

        # Insert into database
        settings_collection.insert_one(db_entry)

        # Prepare safe response data
        response_data = dict(settings_data)
        response_data["user_id"] = user_id
        response_data["timestamp"] = db_entry["timestamp"].isoformat()

        socketio.emit('settings_updated', response_data, namespace='/socket_connection')

        return jsonify({
            "status": "success",
            "message": "Settings updated",
            "data": response_data
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@super_admin_app.route('/api/upload_exe', methods=['POST'])
@token_required_superadmin
def upload_exe(current_user):
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400

        file = request.files['file']
        type = request.form.get('type')

        if type not in ["window", "mac"]:
            return jsonify({'error': 'Invalid type'}), 400
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400

        # Only allow .exe files
        # if not file.filename.endswith('.exe'):
        #     return jsonify({'error': 'Only .exe files are allowed'}), 400

        if type == "window":
            # Always upload to the same Firebase path so it replaces the old file
            firebase_path = 'executables/latest_release.exe'
        elif type == "mac":
            # Always upload to the same Firebase path so it replaces the old file
            firebase_path = 'executables/latest_release_mac.app'

        # Upload the file (overwrite old one)
        storage.child(firebase_path).put(file)

        # Get the public URL
        url = storage.child(firebase_path).get_url(None)

        return jsonify({'message': 'Upload successful', 'url': url}), 200

    except Exception as e:
        return jsonify({'error': f'Failed to upload .exe: {str(e)}'}), 500

@super_admin_app.route('/api/company/mark-deleted', methods=['PUT'])
@token_required_superadmin
def mark_company_deleted(current_user):
    try:
        company = request.json.get('company')
        if not company:
            return jsonify({'error': 'Company not found in user data'}), 400

        result = company_collection.update_one(
            {'company': company},
            {'$set': {'deleted': True}}
        )

        if result.matched_count == 0:
            return jsonify({'error': 'Company not found in database'}), 404

        return jsonify({'message': f'Company {company} marked as deleted', 'status': True}), 200

    except Exception as e:
        return jsonify({'error': str(e), 'status': False}), 500

@super_admin_app.route("/api/login-history", methods=["GET"])
@token_required_superadmin
def get_login_history():
    try:
        user_id = request.args.get("userID")
        if not user_id:
            return jsonify({"message": "Missing userID parameter"}), 400

        result = logins_collection.find_one(
            {"userID": ObjectId(user_id)},
            {"logins": {"$slice": 5}, "_id": 0, "userID": 0}
        )

        if not result or not result.get("logins"):
            return jsonify({"message": "No login history found", "logins": []}), 404

        return jsonify({"logins": result["logins"]}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@super_admin_app.route("/api/company-logins", methods=["GET"])
@token_required_superadmin
def get_company_logins(current_user):
    try:
        company_code = request.args.get("company")
        if not company_code:
            return jsonify({"message": "Missing 'company' parameter"}), 400

        # Find all login documents where type != "user"
        cursor = logins_collection.find(
            {
                "company": company_code,
                "type": {"$ne": "user"}
            },
            {
                "_id": 0,
                "logins": {"$slice": 5},  # only fetch the most recent login
                "userID": 1,
                "company": 1,
                "type": 1
            }
        )

        results = []
        for doc in cursor:
            doc['userID'] = str(doc['userID'])  # Convert ObjectId to string
            results.append(doc)

        if not results:
            return jsonify({"message": "No admin/supervisor login records found"}), 404

        return jsonify({"data": results}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@socketio.on('get_settings', namespace='/socket_connection')
def get_settings(event):
    settings = settings_collection.find_one(sort=[("timestamp", -1)])

    if not settings:
        socketio.emit('settings_updated', {"error": "No settings found"}, namespace='/socket_connection')
        return

    # Create a copy and serialize
    serialized_settings = dict(settings)
    serialized_settings["timestamp"] = serialized_settings["timestamp"].isoformat()
    serialized_settings["user_id"] = str(serialized_settings["user_id"])
    serialized_settings["_id"] = str(serialized_settings["_id"])
    socketio.emit('settings_updated', serialized_settings, namespace='/socket_connection')

@socketio.on('dev_listening',namespace='/socket_connection')
def dev_listening(event):
    for user in event.get('users',[]):
        socketio.emit(f'dev_listening_{user}',event.get('data',{}),namespace='/socket_connection')

@socketio.on('get_company_counts',namespace='/socket_connection')
def get_company_counts(event):

    total_company_count = company_collection.count_documents({})

    free_trial_company_count = 0
    paid_company_count = 0

    companies = company_collection.find({})
    for company in companies:
        if 'plan_list' in company and len(company['plan_list']) > 0:
            last_plan = company['plan_list'][-1]
            if last_plan['status'] in ['Active', 'Inactive']:
                if last_plan['cost'] == 0:
                    free_trial_company_count += 1
                else:
                    paid_company_count += 1
    
    socketio.emit('company_counts',{'total_companies':total_company_count, 'free_trial':free_trial_company_count, 'paid_subs':paid_company_count},namespace = '/socket_connection')