from flask import Blueprint, request, send_file, jsonify
from bson import ObjectId
import pdfkit, tempfile, os, requests, pytz
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors, utils
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle,PageBreak,Spacer, Image
from PIL import Image as PILImage
from datetime import datetime, timedelta

from decorators import collection, company_collection, process_time_entry, upload_report_firebase, token_required_admin

report_app = Blueprint('report_app',__name__)


# config = pdfkit.configuration(wkhtmltopdf=r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe')

# @report_app.route('/api/generate_report', methods=['POST'])
# def generate_report():
#     data = request.get_json()

#     employee_id = str(data.get('employee_id'))
#     start_date = data.get('start_date')
#     end_date = data.get('end_date')

#     # Query the database for relevant entries
#     entries = collection.find_one({
#         "_id": ObjectId(employee_id),
#         "time_tracking": {
#             "$elemMatch": {
#                 "date": {"$gte": start_date, "$lte": end_date}
#             }
#         }
#     })

#     # Fetch employee details from user_collection
#     employee_details = collection.find_one({"_id": ObjectId(employee_id)})

#     # Prepare the table rows for the report
#     table_rows = ""
#     time_tracking_data = entries.get('time_tracking', [])
#     filtered_data = [data for data in time_tracking_data if start_date <= data.get('date') <= end_date]
#     sorted_data = sorted(filtered_data, key=lambda x: x.get('date'))

#     for time_entry in sorted_data:
#         date = time_entry.get('date')
#         start_time = time_entry.get('start_time')
#         end_time = time_entry.get('end_time', '23:59:59')
#         elapsed_time = time_entry.get('elapsed_time', '00:00:00')
#         call_time = time_entry.get('call_time', '00:00:00')
#         total_elapsed_time = time_entry.get('total_elapsed_time', '00:00:00')

#         if start_time:
#             start_time_1 = datetime.strptime(start_time, '%H:%M:%S')
#         else:
#             start_time_1 = datetime.strptime('00:00:00', '%H:%M:%S')

#         if end_time:
#             end_time_1 = datetime.strptime(end_time, '%H:%M:%S')
#         else:
#             end_time_1 = datetime.strptime('00:00:00', '%H:%M:%S')

#         if total_elapsed_time:
#             total_elapsed_time_1 = datetime.strptime(total_elapsed_time, '%H:%M:%S') - datetime.strptime('00:00:00', '%H:%M:%S')
#         else:
#             total_elapsed_time_1 = timedelta(0)

#         if start_time:
#             inactive_time = format_time(max(0,(end_time_1 - start_time_1 - total_elapsed_time_1).total_seconds()))

#         response_details = None
#         for response_entry in time_tracking_data:
#             entry_date_str = response_entry.get('date', '')
#             if entry_date_str == date:
#                 response_details = response_entry
#                 break

#         if response_details:
#             response_values = [value for key, value in response_details.items() if key.startswith("Response")]
#             miss_count = sum(1 for val in response_values if isinstance(val, str) and "Missed" in val)

#             total_response = len(response_values) - 1
#             hit_confirmation = max(0, total_response - miss_count)
#         else:
#             total_response = 0
#             hit_confirmation = 0

#         table_rows += f"""
#         <tr>
#             <td>{date}</td>
#             <td>{find_day(date)}</td>
#             <td>{start_time}</td>
#             <td>{end_time}</td>
#             <td>{elapsed_time}</td>
#             <td>{call_time}</td>
#             <td>{inactive_time}</td>
#             <td>{total_elapsed_time}</td>
#             <td>{hit_confirmation}</td>
#             <td>{total_response}</td>
#         </tr>
#         """

