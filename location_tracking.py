import os
import requests
from flask import Blueprint, request, jsonify
from datetime import datetime
# Authentication removed, just importing the database collection
from decorators import collection 

location_tracking_app = Blueprint('location_tracking_app', __name__)
db = collection.database 

@location_tracking_app.route('/api/log_location', methods=['POST'])
def log_location():
    data = request.json
    
    # Extract data directly from the JSON body since there is no token
    lat = data.get('latitude')
    lng = data.get('longitude')
    employee_id = data.get('employee_id')
    company = data.get('company')

    if lat is None or lng is None or not employee_id or not company:
        return jsonify({"error": "latitude, longitude, employee_id, and company are required"}), 400

    # 1. Google Maps Reverse Geocoding
    api_key = os.getenv('Google_maps_API')
    address = "Address not found"
    
    if api_key:
        gmaps_url = f"https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lng}&key={api_key}"
        try:
            response = requests.get(gmaps_url)
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'OK' and len(result.get('results', [])) > 0:
                    # Grab the most accurate human-readable address
                    address = result['results'][0]['formatted_address']
        except Exception as e:
            print(f"Google Maps API Error: {str(e)}")

    # 2. Prepare database entry
    today_str = datetime.utcnow().strftime('%Y-%m-%d')
    current_time = datetime.utcnow().strftime('%H:%M:%S')

    location_point = {
        "time": current_time,
        "lat": lat,
        "lng": lng,
        "address": address  # Saving the Google Maps address
    }

    # 3. Save to MongoDB
    db.employee_locations.update_one(
        {
            "employee_id": employee_id,
            "company": company,
            "date": today_str
        },
        {
            "$push": {"route": location_point}
        },
        upsert=True
    )

    return jsonify({
        "message": "Location logged successfully", 
        "address_saved": address,
        "status": True
    }), 200