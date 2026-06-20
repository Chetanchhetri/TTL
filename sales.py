from flask import Blueprint, request, jsonify
from socketio_setup import socketio
from bson import ObjectId
import pandas as pd
from datetime import datetime,timezone, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import pytz
from decorators import token_required_superadmin, details_collection, master_admin_collection, company_collection, plans_collection, leads_collection, generate_unique_lead_id

sales_app = Blueprint('sales_app',__name__)


@sales_app.route('/api/converted_clients', methods=['GET'])
@token_required_superadmin
def get_converted_clients(current_user):
    # Define pagination parameters
    page = int(request.args.get('page', 1))  # Default to page 1 if not provided
    per_page = int(request.args.get('per_page', 10))  # Default to 10 items per page

    # Initialize list to hold the converted client companies
    converted_clients = []

    # Step 1: Iterate through each master admin email and check if it exists in leads_collection
    for master_admin in master_admin_collection.find({}, {'email': 1, 'company': 1}):
        master_email = master_admin.get('email')
        
        # Check if this email is in leads_collection
        lead_entry = leads_collection.find_one({'email': master_email})
        
        if lead_entry:
            # Step 2: Get the company code and fetch details from company_collection
            company_code = master_admin.get('company')
            company_details = company_collection.find_one({'company': company_code})

            if company_details:
                # Get the last plan in the plan_list, if plan_list is not empty
                plan_list = company_details.get('plan_list', [])
                last_plan = plan_list[-1] if plan_list else None
                last_plan['plan_id'] = str(last_plan.get('plan_id'))
                
                if last_plan:
                    # Append company and last plan details along with datetime from leads_collection
                    converted_clients.append({
                        'company_details': {
                            'name': company_details.get('name'),
                            'email': company_details.get('email'),
                            'company': company_details.get('company'),
                            'logo': company_details.get('logo'),
                            'company_code': company_code
                        },
                        'last_plan': last_plan,
                        'lead_conversion_date': lead_entry.get('datetime')
                    })

    # Step 3: Sort the converted clients by datetime in descending order
    converted_clients.sort(key=lambda x: x['lead_conversion_date'], reverse=True)

    # Step 4: Implement pagination
    total_clients = len(converted_clients)
    total_pages = (total_clients + per_page - 1) // per_page
    paginated_clients = converted_clients[(page - 1) * per_page: page * per_page]

    # Return response with paginated converted clients
    return jsonify({
        'status': True,
        'data': paginated_clients,
        'pagination': {
            'current_page': page,
            'total_pages': total_pages,
            'total_clients': total_clients,
            'per_page': per_page
        }
    }), 200

@sales_app.route('/api/assign_lead', methods=['POST'])
def assign_lead():
    # Retrieve lead_id and admin_id from request data
    lead_id = request.json.get('lead_id')
    admin_id = request.json.get('admin_id')
    
    # Validate input
    if not lead_id or not admin_id:
        return jsonify({'status': False, 'message': 'Both lead_id and admin_id are required.'}), 400

    # Ensure lead_id and admin_id are valid ObjectIds
    try:
        lead_id = ObjectId(lead_id)
        admin_id = ObjectId(admin_id)
    except Exception as e:
        return jsonify({'status': False, 'message': 'Invalid lead_id or admin_id format.'}), 400

    # Find the lead
    lead = leads_collection.find_one({'_id': lead_id})
    if not lead:
        return jsonify({'status': False, 'message': 'Lead not found.'}), 404
    # Check if lead_id already exists in the admin's leads_list
    admin_details = details_collection.find_one({'_id': admin_id})
    if admin_details and any(lead['lead_id'] == lead_id for lead in admin_details.get('leads_list', [])):
        return jsonify({'status': False, 'message': 'Lead already assigned to this admin.'}), 400

    # Append to the 'sales_admins' list, creating it if necessary
    assignment_entry = {
        'lead_id': lead_id,
        'follow_up_level':'',
        'last_contact':'',
        'next_contact':'',
        'priority':'',
        'status':'',
        'source':lead.get('source', ''),
        'email':lead.get('email', ''),
        'assigned_date': datetime.now()
    }
    
    # Update the lead document in the leads_collection
    details_collection.update_one(
        {'_id': admin_id},
        {'$push': {'leads_list': assignment_entry}}
    )

    return jsonify({
        'status': True,
        'message': 'Lead assigned to sales admin successfully.',
        'data': {
            'lead_id': str(lead_id),
            'admin_id': str(admin_id),
            'assigned_date': assignment_entry['assigned_date']
        }
    }), 200