#     # Prepare HTML content with embedded CSS
#     html_content = f"""
#     <!DOCTYPE html>
#     <html lang="en">
#         <head>
#             <meta charset="UTF-8" />
#             <meta name="viewport" content="width=device-width, initial-scale=1.0" />
#             <title>Toggle Timer Report</title>
#             <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css" />
#             <link rel="preconnect" href="https://fonts.googleapis.com" />
#             <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
#             <link
#                 href="https://fonts.googleapis.com/css2?family=Poppins:ital,wght@0,100;0,200;0,300;0,400;0,500;0,600;0,700;0,800;0,900;1,100;1,200;1,300;1,400;1,500;1,600;1,700;1,800;1,900&display=swap"
#                 rel="stylesheet" />
#             <link
#                 href="https://fonts.googleapis.com/css2?family=Montserrat:ital,wght@0,100..900;1,100..900&display=swap"
#                 rel="stylesheet" />
#             <link
#                 href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,100..1000;1,9..40,100..1000&display=swap"
#                 rel="stylesheet" />
# 		<style>
# 			body {{
# 				font-family: Arial, sans-serif;
# 				background-color: #f5f5f5;
# 				&::-webkit-scrollbar {{
# 					display: none;
#                 }}
# 			}}
# 			* {{
# 				margin: 0;
# 				padding: 0;
# 				box-sizing: border-box;
# 			}}
# 			.container {{
# 				max-width: 100vw;
# 				margin: 0;
# 				background-color: #fff;
# 				padding: 2rem;
# 				box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
# 				overflow: hidden;
# 				min-height: 100vh;
# 			}}

# 			h1 {{
# 				color: #666;
# 				font-family: Montserrat;
# 				font-size: 2.25925rem;
# 				font-style: normal;
# 				font-weight: 600;
# 				line-height: 100%; /* 3.38888rem */
# 				letter-spacing: 0.2485rem;
# 				text-transform: uppercase;

# 				span {{
# 					background: var(--Frame-3, linear-gradient(90deg, #94fd9e 0%, #00c9ff 100%, #00c9ff 100%));
# 					background-clip: text;
# 					-webkit-background-clip: text;
# 					-webkit-text-fill-color: transparent;
# 				}}
# 			}}
# 			.header {{
# 				display: flex;
# 				align-items: center;
# 				gap: 2rem;
# 				border-bottom: 2px solid #eee;
# 				height: 11.125rem;

# 				svg {{
# 					width: 4.8125rem;
# 					height: 3.63769rem;
# 				}}
# 				.CompanyDetails {{
# 					display: flex;
# 					flex-direction: column;
# 					gap: 0.42rem;

# 					p {{
# 						color: #666;
# 						font-family: Montserrat;
# 						font-size: 1.07456rem;
# 						font-style: normal;
# 						font-weight: 500;
# 						line-height: 150%; /* 1.61188rem */
# 						letter-spacing: 0.13969rem;
# 						text-transform: uppercase;
# 					}}
# 				}}
# 			}}

# 			.profile {{
# 				display: flex;
# 				align-items: center;
# 				margin-top: 20px;
# 				flex-wrap: wrap;
# 				padding-right: 5rem;
# 				img {{
# 					border-radius: 50%;
# 					width: 9.04544rem;
# 					aspect-ratio: 1/1;
# 					border-radius: 50%;
# 					margin-right: 20px;
# 				}}
# 			}}
# 			.profile-info {{
# 				display: flex;
# 				flex-direction: column;
# 				gap: 0.82rem;

# 				h2 {{
# 					color: #333;
# 					font-family: Poppins;
# 					font-size: 2.15531rem;
# 					font-style: normal;
# 					font-weight: 600;
# 					line-height: normal;
# 				}}
# 				h3 {{
# 					color: #828385;
# 					font-family: Poppins;
# 					font-size: 1.272rem;
# 					font-style: normal;
# 					font-weight: 500;
# 					line-height: normal;
# 				}}
# 				p {{
# 					width: 22.61319rem;
# 					color: rgba(0, 0, 0, 0.7);
# 					font-family: "DM Sans";
# 					font-size: 0.848rem;
# 					font-style: normal;
# 					font-weight: 700;
# 					line-height: 124%; /* 1.0515rem */
# 				}}
# 			}}

# 			.contact-info {{
# 				margin-left: auto;
# 				display: flex;
# 				gap: 3rem;
# 				flex-wrap: wrap;
# 				.EmailPhoneWrapper {{
# 					display: flex;
# 					flex-direction: column;
# 					gap: 1rem;
# 					.TextCol {{
# 						display: flex;
# 						align-items: center;
# 						gap: 1rem;
# 					}}
# 				}}
# 			}}

# 			.Description {{
# 				width: 100%;
# 				min-height: 7.3125rem;
# 				padding: 1rem;
# 				p {{
# 					color: #000;
# 					font-family: "DM Sans";
# 					font-size: 1rem;
# 					font-style: normal;
# 					font-weight: 400;
# 					line-height: 150%; /* 1.5rem */
# 					margin-bottom: 1rem;
# 				}}

