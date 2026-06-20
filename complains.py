from flask import Blueprint, request, jsonify
from datetime import datetime
from bson import ObjectId
from math import ceil
import re

from decorators import token_required, complains_collection, token_required_superadmin, collection, master_admin_collection, company_collection

complains_app = Blueprint('complains_app', __name__)

@complains_app.route('/api/complain', methods=['POST'])
@token_required
def add_complain(current_user):
    try:
        user_id = str(current_user['_id'])
        company = current_user['company']
        data = request.json
        version = data.get("version")
        complain = data.get("complain")
        user_type = "user"

        company_details = company_collection.find_one({"company": company}, {"name": 1})
        if not company_details:
            return jsonify({"error": "Company not found"}), 404

        user = collection.find_one({'_id': ObjectId(user_id)}, {'name': 1, 'profile_pic': 1, 'employee_id': 1,  '_id':1})
        if not user:
            user = master_admin_collection.find_one({'_id': ObjectId(user_id)}, {'name': 1, 'profile_pic': 1,'email':1,'_id':1})
            if not user: return jsonify({"error": "User not found"}), 404
            user_type = "admin"

        name = user.get('name', '-')
        emp_id = user.get('employee_id', '-')

        if not user_id  or not version or not complain:
            return jsonify({"error": "Missing required fields"}), 400

        # Create complaint document
        complain_doc = {
            "user_id": user_id,
            "company_name": company_details.get('name'),
            "name": name,
            "version": version,
            "company": company,
            "complain": complain,
            "user_type": user_type,
            "emp_id": emp_id,
            "status": "pending",
            "created_at": datetime.now()
        }

        # Insert into MongoDB
        complains_collection.insert_one(complain_doc)

        return jsonify({"message": "Complain submitted successfully", "status": True}), 201

    except Exception as e:
        return jsonify({"error": str(e), "status": False}), 500


@complains_app.route('/api/allComplains', methods=['GET'])
@token_required_superadmin
def get_complains(current_user):
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        skip = (page - 1) * limit

        company = request.args.get('company')
        emp_id = request.args.get('emp_id')
        status = request.args.get('status')  # pending, resolved, etc.
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        search = request.args.get('search')  # search on companyName or name

        query = {}

        if company:
            query["company"] = company
        if emp_id:
            query["emp_id"] = emp_id
        if status:
            query["status"] = status
        if start_date and end_date:
            query["created_at"] = {
                "$gte": datetime.strptime(start_date, "%Y-%m-%d"),
                "$lte": datetime.strptime(end_date, "%Y-%m-%d")
            }
        if search:
            regex = re.compile(f".*{re.escape(search)}.*", re.IGNORECASE)
            query["$or"] = [
                {"company_name": regex},
                {"name": regex}
            ]

        total_count = complains_collection.count_documents(query)
        total_pages = ceil(total_count / limit)

        complains_cursor = complains_collection.find(query)\
            .sort("created_at", -1)\
            .skip(skip)\
            .limit(limit)

        complains_list = [
            {
                "id": str(complain["_id"]),
                "user_id": complain.get("user_id"),
                "name": complain.get("name"),
                "user_type": complain.get("user_type"),
                "emp_id": complain.get("emp_id"),
                "version": complain.get("version"),
                "complain": complain.get("complain"),
                "status": complain.get("status"),
                "company_name": complain.get("company_name"),
                "created_at": complain.get("created_at").isoformat() if complain.get("created_at") else None
            }
            for complain in complains_cursor
        ]

        return jsonify({
            "complains": complains_list,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
            "total_count": total_count
        }), 200

    except Exception as e:
        return jsonify({"error": str(e), "status": False}), 500


@complains_app.route('/api/complain/<complain_id>', methods=['DELETE'])
@token_required_superadmin
def delete_complain(current_user, complain_id):
    try:

        # Find the complain document
        complain = complains_collection.find_one({'_id': ObjectId(complain_id)})

        if not complain:
            return jsonify({'error': 'Complain not found'}), 404

        # Delete the complain
        complains_collection.delete_one({'_id': ObjectId(complain_id)})

        return jsonify({'message': 'Complain deleted successfully', 'status': True}), 200

    except Exception as e:
        return jsonify({'error': str(e), 'status': False}), 500