@sales_app.route('/api/add_lead', methods=['POST'])
@token_required_superadmin
def add_lead(current_user):
    # Retrieve lead name and email from request data
    lead_name = request.json.get('lead_name')
    lead_email = request.json.get('lead_email')

    # Validate input
    if not lead_name or not lead_email:
        return jsonify({'status': False, 'message': 'Both lead name and email are required.'}), 400

    # Check if a lead with the same email already exists
    existing_lead = leads_collection.find_one({'email': lead_email})
    if existing_lead:
        return jsonify({'status': False, 'message': 'A lead with this email already exists.'}), 409

    lead_id = generate_unique_lead_id()
    # Prepare lead data to be inserted
    lead_data = {
        'lead_id': lead_id,
        'name': lead_name,
        'email': lead_email,
        'source':'Manual',
        'added_by': ObjectId(current_user['_id']),
        'datetime': datetime.now(),
        'sales_admins': [],  # Initialize with an empty list for future assignments,
        'not_lead': False
    }

    # Insert the new lead into the leads_collection
    lead_id = leads_collection.insert_one(lead_data).inserted_id

    return jsonify({
        'status': True,
        'message': 'Lead added successfully.',
        'data': {
            'lead_id': str(lead_id),
            'name': lead_name,
            'email': lead_email,
            'datetime': lead_data['datetime']
        }
    }), 201


@sales_app.route('/api/update_lead', methods=['POST'])
@token_required_superadmin
def update_lead(current_user):
    # Retrieve input data from request
    lead_id = request.json.get('lead_id')
    admin_id = request.json.get('admin_id')
    potential_plan = request.json.get('potential_plan', {})
    call_msg_email = request.json.get('call_msg_email', '')
    num_calls = request.json.get('num_calls', 0)
    followups = request.json.get('followups', [])
    status = request.json.get('status', '')
    comment = request.json.get('comment', '')
    priority = request.json.get('priority', '')
    email = request.json.get('email', '')

    # Validate input
    if not lead_id:
        return jsonify({'status': False, 'message': 'Lead ID is required.'}), 400
    if not admin_id:
        return jsonify({'status': False, 'message': 'Admin ID is required.'}), 400

    # Update the lead in the leads_list of the details_collection
    result = details_collection.update_one(
        {
            '_id': ObjectId(admin_id),
            'leads_list.lead_id': ObjectId(lead_id)
        },
        {
            '$set': {
                f'leads_list.$.potential_plan': potential_plan,
                f'leads_list.$.call_msg_email': call_msg_email,
                f'leads_list.$.num_calls': num_calls,
                f'leads_list.$.followups': followups,
                f'leads_list.$.status': status,
                f'leads_list.$.comment': comment,
                f'leads_list.$.priority': priority,
                f'leads_list.$.email': email
            }
        }
    )

    # Check if the lead was found and updated
    if result.matched_count == 0:
        return jsonify({'status': False, 'message': 'Lead not found or no changes made.'}), 404

    # If the status is "failed", update the not_lead field in the leads_collection
    if status.lower() == "failed":
        leads_collection.update_one(
            {'_id': ObjectId(lead_id)},
            {'$set': {'not_lead': True}}
        )

    return jsonify({'status': True, 'message': 'Lead updated successfully.'}), 200