# 				/* white-space: pre-line; */
# 			}}
# 			.report-title {{
# 				color: #000;
# 				font-family: Montserrat;
# 				font-size: 2.25rem;
# 				font-style: normal;
# 				font-weight: 500;
# 				line-height: 1.25rem; /* 55.556% */
# 				letter-spacing: 0.00625rem;
# 				text-align: center;
# 				padding: 2rem;
# 			}}
# 			.table-container {{
# 				overflow-x: auto;
# 			}}
# 			table {{
# 				width: 100%;
# 				border-collapse: collapse;
# 				margin-top: 20px;
# 				table-layout: fixed;
# 			}}
# 			table,
# 			th,
# 			td {{
# 				border: 1px solid #ddd;
# 			}}
# 			th,
# 			td {{
# 				padding: 12px;
# 				text-align: center;
# 				word-wrap: break-word;
# 			}}
# 			th {{
# 				background-color: #f4f4f4;
# 				color: var(--Shade-6, #222);
# 				/* Subtitle/Subtitle 2 */
# 				font-family: "DM Sans";
# 				font-size: 0.875rem;
# 				font-style: normal;
# 				font-weight: 700;
# 				line-height: 1.25rem; /* 142.857% */
# 				letter-spacing: 0.00625rem;
# 			}}
# 			td {{
# 				color: #333;
# 				font-family: "DM Sans";
# 				font-size: 0.875rem;
# 				font-style: normal;
# 				font-weight: 400;
# 				line-height: 1.25rem; /* 142.857% */
# 				letter-spacing: 0.00625rem;
# 			}}
# 		</style>
#         </head>
#         <body>
#             <div class="container">
#                 <div class="header">
#                     <svg xmlns="http://www.w3.org/2000/svg" width="77" height="59" viewBox="0 0 77 59" fill="none">
#                         <path d="M0 8.62643C0 3.9118 3.82196 0.0898438 8.53658 0.0898438H35.6903V33.8618H18.9167V17.163H8.53659C3.82196 17.163 0 13.341 0 8.62643Z" fill="url(#paint0_linear_112_63)" />
#                         <path d="M0 50.7483C0 46.0337 3.82196 42.2118 8.53658 42.2118H8.91743V50.7483H0V50.7483Z" fill="url(#paint1_linear_112_63)" />
#                         <path d="M42.1182 50.7483C42.1182 46.0337 45.9401 42.2118 50.6547 42.2118H76.3896V50.7483H42.1182Z" fill="url(#paint2_linear_112_63)" />
#                         <path d="M8.91743 50.7483C8.91743 46.0337 12.7394 42.2118 17.4539 42.2118H24.5077C29.2223 42.2118 33.0443 46.0337 33.0443 50.7483V58.9903H8.91743V50.7483Z" fill="url(#paint3_linear_112_63)" />
#                         <path d="M43.0965 8.62643C43.0965 3.9118 46.9185 0.0898438 51.6331 0.0898438H68.7853C73.4999 0.0898438 77.3218 3.9118 77.3218 8.62643V33.8618H43.0965V8.62643Z" fill="url(#paint4_linear_112_63)" />
#                         <defs>
#                             <linearGradient id="paint0_linear_112_63" x1="43.7205" y1="-38.4485" x2="-41.4234" y2="-22.7177" gradientUnits="userSpaceOnUse">
#                                 <stop stop-color="#00C9FF" />
#                                 <stop offset="1" stop-color="#94FD9E" />
#                             </linearGradient>
#                             <linearGradient id="paint1_linear_112_63" x1="9.33292" y1="43.1318" x2="0.166587" y2="45.5466" gradientUnits="userSpaceOnUse">
#                                 <stop stop-color="#00C9FF" />
#                                 <stop offset="1" stop-color="#94FD9E" />
#                             </linearGradient>
#                             <linearGradient id="paint2_linear_112_63" x1="75.7794" y1="49.8273" x2="50.3694" y2="58.5396" gradientUnits="userSpaceOnUse">
#                                 <stop stop-color="#00C9FF" />
#                                 <stop offset="1" stop-color="#94FD9E" />
#                             </linearGradient>
#                             <linearGradient id="paint3_linear_112_63" x1="32.4337" y1="41.7648" x2="-3.29761" y2="58.8181" gradientUnits="userSpaceOnUse">
#                                 <stop stop-color="#00C9FF" />
#                                 <stop offset="1" stop-color="#94FD9E" />
#                             </linearGradient>
#                             <linearGradient id="paint4_linear_112_63" x1="77.3218" y1="0.0898438" x2="36.8981" y2="23.6546" gradientUnits="userSpaceOnUse">
#                                 <stop stop-color="#00C9FF" />
#                                 <stop offset="1" stop-color="#94FD9E" />
#                             </linearGradient>
#                         </defs>
#                     </svg>
# 				<div class="CompanyDetails">
# 					<h1>toggle <span>timer</span></h1>
# 					<p>Product Of HANSRAJ VENTURES</p>
# 				</div>
#                 </div>
#                 <div class="profile">
#                     <img src="{employee_details.get('profile_pic')}" alt="Profile Picture" />
#                     <div class="profile-info">
#                         <h2>{employee_details.get('name')}</h2>
#                         <h3>{employee_details.get('job')}</h3>
#                         <p>{employee_details.get('bio')}</p>
#                     </div>
#                     <div class="contact-info">
#                         <div class="EmailPhoneWrapper">
#                             <div class="TextCol">
#                                 <i class="fas fa-envelope"></i>
#                                 <span>{employee_details.get('email')}</span>
#                             </div>
#                             <div class="TextCol">
#                                 <i class="fas fa-phone-alt"></i>
#                                 <span>{employee_details.get('phone')}</span>
#                             </div>
#                         </div>
#                         <div>
#                             <i class="fas fa-mars"></i>
#                             <span>{employee_details.get('gender')}</span>
#                         </div>
#                     </div>
#                 </div>
#                 <h3>Toggle Timer Report ({start_date} - {end_date})</h3>
#                 <div class="table-container">
#                     <table>
#                         <thead>
#                             <tr>
#                                 <th>Date</th>
#                                 <th>Day</th>
#                                 <th>Start Time</th>
#                                 <th>End Time</th>
#                                 <th>Elapsed Time</th>
#                                 <th>Call Time</th>
#                                 <th>Inactive Time</th>
#                                 <th>Total Time</th>
#                                 <th>Response Hit</th>
#                                 <th>Total Response</th>
#                             </tr>
#                         </thead>
#                         <tbody>
#                             {table_rows}
#                         </tbody>
#                     </table>
#                 </div>
#             </div>
#         </body>
#     </html>
#     """

