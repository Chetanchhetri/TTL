# import cProfile, sys

# from gevent.pywsgi import WSGIServer
# from geventwebsocket.handler import WebSocketHandler
# from gevent import monkey

import eventlet
from eventlet import wsgi

# Disabled OS/thread patching to prevent Windows system library compatibility errors
eventlet.monkey_patch(os=False, thread=False)

# ATTACHING BLUEPRINTS OF ALL FILES
from socketio_setup import socketio, app
from time_manage import time_manage_app
from emp_work_update import emp_work_update_app
from tasks import tasks_app
from employee_extra import employee_extra_app
from add_delete_emp import add_delete_emp_app
from admin_details import admin_details_app
from admin_extras import admin_extras_app
from report import report_app
from email_send import email_send_app
from notifications import notifications_app
from tickets import ticket_app
from super_admin import super_admin_app
from landing_page import landing_page_app
from login import login_app
from leaves import leaves_app
from sales import sales_app
from complains import complains_app

# --- FIX: Explicitly import and apply Flask-CORS directly onto the app object ---
from flask_cors import CORS
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

# Register Blueprints
app.register_blueprint(time_manage_app)
app.register_blueprint(emp_work_update_app)
app.register_blueprint(tasks_app)
app.register_blueprint(employee_extra_app)
app.register_blueprint(add_delete_emp_app)
app.register_blueprint(admin_details_app)
app.register_blueprint(admin_extras_app)
app.register_blueprint(report_app)
app.register_blueprint(email_send_app)
app.register_blueprint(notifications_app)
app.register_blueprint(ticket_app)
app.register_blueprint(super_admin_app)
app.register_blueprint(landing_page_app)
app.register_blueprint(login_app)
app.register_blueprint(leaves_app)
app.register_blueprint(sales_app)
app.register_blueprint(complains_app)

from flask import request, g
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

@app.before_request
def start_timer():
    g.start = time.time()

@app.after_request
def log_request(response):
    if request.path == '/favicon.ico':
        return response
    if request.path.startswith('/static'):
        return response

    duration = round(time.time() - g.start, 3)
    status = response.status_code
    method = request.method
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    log_params = {
        "method": method,
        "path": request.path,
        "status": status,
        "duration": duration,
        "ip": ip,
    }

    if duration > 5 or status >= 500:
        logging.warning(f"[SLOW/ERROR] {log_params}")
    else:
        logging.info(f"{log_params}")
    
    return response


if __name__ == '__main__':
    # main()
    # socketio.run(app, port=5002,debug=True)

    # http = WSGIServer(('0.0.0.0', 5002), app, handler_class=WebSocketHandler)
    # http.serve_forever()
    
    print("Starting Toggle Timer Backend on port 5002...")
    wsgi.server(eventlet.listen(('0.0.0.0', 5002)), app, max_size=2000)

    # app.run(host="0.0.0.0", port=5002, debug=True, use_reloader=False)