@sales_app.route('/api/fetch_leads', methods=['GET'])
@token_required_superadmin
def fetch_leads(current_user):
    # Pagination parameters
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))
    unassigned_only = request.args.get('unassigned_only', 'false').lower() == 'true'

    # Calculate the number of skips for pagination
    skips = (page - 1) * per_page

    if unassigned_only:
        # Step 1: Gather all lead IDs assigned to admins
        assigned_lead_ids = set()
        admins = details_collection.find({}, {'leads_list.lead_id': 1})
        for admin in admins:
            leads_list = admin.get('leads_list', [])
            for lead in leads_list:
                assigned_lead_ids.add(lead['lead_id'])

        # Step 2: Fetch unassigned leads from leads_collection
        unassigned_leads = leads_collection.find(
            {
                '_id': {'$nin': list(assigned_lead_ids)},
                '$or': [
                    {'not_lead': {'$exists': False}},  # Field not present
                    {'not_lead': False}               # Field explicitly set to False
                ]
            }
        ).sort('datetime', -1).skip(skips).limit(per_page)

        # Step 3: Construct the response data
        unassigned_leads_list = []
        for lead in unassigned_leads:
            unassigned_leads_list.append({
                'lead_id': str(lead['_id']),
                'name': lead.get('name', ''),
                'email': lead.get('email', ''),
                'datetime': lead.get('datetime'),
                'not_lead': lead.get('not_lead', False),
                'source': lead.get('source', '')
            })

        # Get total count of unassigned leads for pagination
        total_unassigned_leads = leads_collection.count_documents(
            {'_id': {'$nin': list(assigned_lead_ids)}}
        )
        total_pages = (total_unassigned_leads + per_page - 1) // per_page

        return jsonify({
            'status': True,
            'data': unassigned_leads_list,
            'total_pages': total_pages,
            'current_page': page,
            'total_leads': total_unassigned_leads
        }), 200
    else:
        # Fetch all leads from all admins with pagination
        admins = details_collection.find().skip(skips).limit(per_page)
        leads_with_admin = []

        for admin in admins:
            admin_name = admin.get('name')
            admin_id = str(admin.get('_id'))

            # Check if leads_list exists and iterate through it
            if 'leads_list' in admin:
                for lead in admin['leads_list']:
                    lead_details = {
                        'lead_id': str(lead['lead_id']),
                        'follow_up_level': lead.get('follow_up_level', ''),
                        'last_contact': lead.get('last_contact', ''),
                        'next_contact': lead.get('next_contact', ''),
                        'priority': lead.get('priority', ''),
                        'status': lead.get('status', ''),
                        'assigned_date': lead.get('assigned_date'),
                        'admin_name': admin_name,
                        'admin_id': admin_id
                    }
                    leads_with_admin.append(lead_details)

        # Sort leads in decreasing order of assigned_date
        leads_with_admin.sort(key=lambda x: x['assigned_date'], reverse=True)

        # Get total leads count for pagination
        total_leads = sum(len(admin.get('leads_list', [])) for admin in details_collection.find())
        total_pages = (total_leads + per_page - 1) // per_page  # Calculate total pages

        return jsonify({
            'status': True,
            'data': leads_with_admin,
            'total_pages': total_pages,
            'current_page': page,
            'total_leads': total_leads
        }), 200