#     # Save HTML to a temporary file
#     temp_html_path = os.path.join(tempfile.gettempdir(), f"TT_Report_{employee_details.get('name')}.html")
#     with open(temp_html_path, 'w', encoding='utf-8') as temp_html:
#         temp_html.write(html_content)

#     # Generate PDF from HTML file
#     temp_pdf_path = os.path.join(tempfile.gettempdir(), f"TT_Report_{employee_details.get('name')}.pdf")
#     pdfkit.from_file(temp_html_path, temp_pdf_path, configuration=config)

#     # Return PDF as response
#     return send_file(temp_pdf_path, as_attachment=True, download_name=f"TT_Report_{employee_details.get('name')}.pdf")


def find_day(date_string):
    try:
        # Convert date string to datetime object
        date_obj = datetime.strptime(date_string, '%Y-%m-%d')

        # Get the day of the week (Monday is 0 and Sunday is 6)
        day_of_week = date_obj.weekday()

        # List of days of the week
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        # Return the corresponding day
        return days[day_of_week]

    except ValueError:
        return "Invalid Date Format"

def format_time(seconds):
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return '{:02d}:{:02d}:{:02d}'.format(int(hours), int(minutes), int(seconds))

@report_app.route('/api/generate_report_pdf', methods=['POST'])
@token_required_admin
def generate_report_pdf(current_user):

    try:
        data = request.get_json()
        company = current_user["company"]
        employee_id = str(data.get('employee_id'))
        start_date = data.get('start_date')
        end_date = data.get('end_date')

        # Query the database for relevant entries within the date range
        entries = collection.find_one({
            "_id": ObjectId(employee_id),
            "time_tracking": {
                "$elemMatch": {
                    "date": {"$gte": start_date, "$lte": end_date}
                }
            }
        })

        # Fetch employee details from user_collection
        employee_details = collection.find_one({"_id": ObjectId(employee_id)})
        company_name = company_collection.find_one({"company": employee_details.get('company')})

        # Prepare time tracking data and response summary
        time_tracking_data = entries.get('time_tracking', [])
        filtered_data = [data for data in time_tracking_data if start_date <= data.get('date') <= end_date]
        sorted_data = sorted(filtered_data, key=lambda x: x.get('date'))

        time_entries = []
        response_summary = []

        for time_entry in sorted_data:
            date = time_entry.get('date')
            start_time = time_entry.get('start_time')
            end_time = time_entry.get('end_time', '23:59:59')
            elapsed_time = time_entry.get('elapsed_time', '00:00:00')
            call_time = time_entry.get('call_time', '00:00:00')
            total_elapsed_time = time_entry.get('total_elapsed_time', '00:00:00')
            afk_count_length = len(time_entry.get('afk', []))

            # Calculate responses and hit confirmations
            response_details = next(
                (entry for entry in time_tracking_data if entry.get('date') == date), None
            )
            if response_details:
                response_values = [
                    value for key, value in response_details.items() if key.startswith("Response")
                ]
                miss_count = sum(1 for val in response_values if isinstance(val, str) and "Missed" in val)
                total_response = len(response_values) - 1
                hit_confirmation = max(0, total_response - miss_count)
            else:
                total_response = 0
                hit_confirmation = 0

            # Add time entry details
            time_entries.append({
                "date": date,
                "start_time": start_time,
                "end_time": end_time,
                "elapsed_time": elapsed_time,
                "call_time": call_time,
                "total_elapsed_time": total_elapsed_time,
                "inactive_time": elapsed_time,  # Adjust as per inactive time logic
            })

            # Add response summary
            response_summary.append({
                "date": date,
                "total_response": total_response,
                "hit_confirmation": hit_confirmation,
                "afk_count": afk_count_length
            })

        # # Prepare PDF content
        # pdf_buffer = BytesIO()

        # # Create PDF using reportlab
        # pdf = SimpleDocTemplate(pdf_buffer, pagesize=letter)
        # styles = getSampleStyleSheet()

        # # Title
        # title_style = styles['Title']
        # title_style.alignment = 1  # Center alignment
        # title_style.fontSize = 20
        # title = Paragraph(f"<u>{company_name['name']}</u>", title_style)

        # # Add a Spacer to create space
        # space_height = 30  # Adjust the height as needed
        # space = Spacer(1, space_height)

        # # Add Image from URL
        # # image_url = "https://www.hansrajventures.com/assets/HV-logo1-BnYK_F7c.webp"  # Replace this with the URL of your image
        # image_url = company_collection.find_one({"company": company},{"logo":1})['logo']
        # response = requests.get(image_url)
        # img_data = BytesIO(response.content)
        # img = Image(img_data, width=100, height=100)  # Adjust width and height as needed

        # # Employee details
        # details_style = ParagraphStyle('Details', parent=styles['Normal'],fontSize =10)
        # details_style.alignment = 1  # Center alignment
        # details_data = [
        #     ["Employee:", employee_details.get('name')],
        #     ["Email:", employee_details.get('email')],
        #     ["Phone:", employee_details.get('phone')],
        #     ["Gender:", employee_details.get('gender')],
        #     ["Date of Birth:", employee_details.get('dob')],
        #     ["Job:", employee_details.get('job')],
        #     ["Bio:", employee_details.get('bio')],
        #     # Add other details as needed
        # ]

        # details_table = Table(details_data, colWidths=[120, 260], hAlign='LEFT')
        # details_table.setStyle(TableStyle([
        #     ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        #     ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        #     ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        #     ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        #     ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        #     ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        # ]))

        # # Time Tracking Report
        # title2 = Paragraph(f"<u>Time Tracking Report ({start_date} - {end_date})</u>", title_style)

        # # Table headers
        # table_headers = ["Date", "Start Time", "End Time", "Elapsed Time", "Call Time", "Total Time", "Inactive Time", "Responses", "Confirmation","AFK Count"]
        # data_rows = [table_headers]

        # # Table data
        # time_tracking_data = entries.get('time_tracking', [])
        # # Filter time_tracking_data by date range
        # filtered_data = [data for data in time_tracking_data if start_date <= data.get('date') <= end_date]

        # # Sort filtered_data by 'date' in ascending order
        # sorted_data = sorted(filtered_data, key=lambda x: x.get('date'))

        # for time_entry in sorted_data:
        #     date = time_entry.get('date')
        #     start_time = time_entry.get('start_time')
        #     end_time = time_entry.get('end_time', '23:59:59')
        #     elapsed_time = time_entry.get('elapsed_time', '00:00:00')
        #     call_time = time_entry.get('call_time', '00:00:00')
        #     total_elapsed_time = time_entry.get('total_elapsed_time', '00:00:00')
        #     afk_count_length = len(time_entry.get('afk', []))



        #     if start_time:
        #         start_time_1 = datetime.strptime(start_time, '%H:%M:%S')
        #     else:
        #         start_time_1 = datetime.strptime('00:00:00', '%H:%M:%S')

        #     if end_time:
        #         end_time_1 = datetime.strptime(end_time, '%H:%M:%S')
        #     else:
        #         end_time_1 = datetime.strptime('00:00:00', '%H:%M:%S')

        #     if total_elapsed_time:
        #         total_elapsed_time_1 = datetime.strptime(total_elapsed_time, '%H:%M:%S') - datetime.strptime('00:00:00', '%H:%M:%S')
        #     else:
        #         total_elapsed_time_1 = timedelta(0)
        #     inactive_time = '00:00:00'
        #     if start_time:
        #         inactive_time = format_time(max(0,(end_time_1 - start_time_1 - total_elapsed_time_1).total_seconds()))


        #     # Calculate Total Response and Hit Confirmation (from response_details_by_date route logic)
        #     response_details = None
        #     for response_entry in time_tracking_data:
        #         entry_date_str = response_entry.get('date', '')
        #         if entry_date_str == date:
        #             response_details = response_entry
        #             break

        #     if response_details:
        #         response_values = [value for key, value in response_details.items() if key.startswith("Response")]
        #         miss_count = sum(1 for val in response_values if isinstance(val, str) and "Missed" in val)

        #         total_response = len(response_values) - 1
        #         hit_confirmation = max(0, total_response - miss_count)
        #     else:
        #         total_response = 0
        #         hit_confirmation = 0

        #     data_row = [date, start_time, end_time, elapsed_time, call_time, total_elapsed_time, inactive_time, total_response, hit_confirmation, afk_count_length]
        #     data_rows.append(data_row)

        # # Calculate column widths dynamically
        # col_widths = [55, 55, 55, 55, 55, 55, 55, 55, 55, 55]  # Adjust as needed

        # # Create table
        # table = Table(data_rows, colWidths=col_widths)
        # table.setStyle(TableStyle([
        #     ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        #     ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        #     ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        #     ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        #     ('FONTSIZE', (0, 0), (-1, 0), 8),  # Reduced font size for headers
        #     ('BOTTOMPADDING', (0, 0), (-1, 0), 4),  # Reduced padding for headers
        #     ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),  # Regular font for data rows
        #     ('FONTSIZE', (0, 1), (-1, -1), 8),  # Reduced font size for data rows
        #     ('BOTTOMPADDING', (0, 1), (-1, -1), 4),  # Reduced padding for data rows
        #     ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        # ]))

        # # Build the PDF
        # pdf.build([title, space, img, space, details_table, space, title2, table])

        # # Return PDF as response
        # pdf_buffer.seek(0)
        # pdf_name = f"TT_Report_{employee_details.get('name')}.pdf"
        pdf_url = ""
        # pdf_url = upload_report_firebase(pdf_buffer, 'reports', pdf_name)

        # Prepare response data
        response_data = {
            "employee_details": {
                "name": employee_details.get('name'),
                "email": employee_details.get('email'),
                "phone": employee_details.get('phone'),
                "gender": employee_details.get('gender'),
                "dob": employee_details.get('dob'),
                "job": employee_details.get('job'),
                "bio": employee_details.get('bio'),
                "profile_pic": employee_details.get('profile_pic',''),
            },
            "company_details": {
                "name": company_name.get('name'),
                "logo": company_name.get('logo'),
            },
            "time_tracking": time_entries,
            "response_summary": response_summary,
            "report_url": pdf_url
        }

        return jsonify({"message": "Report generated successfully", "url": pdf_url, "data": response_data}), 200


    except Exception as e:
        return jsonify({"error": f"Something went wrong: {e}"}), 500