@sales_app.route('/api/admin_leads_summary', methods=['GET'])
@token_required_superadmin
def admin_leads_summary(current_user):
    # Initialize response list
    admin_leads_summary = []

    # Iterate through each admin in details_collection
    # check if 'leads_list' is present in admin document
    admins = details_collection.find({'leads_list': {'$exists': True}})
    for admin in admins:
        admin_id = admin['_id']
        admin_name = admin.get('name', 'Unknown Admin')
        admin_pic = admin.get('profile_pic', '')
        total_leads = 0
        current_leads = 0
        completed_leads = 0
        leads_added_by_admin = 0
        detailed_leads = []  # To store detailed lead info

        # Check if 'leads_list' is present in the admin document
        leads_list = admin.get('leads_list', [])

        # Calculate current, completed, and total leads
        for lead_entry in leads_list:
            lead_id = lead_entry.get('lead_id')
            lead_status = lead_entry.get('status', '').lower()

            # Fetch detailed lead information from leads_collection
            lead_details = leads_collection.find_one({'_id': lead_id})
            if lead_details:
                detailed_leads.append({
                    'lead_id': str(lead_id),
                    'name': lead_details.get('name', 'Unknown'),
                    'email': lead_details.get('email', 'Unknown'),
                    'status': lead_status,
                    'priority': lead_entry.get('priority', ''),
                    'last_contact': lead_entry.get('last_contact', ''),
                    'next_contact': lead_entry.get('next_contact', ''),
                    'assigned_date': lead_entry.get('assigned_date', ''),
                    'source': lead_details.get('source', 'Unknown'),
                })

            # Update lead counts
            total_leads += 1
            if lead_status == 'completed':
                completed_leads += 1
            elif lead_status not in ('completed', 'failed'):
                current_leads += 1

        # Calculate leads added by admin in leads_collection
        leads_added_by_admin = leads_collection.count_documents({'added_by': ObjectId(admin_id)})

        # Append the summary for this admin to the response list
        admin_leads_summary.append({
            'admin_id': str(admin_id),
            'admin_name': admin_name,
            'admin_pic': admin_pic,
            'total_leads': total_leads,
            'current_leads': current_leads,
            'completed_leads': completed_leads,
            'leads_added_by_admin': leads_added_by_admin,
            'detailed_leads': detailed_leads
        })

    return jsonify({
        'status': True,
        'data': admin_leads_summary
    }), 200

@sales_app.route('/api/all_leads', methods=['GET'])
@token_required_superadmin
def get_paginated_leads(current_user):
    try:
        # Get page and limit from query parameters
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 25))

        if page < 1 or limit < 1:
            return jsonify({'message': 'Page and limit must be greater than 0'}), 400

        skip = (page - 1) * limit

        # Query leads ordered by datetime descending
        cursor = leads_collection.find().sort('datetime', -1).skip(skip).limit(limit)

        leads = []
        for doc in cursor:
            datetime_value = doc.get("datetime")
            leads.append({
                "_id": str(doc["_id"]),
                "email": doc.get("email"),
                "name": doc.get("name"),
                "lead_id": doc.get("lead_id"),
                "datetime": datetime_value.strftime('%Y-%m-%d %H:%M:%S') if datetime_value else None,
                "not_lead": doc.get("not_lead", False),
                "lead_type": doc.get("lead_type"),
                "source": doc.get("source")
            })

        total = leads_collection.count_documents({})
        total_pages = (total + limit - 1) // limit  # Ceiling division

        return jsonify({
            "page": page,
            "limit": limit,
            "total_leads": total,
            "total_pages": total_pages,
            "data": leads
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@sales_app.route('/api/add_leads_from_sheet', methods=['POST'])
@token_required_superadmin
def add_leads_from_sheet(current_user):
    try:
        # Check if a file is uploaded
        if 'file' not in request.files:
            return jsonify({'status': False, 'message': 'No file provided'}), 400

        file = request.files['file']

        # Read the Excel file into a DataFrame
        try:
            df = pd.read_excel(file)
        except Exception as e:
            return jsonify({'status': False, 'message': f'Error reading Excel file: {str(e)}'}), 400

        # Validate required columns
        required_columns = [
            "Country", "State", "City", "Category of Business", "Name", "Address", "Phone", "Email",
            "Call/Msg/Email", "No. of Time of Calling", "FollowUp 1", "FollowUp 2", 
            "FollowUp 3", "FollowUp 4", "FollowUp 5", "Status", "Comment", "Priority", 
            "AdminName"
        ]
        if not all(col in df.columns for col in required_columns):
            return jsonify({'status': False, 'message': 'Missing required columns in Excel file'}), 400

        # Extract admin ID from token
        admin_id = current_user['_id']

        added_leads = []  # To track successfully added leads
        failed_leads = []  # To track rows with issues

        # Iterate over rows in the DataFrame
        for index, row in df.iterrows():
            try:
                # Extract data from the row
                country = str(row["Country"]).strip()
                state = str(row["State"]).strip()
                city = str(row["City"]).strip()
                category = str(row["Category of Business"]).strip()
                name = str(row["Name"]).strip()
                address = str(row["Address"]).strip()
                phone = str(row["Phone"]).strip()
                email = str(row["Email"]).strip()
                call_msg_email = str(row["Call/Msg/Email"]).strip()
                num_calls = int(row["No. of Time of Calling"]) if not pd.isnull(row["No. of Time of Calling"]) else 0
                followups = [
                    str(row[col]).strip() for col in ["FollowUp 1", "FollowUp 2", "FollowUp 3", "FollowUp 4", "FollowUp 5"]
                    if not pd.isnull(row[col]) and str(row[col]).strip() != ""
                ]
                status = str(row["Status"]).strip()
                comment = str(row["Comment"]).strip()
                priority = str(row["Priority"]).strip()
                admin_name = str(row["AdminName"]).strip()

                # Check if the lead already exists by email
                existing_lead = leads_collection.find_one({'email': email})
                existing_in_admin = details_collection.find_one({'leads_list.email': email})
                existing_in_company = master_admin_collection.find_one({'email': email})

                if existing_lead or existing_in_admin or existing_in_company :
                    failed_leads.append({'row': index + 1, 'error': 'Lead with this email already exists'})
                    continue

                # Generate a unique lead ID
                lead_code = generate_unique_lead_id()

                # Insert data into the leads collection
                lead_data = {
                    'lead_id': lead_code,
                    'country': country,
                    'state': state,
                    'city': city,
                    'category': category,
                    'name': name,
                    'address': address,
                    'phone': phone,
                    'email': email,
                    'not_lead': False,
                    'password': None,
                    'datetime': datetime.now(),
                    'source': 'Manual',
                    'addedBy': ObjectId(admin_id),
                }
                lead_id = leads_collection.insert_one(lead_data).inserted_id

                # If AdminName is provided, assign the lead to the admin
                if admin_name:
                    # Check if the admin exists in the details_collection
                    admin = details_collection.find_one({'name': admin_name.strip()})
                    if admin:
                        lead_assignment = {
                            'lead_id': ObjectId(lead_id),
                            'leadId': lead_code,
                            'source': 'Manual',
                            'assigned_date': datetime.now(),
                            'call_msg_email': call_msg_email,
                            'num_calls': num_calls,
                            'followups': followups,
                            'status': status,
                            'comment': comment,
                            'priority': priority,
                            'email': email
                        }

                        # Append the lead assignment to the admin's leads_list
                        details_collection.update_one(
                            {'_id': admin['_id']},
                            {'$push': {'leads_list': lead_assignment}}
                        )

                # Track successfully added lead
                added_leads.append({
                    'lead_id': str(lead_id),
                    'lead_code': lead_code,
                    'name': name,
                    'email': email
                })

            except Exception as e:
                # Log the row that caused the failure and the reason
                failed_leads.append({'row': index + 1, 'error': str(e)})

        return jsonify({
            'status': True,
            'message': 'Leads processed successfully',
            'added_leads': added_leads,
            'failed_leads': failed_leads
        }), 200

    except Exception as e:
        return jsonify({'status': False, 'message': f'Error occurred: {str(e)}'}), 500
