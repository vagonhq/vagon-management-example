"""
Vagon Organization Management API - Example Flask Application

This Flask application demonstrates how to use the Vagon Organization
Management External API. It provides a web interface for managing machines
and files.

Features:
    - List and view machines
    - Start/Stop machines
    - Create temporary machine access links
    - Browse and upload files (organization and machine-specific)

Usage:
    1. Copy .env.example to .env and fill in your API credentials
    2. Install dependencies: pip install -r requirements.txt
    3. Run: python app.py
    4. Open http://localhost:5000 in your browser
"""

import os
import logging
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from werkzeug.exceptions import BadRequest, HTTPException
from dotenv import load_dotenv

from vagon_api import (
    VagonAPI,
    VagonAPIError,
    format_bytes,
    flatten_jsonapi_resource,
    flatten_jsonapi_list
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key')

# Initialize Vagon API client
api_client = VagonAPI(
    api_key=os.getenv('VAGON_API_KEY', ''),
    api_secret=os.getenv('VAGON_API_SECRET', ''),
    base_url=os.getenv('VAGON_BASE_URL', VagonAPI.PRODUCTION_URL)
)


# =============================================================================
# REQUEST LOGGING
# =============================================================================

@app.before_request
def log_request_info():
    """Log only API requests (not HTML page renders)."""
    # Only log API endpoints, skip HTML page requests
    if not request.path.startswith('/api/'):
        return
    
    logger.info(f"[REQUEST] {request.method} {request.path}")
    logger.info(f"  Remote Addr: {request.remote_addr}")
    logger.info(f"  User-Agent: {request.headers.get('User-Agent', 'N/A')}")
    
    if request.args:
        logger.info(f"  Query Params: {dict(request.args)}")
    
    # Safely try to get JSON body without forcing Flask to parse it
    # Use get_json with silent=True to avoid exceptions
    content_type = request.headers.get('Content-Type', '')
    has_data = request.data and len(request.data) > 0
    
    if 'application/json' in content_type:
        # Use silent=True to avoid BadRequest exception if JSON is invalid or empty
        json_data = request.get_json(silent=True, force=True)
        if json_data:
            logger.info(f"  JSON Body: {json_data}")
        elif has_data:
            logger.info(f"  JSON Body: (empty or invalid)")
    elif request.form:
        logger.info(f"  Form Data: {dict(request.form)}")
    elif has_data:
        try:
            import json
            body = json.loads(request.data.decode('utf-8'))
            logger.info(f"  Body: {body}")
        except:
            logger.info(f"  Body (raw): {request.data[:500]}")


@app.after_request
def log_response_info(response):
    """Log only API responses (not HTML page renders)."""
    # Only log API endpoints, skip HTML page requests
    if not request.path.startswith('/api/'):
        return response
    
    logger.info(f"[RESPONSE] {request.method} {request.path} -> {response.status_code}")
    
    # Only log JSON responses (API responses)
    try:
        import json
        # Get response data
        response_data = response.get_data(as_text=True)
        
        if response_data:
            # Try to parse as JSON
            try:
                parsed_json = json.loads(response_data)
                logger.info(f"  Response Body (JSON): {json.dumps(parsed_json, indent=2)}")
            except json.JSONDecodeError:
                # If not JSON, skip logging (probably HTML or other non-API content)
                pass
        else:
            logger.info(f"  Response Body: (empty)")
            
        # Also log headers for debugging errors
        if response.status_code >= 400:
            logger.info(f"  Response Headers: {dict(response.headers)}")
    except Exception as e:
        logger.warning(f"  Could not log response body: {str(e)}")
    
    return response


# =============================================================================
# ERROR HANDLING
# =============================================================================

@app.errorhandler(BadRequest)
def handle_bad_request(e):
    """Handle BadRequest exceptions (like JSON decode errors) and return JSON for API routes."""
    logger.error(f"[BAD REQUEST] {request.method} {request.path} -> {str(e)}")
    
    # Return JSON for API requests
    if request.path.startswith('/api/'):
        error_response = jsonify({
            'error': str(e.description) if hasattr(e, 'description') else str(e),
            'client_code': 400,
            'status_code': 400
        })
        error_response.headers['Content-Type'] = 'application/json'
        return error_response, 400
    
    # For non-API requests, return default Flask error
    return e


@app.errorhandler(HTTPException)
def handle_http_exception(e):
    """Handle all HTTP exceptions and return JSON for API routes."""
    logger.error(f"[HTTP EXCEPTION] {request.method} {request.path} -> {e.code}: {str(e)}")
    
    # Return JSON for API requests
    if request.path.startswith('/api/'):
        error_response = jsonify({
            'error': e.description if hasattr(e, 'description') else str(e),
            'client_code': e.code,
            'status_code': e.code
        })
        error_response.headers['Content-Type'] = 'application/json'
        return error_response, e.code
    
    # For non-API requests, return default Flask error
    return e


def handle_api_errors(f):
    """Decorator to handle VagonAPIError exceptions."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except VagonAPIError as e:
            # Log error details
            logger.error(f"[API ERROR] {request.method} {request.path} -> client_code={e.client_code}, status={e.status_code}, message={e.message}")

            # Return JSON for API requests
            if request.is_json or request.headers.get('Accept') == 'application/json' or request.path.startswith('/api/'):
                error_response = jsonify({
                    'error': e.message,
                    'client_code': e.client_code,
                    'status_code': e.status_code
                })
                # Ensure Content-Type is set correctly
                error_response.headers['Content-Type'] = 'application/json'
                logger.info(f"[API ERROR] Returning JSON response: {error_response.get_data(as_text=True)}")
                return error_response, e.status_code

            flash(f'API Error [{e.client_code}]: {e.message}', 'error')
            return redirect(request.referrer or url_for('index'))
        except Exception as e:
            # Catch any other unexpected exceptions
            logger.error(f"[UNEXPECTED ERROR] {request.method} {request.path} -> error={str(e)}, type={type(e).__name__}")
            
            # Return JSON for API requests
            if request.path.startswith('/api/'):
                error_response = jsonify({
                    'error': str(e),
                    'client_code': 500,
                    'status_code': 500
                })
                error_response.headers['Content-Type'] = 'application/json'
                return error_response, 500
            
            # For non-API requests, re-raise
            raise
    return decorated_function


# =============================================================================
# TEMPLATE FILTERS
# =============================================================================

@app.template_filter('format_bytes')
def format_bytes_filter(value):
    """Jinja2 filter to format bytes."""
    if value is None:
        return 'N/A'
    try:
        return format_bytes(int(value))
    except (TypeError, ValueError):
        return 'N/A'


@app.template_filter('format_gigabytes')
def format_gigabytes_filter(value):
    """Jinja2 filter to format value as gigabytes (value is already in GB)."""
    if value is None:
        return 'N/A'
    try:
        value_float = float(value)
        return f"{value_float:.2f} GB"
    except (TypeError, ValueError):
        return 'N/A'


@app.template_filter('format_minutes')
def format_minutes_filter(value):
    """Jinja2 filter to format minutes into human-readable format."""
    if value is None or value == 0:
        return '0 minutes'
    try:
        minutes = int(value)
        if minutes < 60:
            return f"{minutes} minute{'s' if minutes != 1 else ''}"
        elif minutes < 1440:  # Less than 24 hours
            hours = minutes // 60
            remaining_minutes = minutes % 60
            if remaining_minutes == 0:
                return f"{hours} hour{'s' if hours != 1 else ''}"
            else:
                return f"{hours} hour{'s' if hours != 1 else ''} {remaining_minutes} minute{'s' if remaining_minutes != 1 else ''}"
        else:  # 24 hours or more
            days = minutes // 1440
            remaining_hours = (minutes % 1440) // 60
            if remaining_hours == 0:
                return f"{days} day{'s' if days != 1 else ''}"
            else:
                return f"{days} day{'s' if days != 1 else ''} {remaining_hours} hour{'s' if remaining_hours != 1 else ''}"
    except (TypeError, ValueError):
        return 'N/A'


@app.template_filter('format_usage_minutes')
def format_usage_minutes_filter(minutes):
    """Jinja2 filter to format minutes as 'X hours Y minutes'."""
    # Handle None, empty string, or 0
    if minutes is None or minutes == '':
        return '0 hours 0 minutes'
    
    try:
        # Convert to int, handling string numbers
        minutes_int = int(float(str(minutes)))
        hours = minutes_int // 60
        remaining_minutes = minutes_int % 60
        
        if hours == 0:
            if remaining_minutes == 0:
                return '0 hours 0 minutes'
            elif remaining_minutes == 1:
                return '0 hours 1 minute'
            else:
                return f'0 hours {remaining_minutes} minutes'
        else:
            if remaining_minutes == 0:
                if hours == 1:
                    return '1 hour 0 minutes'
                else:
                    return f'{hours} hours 0 minutes'
            else:
                if hours == 1:
                    if remaining_minutes == 1:
                        return '1 hour 1 minute'
                    else:
                        return f'1 hour {remaining_minutes} minutes'
                else:
                    if remaining_minutes == 1:
                        return f'{hours} hours 1 minute'
                    else:
                        return f'{hours} hours {remaining_minutes} minutes'
    except (TypeError, ValueError) as e:
        # If conversion fails, return the original value formatted
        return f'0 hours 0 minutes'


@app.template_filter('format_usage_with_machine_type')
def format_usage_with_machine_type_filter(minutes, machine_type_name=None):
    """Jinja2 filter to format minutes as 'X hours Y minutes of [machine_type] usage'."""
    # Handle None, empty string, or 0
    if minutes is None or minutes == '':
        machine_type = machine_type_name or 'machine'
        return f'0 hours 0 minutes of {machine_type} usage'
    
    try:
        # Convert to int, handling string numbers
        minutes_int = int(float(str(minutes)))
        hours = minutes_int // 60
        remaining_minutes = minutes_int % 60
        machine_type = machine_type_name or 'machine'
        
        if hours == 0:
            if remaining_minutes == 0:
                return f'0 hours 0 minutes of {machine_type} usage'
            elif remaining_minutes == 1:
                return f'0 hours 1 minute of {machine_type} usage'
            else:
                return f'0 hours {remaining_minutes} minutes of {machine_type} usage'
        else:
            if remaining_minutes == 0:
                if hours == 1:
                    return f'1 hour 0 minutes of {machine_type} usage'
                else:
                    return f'{hours} hours 0 minutes of {machine_type} usage'
            else:
                if hours == 1:
                    if remaining_minutes == 1:
                        return f'1 hour 1 minute of {machine_type} usage'
                    else:
                        return f'1 hour {remaining_minutes} minutes of {machine_type} usage'
                else:
                    if remaining_minutes == 1:
                        return f'{hours} hours 1 minute of {machine_type} usage'
                    else:
                        return f'{hours} hours {remaining_minutes} minutes of {machine_type} usage'
    except (TypeError, ValueError) as e:
        machine_type = machine_type_name or 'machine'
        return f'0 hours 0 minutes of {machine_type} usage'


# =============================================================================
# PAGE ROUTES
# =============================================================================

@app.route('/')
@handle_api_errors
def index():
    """
    Home page - Display list of all machines.

    This demonstrates the list_machines() API method.
    API returns JSON:API format which we flatten for easier template usage.
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    query = request.args.get('q', None)
    time_left = request.args.get('time_left', type=int)
    has_session_data = request.args.get('has_session_data', type=lambda v: v.lower() == 'true' if v else None)
    status = request.args.get('status', None)

    result = api_client.list_machines(
        page=page,
        per_page=per_page,
        query=query,
        time_left=time_left,
        has_session_data=has_session_data,
        status=status
    )

    # Flatten JSON:API format for template
    machines = flatten_jsonapi_list(result.get('machines', []))

    return render_template(
        'index.html',
        machines=machines,
        count=result.get('count', 0),
        page=page,
        next_page=result.get('next_page'),
        query=query,
        time_left=time_left,
        has_session_data=has_session_data,
        status=status,
        default_plan_id=os.getenv('DEFAULT_PLAN_ID', '')
    )


@app.route('/machines/<int:machine_id>')
@handle_api_errors
def machine_detail(machine_id):
    """
    Machine detail page - Show machine info and files.

    This demonstrates get_machine() and get_machine_files() API methods.
    API returns JSON:API format which we flatten for easier template usage.
    """
    machine_response = api_client.get_machine(machine_id)
    machine = flatten_jsonapi_resource(machine_response)
    
    if not machine:
        return render_template('error.html', error="Machine not found"), 404
    
    parent_id = request.args.get('parent_id', 0, type=int)
    page = request.args.get('page', 1, type=int)

    files_result = api_client.get_machine_files(
        machine_id=machine_id,
        parent_id=parent_id,
        page=page
    )

    # Flatten JSON:API format for template
    files = flatten_jsonapi_list(files_result.get('files', []))
    current = flatten_jsonapi_resource(files_result.get('current'))

    return render_template(
        'machine_detail.html',
        machine=machine,
        files=files,
        current=current,
        count=files_result.get('count', 0),
        page=page,
        next_page=files_result.get('next_page'),
        parent_id=parent_id
    )


@app.route('/files')
@handle_api_errors
def organization_files():
    """
    Organization files page - Show shared files.

    This demonstrates list_files() API method.
    API returns JSON:API format which we flatten for easier template usage.
    """
    parent_id = request.args.get('parent_id', 0, type=int)
    page = request.args.get('page', 1, type=int)
    query = request.args.get('q', None)

    result = api_client.list_files(
        parent_id=parent_id,
        page=page,
        query=query
    )

    capacity = api_client.get_capacity()

    # Flatten JSON:API format for template
    files = flatten_jsonapi_list(result.get('files', []))
    current = flatten_jsonapi_resource(result.get('current'))

    return render_template(
        'files.html',
        files=files,
        current=current,
        count=result.get('count', 0),
        page=page,
        next_page=result.get('next_page'),
        parent_id=parent_id,
        query=query,
        capacity=capacity
    )

def _parse_date_param(param_name: str, default_value: datetime) -> datetime:
    """
    Parse an ISO date/datetime string from query params.

    Accepts either full ISO datetime or YYYY-MM-DD. Falls back to default_value.
    """
    value = request.args.get(param_name)
    if not value:
        return default_value

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise BadRequest(f"Invalid {param_name} format. Use ISO date or datetime.") from exc


@app.route('/images')
@handle_api_errors
def images():
    """
    Images page - Display list of all images (templates).

    This demonstrates the list_images() API method.
    API returns JSON:API format which we flatten for easier template usage.
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    query = request.args.get('q', None)

    result = api_client.list_images(page=page, per_page=per_page, query=query)

    # Flatten JSON:API format for template
    images_list = flatten_jsonapi_list(result.get('images', []))
    
    # Post-process images to fix enum values and format dates
    for image in images_list:
        # Convert source enum (0=seat, 1=pre_installation) to string
        source_map = {0: 'seat', 1: 'pre_installation'}
        if 'source' in image and isinstance(image['source'], int):
            image['source'] = source_map.get(image['source'], 'unknown')
        
        # Format created_at date
        if 'created_at' in image and image['created_at']:
            try:
                # Parse ISO format date and format it nicely
                from datetime import datetime
                dt = datetime.fromisoformat(image['created_at'].replace('Z', '+00:00'))
                image['created_at'] = dt.strftime('%Y-%m-%d %H:%M')
            except (ValueError, AttributeError):
                # If parsing fails, try to extract date part
                if isinstance(image['created_at'], str) and len(image['created_at']) >= 10:
                    image['created_at'] = image['created_at'][:10]

    # Get machines for assign modal
    machines_result = api_client.list_machines(page=1, per_page=100)
    machines = flatten_jsonapi_list(machines_result.get('machines', []))

    return render_template(
        'images.html',
        images=images_list,
        count=result.get('count', 0),
        page=page,
        next_page=result.get('next_page'),
        query=query,
        machines=machines
    )


@app.route('/logs')
@handle_api_errors
def user_action_logs():
    """
    Organization activity logs (recent 30 days) with optional filters.
    Also shows archived log download URLs for dates older than 30 days.

    Uses the /organization-management/v1/user-action-logs endpoint for recent logs
    and /organization-management/v1/user-action-logs/archived-download-urls for archived logs.
    """
    today = datetime.utcnow()
    default_start = today - timedelta(days=7)

    start_date = _parse_date_param('start_date', default_start)
    end_date = _parse_date_param('end_date', today)

    if end_date < start_date:
        raise BadRequest("end_date must be after start_date")

    action_type = request.args.get('action_type') or None
    user_email = request.args.get('user_email') or None
    organization_machine_id = request.args.get('organization_machine_id', type=int)

    # Get recent logs (last 30 days)
    logs_result = api_client.list_user_action_logs(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        action_type=action_type,
        user_email=user_email,
        organization_machine_id=organization_machine_id
    )

    # Flatten JSON:API format for template
    raw_logs = logs_result.get('logs', [])
    logs = flatten_jsonapi_list(raw_logs)
    
    # Ensure metadata is always a dict (not None, Undefined, or missing)
    for log in logs:
        # Ensure metadata exists and is a dict
        if 'metadata' not in log or log.get('metadata') is None:
            log['metadata'] = {}
        elif not isinstance(log.get('metadata'), dict):
            # If metadata is not a dict, wrap it or make it empty
            log['metadata'] = {}
        
        # Convert created_at to readable format if it's a string
        if 'created_at' in log and isinstance(log['created_at'], str):
            try:
                dt = datetime.fromisoformat(log['created_at'].replace('Z', '+00:00'))
                log['created_at'] = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
            except (ValueError, AttributeError):
                pass  # Keep original if parsing fails

    # Check if we need to fetch archived logs (older than 30 days)
    archived_urls = []
    retention_cutoff = today - timedelta(days=30)
    
    # If end_date is older than 30 days, fetch archived URLs
    if end_date < retention_cutoff:
        try:
            archived_result = api_client.get_archived_user_action_logs_urls(
                start_date=start_date.date().isoformat(),
                end_date=end_date.date().isoformat(),
                expires_in=3600  # 1 hour expiration
            )
            archived_urls = archived_result.get('download_urls', [])
        except VagonAPIError as e:
            # If archived endpoint fails (e.g., no archived logs), just log and continue
            logger.warning(f"Could not fetch archived logs: {e.message}")
            archived_urls = []
    elif start_date < retention_cutoff:
        # If start_date is older than 30 days but end_date is not, fetch archived URLs for the old part
        try:
            archived_result = api_client.get_archived_user_action_logs_urls(
                start_date=start_date.date().isoformat(),
                end_date=retention_cutoff.date().isoformat(),
                expires_in=3600
            )
            archived_urls = archived_result.get('download_urls', [])
        except VagonAPIError as e:
            logger.warning(f"Could not fetch archived logs: {e.message}")
            archived_urls = []

    return render_template(
        'logs.html',
        logs=logs,
        count=logs_result.get('count', len(logs)),
        start_date=start_date.date(),
        end_date=end_date.date(),
        archived_urls=archived_urls,
        filters={
            'action_type': action_type or '',
            'user_email': user_email or '',
            'organization_machine_id': organization_machine_id or ''
        }
    )


# =============================================================================
# MACHINE API ROUTES
# =============================================================================

@app.route('/api/machines', methods=['GET'])
@handle_api_errors
def api_list_machines():
    """
    API endpoint to list machines (for use in modals and AJAX calls).
    
    Returns JSON with machines list in flattened format.
    
    Query parameters:
        - page: Page number (default: 1)
        - per_page: Items per page (default: 20)
        - q: Search query
        - time_left: Filter by remaining usage in minutes
        - has_session_data: Filter by whether machine has session data (true/false)
        - status: Filter by machine status (e.g., 'running', 'off', 'stopping')
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    query = request.args.get('q', None)
    time_left = request.args.get('time_left', type=int)
    has_session_data = request.args.get('has_session_data', type=lambda v: v.lower() == 'true' if v else None)
    status = request.args.get('status', None)

    result = api_client.list_machines(
        page=page,
        per_page=per_page,
        query=query,
        time_left=time_left,
        has_session_data=has_session_data,
        status=status
    )

    # Flatten JSON:API format for template
    machines = flatten_jsonapi_list(result.get('machines', []))

    return jsonify({
        'machines': machines,
        'count': result.get('count', 0),
        'page': result.get('page', page),
        'next_page': result.get('next_page')
    })


@app.route('/api/machines/<int:machine_id>/start', methods=['POST'])
@handle_api_errors
def start_machine(machine_id):
    """
    Start a machine.

    This demonstrates the start_machine() API method.

    Optional JSON body:
        {
            "machine_type_id": 5,
            "region": "dublin"
        }
    """
    logger.info(f"[MACHINE START] Starting machine_id={machine_id}")
    
    # Use silent=True to avoid BadRequest exception if JSON is invalid or empty
    data = request.get_json(silent=True) or {}
    logger.info(f"[MACHINE START] Request data: machine_id={machine_id}, machine_type_id={data.get('machine_type_id')}, region={data.get('region')}")

    try:
        result = api_client.start_machine(
            machine_id=machine_id,
            machine_type_id=data.get('machine_type_id'),
            region=data.get('region')
        )
        logger.info(f"[MACHINE START] Success: machine_id={machine_id}, result={result}")
        return jsonify({'success': True, 'message': 'Machine start initiated'})
    except VagonAPIError as e:
        logger.error(f"[MACHINE START] Error: machine_id={machine_id}, client_code={e.client_code}, status={e.status_code}, message={e.message}")
        raise
    except Exception as e:
        logger.error(f"[MACHINE START] Unexpected error: machine_id={machine_id}, error={str(e)}")
        raise


@app.route('/api/machines/<int:machine_id>/stop', methods=['POST'])
@handle_api_errors
def stop_machine(machine_id):
    """
    Stop a machine.

    This demonstrates the stop_machine() API method.
    """
    logger.info(f"[MACHINE STOP] Stopping machine_id={machine_id}")
    try:
        result = api_client.stop_machine(machine_id)
        logger.info(f"[MACHINE STOP] Success: machine_id={machine_id}, result={result}")
        return jsonify({'success': True, 'message': 'Machine stop initiated'})
    except Exception as e:
        logger.error(f"[MACHINE STOP] Error: machine_id={machine_id}, error={str(e)}")
        raise


@app.route('/api/machines/<int:machine_id>/reset', methods=['POST'])
@handle_api_errors
def reset_machine(machine_id):
    """
    Reset a stopped machine.

    This demonstrates the reset_machine() API method.
    
    Note: The machine must be stopped (not running) to reset it.
    This will delete all machine images, mark the session as reset,
    and terminate the EC2 instance if it exists.
    """
    logger.info(f"[MACHINE RESET] Resetting machine_id={machine_id}")
    try:
        result = api_client.reset_machine(machine_id)
        logger.info(f"[MACHINE RESET] Success: machine_id={machine_id}, result={result}")
        return jsonify({'success': True, 'message': 'Machine reset initiated'})
    except VagonAPIError as e:
        logger.error(f"[MACHINE RESET] Error: machine_id={machine_id}, client_code={e.client_code}, status={e.status_code}, message={e.message}")
        raise
    except Exception as e:
        logger.error(f"[MACHINE RESET] Unexpected error: machine_id={machine_id}, error={str(e)}")
        raise


@app.route('/api/machines/<int:machine_id>/access', methods=['POST'])
@handle_api_errors
def create_access(machine_id):
    """
    Create temporary machine access link.

    This demonstrates the create_machine_access() API method.
    API returns JSON:API format with attributes nested.

    JSON body:
        {
            "expires_in": 3600  // seconds
        }
    """
    logger.info(f"[MACHINE ACCESS] Creating access for machine_id={machine_id}")
    # Use silent=True to avoid BadRequest exception if JSON is invalid or empty
    data = request.get_json(silent=True) or {}
    
    # expires_in is required, must be provided by frontend
    if 'expires_in' not in data or data.get('expires_in') is None:
        logger.error(f"[MACHINE ACCESS] Missing expires_in parameter")
        return jsonify({
            'error': 'expires_in parameter is required (in seconds)',
            'client_code': 400,
            'status_code': 400
        }), 400
    
    expires_in = data.get('expires_in')
    # Convert minutes to seconds if needed (if expires_in > 10000, assume it's in seconds, otherwise assume minutes)
    # Actually, let's just use seconds as specified in API
    logger.info(f"[MACHINE ACCESS] Request: machine_id={machine_id}, expires_in={expires_in} seconds")

    result = api_client.create_machine_access(
        machine_id=machine_id,
        expires_in=expires_in
    )
    logger.info(f"[MACHINE ACCESS] Success: machine_id={machine_id}, result={result}")

    # Extract from JSON:API format (attributes are nested)
    attrs = result.get('attributes', {})
    
    # Log the raw expires_at value for debugging
    expires_at_raw = attrs.get('expires_at')
    logger.info(f"[MACHINE ACCESS] Raw expires_at from API: {expires_at_raw}")

    return jsonify({
        'success': True,
        'connection_link': attrs.get('connection_link'),
        'expires_at': expires_at_raw
    })


@app.route('/api/machines/<int:machine_id>')
@handle_api_errors
def get_machine(machine_id):
    """
    Get machine details.

    This demonstrates the get_machine() API method.
    """
    logger.info(f"[GET MACHINE] Fetching machine_id={machine_id}")
    machine = api_client.get_machine(machine_id)
    logger.info(f"[GET MACHINE] Success: machine_id={machine_id}")
    return jsonify(machine)


@app.route('/api/machines/<int:machine_id>/machine-type', methods=['POST'])
@handle_api_errors
def set_machine_type(machine_id):
    """
    Set machine type for a machine.

    This demonstrates the set_machine_type() API method.

    JSON body:
        {
            "machine_type_id": 5
        }
    """
    logger.info(f"[SET MACHINE TYPE] Setting machine type for machine_id={machine_id}")
    # Use silent=True to avoid BadRequest exception if JSON is invalid or empty
    data = request.get_json(silent=True) or {}
    machine_type_id = data.get('machine_type_id')
    
    if not machine_type_id:
        logger.error("[SET MACHINE TYPE] Missing machine_type_id parameter")
        return jsonify({
            'error': 'machine_type_id parameter is required',
            'client_code': 400,
            'status_code': 400
        }), 400
    
    logger.info(f"[SET MACHINE TYPE] Request: machine_id={machine_id}, machine_type_id={machine_type_id}")
    
    try:
        result = api_client.set_machine_type(
            machine_id=machine_id,
            machine_type_id=machine_type_id
        )
        logger.info(f"[SET MACHINE TYPE] Success: machine_id={machine_id}, machine_type_id={machine_type_id}")
        return jsonify({'success': True, 'message': 'Machine type updated'})
    except VagonAPIError as e:
        logger.error(f"[SET MACHINE TYPE] Error: machine_id={machine_id}, client_code={e.client_code}, status={e.status_code}, message={e.message}")
        raise
    except Exception as e:
        logger.error(f"[SET MACHINE TYPE] Unexpected error: machine_id={machine_id}, error={str(e)}")
        raise


# =============================================================================
# FILES API ROUTES
# =============================================================================

@app.route('/api/files', methods=['POST'])
@handle_api_errors
def create_file():
    """
    Create a directory only (JSON endpoint).

    For file uploads, use /api/files/upload instead.

    JSON body for directory:
        {
            "name": "New Folder",
            "object_type": "directory",
            "parent_id": 0,
            "machine_id": 123  // optional
        }
    """
    logger.info(f"[CREATE FILE/DIR] Request received")
    # Use silent=True to avoid BadRequest exception if JSON is invalid or empty
    data = request.get_json(silent=True)
    
    if not data:
        logger.error("[CREATE FILE/DIR] No JSON data provided")
        return jsonify({'error': 'JSON body is required', 'client_code': 400, 'status_code': 400}), 400
    
    logger.info(f"[CREATE FILE/DIR] Data: {data}")

    if data.get('object_type') != 'directory':
        logger.warning(f"[CREATE FILE/DIR] Invalid object_type: {data.get('object_type')}")
        return jsonify({'error': 'Use /api/files/upload for file uploads'}), 400

    result = api_client.create_directory(
        name=data['name'],
        parent_id=data.get('parent_id', 0),
        machine_id=data.get('machine_id')
    )
    logger.info(f"[CREATE FILE/DIR] Success: result={result}")

    return jsonify({
        'success': True,
        'id': result.get('id'),
        'uid': result.get('uid')
    })


@app.route('/api/files/upload', methods=['POST'])
@handle_api_errors
def upload_file():
    """
    Upload a file to Vagon storage.

    Backend handles the entire upload process:
    1. Creates file entry via Vagon API
    2. Uploads file chunks to S3 presigned URLs
    3. Completes the multipart upload

    Form data:
        - file: The file to upload
        - parent_id: Parent directory ID (default: 0 for root)
        - machine_id: Machine ID for machine-specific storage (optional)
    """
    import requests as http_requests

    logger.info(f"[FILE UPLOAD] Starting upload request")
    
    # Get file from request
    if 'file' not in request.files:
        logger.error("[FILE UPLOAD] No file in request")
        return jsonify({'error': 'No file provided', 'client_code': 400}), 400

    file = request.files['file']
    if file.filename == '':
        logger.error("[FILE UPLOAD] Empty filename")
        return jsonify({'error': 'No file selected', 'client_code': 400}), 400

    # Get form parameters
    parent_id = request.form.get('parent_id', 0, type=int)
    machine_id = request.form.get('machine_id', type=int)

    logger.info(f"[FILE UPLOAD] Starting upload: filename={file.filename}, parent_id={parent_id}, machine_id={machine_id}")

    # Read file content
    file_content = file.read()
    file_size = len(file_content)
    content_type = file.content_type or 'application/octet-stream'

    logger.info(f"[FILE UPLOAD] File size={file_size}, content_type={content_type}")

    # Step 1: Create file entry and get upload URLs
    try:
        create_result = api_client.create_file(
            name=file.filename,
            parent_id=parent_id,
            content_type=content_type,
            size=file_size,
            machine_id=machine_id
        )
        logger.info(f"[FILE UPLOAD] Create file result: {create_result}")
    except VagonAPIError as e:
        logger.error(f"[FILE UPLOAD] Create file failed: client_code={e.client_code}, status={e.status_code}, message={e.message}")
        raise

    file_id = create_result.get('id')
    upload_urls = create_result.get('upload_urls', [])

    logger.info(f"[FILE UPLOAD] File ID={file_id}, upload_urls count={len(upload_urls)}")

    if not upload_urls:
        logger.error("[FILE UPLOAD] No upload URLs received from API")
        return jsonify({'error': 'No upload URLs received from API', 'client_code': 500}), 500

    # Step 2: Upload file chunks to S3
    chunk_size = 250 * 1024 * 1024  # 250MB per chunk
    parts = []

    for i, upload_url in enumerate(upload_urls):
        start = i * chunk_size
        end = min(start + chunk_size, file_size)
        chunk = file_content[start:end]

        logger.info(f"[FILE UPLOAD] Uploading chunk {i + 1}/{len(upload_urls)}, size={len(chunk)}")

        # Upload chunk to S3 presigned URL
        try:
            response = http_requests.put(
                upload_url,
                data=chunk,
                headers={'Content-Type': content_type}
            )
            logger.info(f"[FILE UPLOAD] S3 response: status={response.status_code}, headers={dict(response.headers)}")
        except Exception as e:
            logger.error(f"[FILE UPLOAD] S3 upload exception: {str(e)}")
            return jsonify({
                'error': f'Failed to upload chunk {i + 1}: {str(e)}',
                'client_code': 500
            }), 500

        if not response.ok:
            logger.error(f"[FILE UPLOAD] S3 upload failed: status={response.status_code}, body={response.text}")
            return jsonify({
                'error': f'Failed to upload chunk {i + 1}: {response.text}',
                'client_code': 500
            }), 500

        # Get ETag from response headers
        etag = response.headers.get('ETag')
        logger.info(f"[FILE UPLOAD] Chunk {i + 1} uploaded, ETag={etag}")
        if etag:
            parts.append({
                'part_number': i + 1,
                'etag': etag
            })

    logger.info(f"[FILE UPLOAD] All chunks uploaded, parts={parts}")

    # Step 3: Complete multipart upload
    try:
        complete_result = api_client.complete_upload(
            file_id=file_id,
            parts=parts
        )
        logger.info(f"[FILE UPLOAD] Complete upload result: {complete_result}")
    except VagonAPIError as e:
        logger.error(f"[FILE UPLOAD] Complete upload failed: client_code={e.client_code}, status={e.status_code}, message={e.message}")
        raise

    return jsonify({
        'success': True,
        'id': file_id,
        'uid': complete_result.get('uid'),
        'download_url': complete_result.get('download_url')
    })


@app.route('/api/files/<int:file_id>/complete', methods=['POST'])
@handle_api_errors
def complete_upload(file_id):
    """
    Complete multipart upload.

    This demonstrates the complete_upload() API method.

    JSON body:
        {
            "parts": [
                {"part_number": 1, "etag": "\"etag1\""},
                {"part_number": 2, "etag": "\"etag2\""}
            ]
        }
    """
    logger.info(f"[COMPLETE UPLOAD] Completing upload for file_id={file_id}")
    # Use silent=True to avoid BadRequest exception if JSON is invalid or empty
    data = request.get_json(silent=True)
    
    if not data or 'parts' not in data:
        logger.error(f"[COMPLETE UPLOAD] Invalid or missing JSON data: {data}")
        return jsonify({'error': 'JSON body with "parts" array is required', 'client_code': 400, 'status_code': 400}), 400
    
    logger.info(f"[COMPLETE UPLOAD] Parts count: {len(data.get('parts', []))}")

    result = api_client.complete_upload(
        file_id=file_id,
        parts=data['parts']
    )
    logger.info(f"[COMPLETE UPLOAD] Success: file_id={file_id}")

    return jsonify({
        'success': True,
        'uid': result.get('uid'),
        'download_url': result.get('download_url')
    })


@app.route('/api/files/<int:file_id>/download')
@handle_api_errors
def get_download_url(file_id):
    """
    Get file download URL.

    This demonstrates the get_download_url() API method.
    """
    logger.info(f"[GET DOWNLOAD URL] Requesting download URL for file_id={file_id}")
    result = api_client.get_download_url(file_id)
    logger.info(f"[GET DOWNLOAD URL] Success: file_id={file_id}")
    return jsonify(result)


@app.route('/api/files/<int:file_id>', methods=['DELETE'])
@handle_api_errors
def delete_file(file_id):
    """
    Delete a file or directory.

    This demonstrates the delete_file() API method.
    """
    logger.info(f"[DELETE FILE] Deleting file_id={file_id}")
    try:
        result = api_client.delete_file(file_id)
        logger.info(f"[DELETE FILE] Success: file_id={file_id}, result={result}")
        return jsonify({'success': True, 'message': 'File deleted'}), 200
    except VagonAPIError as e:
        logger.error(f"[DELETE FILE] VagonAPIError: file_id={file_id}, client_code={e.client_code}, status={e.status_code}, message={e.message}")
        # This will be caught by handle_api_errors, but we log it here too
        raise
    except Exception as e:
        logger.error(f"[DELETE FILE] Unexpected error: file_id={file_id}, error={str(e)}, type={type(e).__name__}")
        # Return JSON error for API endpoints
        return jsonify({
            'error': str(e),
            'client_code': 500,
            'status_code': 500
        }), 500


@app.route('/api/files/capacity')
@handle_api_errors
def get_capacity():
    """
    Get storage capacity.

    This demonstrates the get_capacity() API method.
    """
    machine_id = request.args.get('machine_id', type=int)
    logger.info(f"[GET CAPACITY] Requesting capacity, machine_id={machine_id}")
    result = api_client.get_capacity(machine_id=machine_id)
    logger.info(f"[GET CAPACITY] Success: machine_id={machine_id}")
    return jsonify(result)


# =============================================================================
# MACHINE FILES API ROUTES
# =============================================================================

@app.route('/api/machines/<int:machine_id>/files')
@handle_api_errors
def get_machine_files(machine_id):
    """
    Get machine files.

    This demonstrates the get_machine_files() API method.
    """
    parent_id = request.args.get('parent_id', 0, type=int)
    page = request.args.get('page', 1, type=int)
    logger.info(f"[GET MACHINE FILES] machine_id={machine_id}, parent_id={parent_id}, page={page}")

    result = api_client.get_machine_files(
        machine_id=machine_id,
        parent_id=parent_id,
        page=page
    )
    logger.info(f"[GET MACHINE FILES] Success: machine_id={machine_id}, count={result.get('count', 0)}")

    return jsonify(result)


@app.route('/api/software')
@handle_api_errors
def list_software():
    """API endpoint to list available softwares and golden images."""
    try:
        result = api_client.list_softwares()
        # Flatten JSON:API format
        software = flatten_jsonapi_list(result.get('software', []))
        base_images = flatten_jsonapi_list(result.get('base_images', []))
        return jsonify({
            'softwares': software,  # Keep 'softwares' for frontend compatibility
            'base_images': base_images
        })
    except VagonAPIError as e:
        logger.error(f"Error fetching softwares: {e.message}")
        return jsonify({'error': e.message}), e.status_code


@app.route('/api/machines/create', methods=['POST'])
@handle_api_errors
def create_machine():
    """API endpoint to create new machines."""
    try:
        data = request.get_json()
        plan_id = data.get('plan_id') or data.get('seat_plan_id')  # Support both for backward compatibility
        quantity = data.get('quantity', 1)
        software_ids = data.get('software_ids', [])
        base_image_id = data.get('base_image_id')

        if not plan_id:
            return jsonify({'error': 'plan_id is required'}), 400

        permissions = data.get('permissions')
        
        result = api_client.create_machine(
            plan_id=plan_id,
            quantity=quantity,
            software_ids=software_ids if software_ids else None,
            base_image_id=base_image_id,
            permissions=permissions if permissions else None
        )
        return jsonify(result)
    except VagonAPIError as e:
        logger.error(f"Error creating machine: {e.message}")
        return jsonify({'error': e.message}), e.status_code


@app.route('/api/machines/permission-fields')
@handle_api_errors
def get_permission_fields():
    """API endpoint to get permission fields."""
    try:
        result = api_client.get_permission_fields()
        return jsonify(result)
    except VagonAPIError as e:
        logger.error(f"Error fetching permission fields: {e.message}")
        return jsonify({'error': e.message}), e.status_code


@app.route('/api/machines/<int:machine_id>/available-machine-types')
@handle_api_errors
def get_machine_available_machine_types(machine_id):
    """
    Get available machine types for a machine.

    This demonstrates the get_machine_available_machine_types() API method.
    """
    logger.info(f"[GET AVAILABLE MACHINE TYPES] machine_id={machine_id}")
    try:
        machine_types = api_client.get_machine_available_machine_types(machine_id)
        logger.info(f"[GET AVAILABLE MACHINE TYPES] Success: machine_id={machine_id}, count={len(machine_types)}")
        return jsonify({'machine_types': machine_types})
    except VagonAPIError as e:
        logger.error(f"[GET AVAILABLE MACHINE TYPES] Error: machine_id={machine_id}, client_code={e.client_code}, status={e.status_code}, message={e.message}")
        raise
    except Exception as e:
        logger.error(f"[GET AVAILABLE MACHINE TYPES] Unexpected error: machine_id={machine_id}, error={str(e)}")
        raise


@app.route('/api/machines/<int:machine_id>/permissions', methods=['POST'])
@handle_api_errors
def update_machine_permissions(machine_id):
    """
    Update permissions for a machine.

    This demonstrates the update_machine_permissions() API method.

    JSON body:
        {
            "permissions": {
                "screen_recording_enabled": true,
                "input_recording_enabled": false
            }
        }
    """
    logger.info(f"[UPDATE MACHINE PERMISSIONS] machine_id={machine_id}")
    # Use silent=True to avoid BadRequest exception if JSON is invalid or empty
    data = request.get_json(silent=True) or {}
    permissions = data.get('permissions')
    
    if not permissions:
        logger.error("[UPDATE MACHINE PERMISSIONS] Missing permissions parameter")
        return jsonify({
            'error': 'permissions parameter is required',
            'client_code': 400,
            'status_code': 400
        }), 400
    
    logger.info(f"[UPDATE MACHINE PERMISSIONS] Request: machine_id={machine_id}, permissions={permissions}")
    
    try:
        result = api_client.update_machine_permissions(
            machine_id=machine_id,
            permissions=permissions
        )
        logger.info(f"[UPDATE MACHINE PERMISSIONS] Success: machine_id={machine_id}")
        return jsonify({'success': True, 'message': 'Machine permissions updated'})
    except VagonAPIError as e:
        logger.error(f"[UPDATE MACHINE PERMISSIONS] Error: machine_id={machine_id}, client_code={e.client_code}, status={e.status_code}, message={e.message}")
        raise
    except Exception as e:
        logger.error(f"[UPDATE MACHINE PERMISSIONS] Unexpected error: machine_id={machine_id}, error={str(e)}")
        raise


# =============================================================================
# IMAGES API ROUTES
# =============================================================================

@app.route('/api/images')
@handle_api_errors
def list_images():
    """
    List all images (templates).

    This demonstrates the list_images() API method.
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    query = request.args.get('q', None)

    logger.info(f"[LIST IMAGES] page={page}, per_page={per_page}, query={query}")
    result = api_client.list_images(page=page, per_page=per_page, query=query)
    logger.info(f"[LIST IMAGES] Success: count={result.get('count', 0)}")

    # Flatten JSON:API format
    images = flatten_jsonapi_list(result.get('images', []))
    return jsonify({
        'images': images,
        'count': result.get('count', 0),
        'page': result.get('page', page),
        'next_page': result.get('next_page')
    })


@app.route('/api/images/<int:image_id>')
@handle_api_errors
def get_image(image_id):
    """
    Get image details.

    This demonstrates the get_image() API method.
    """
    logger.info(f"[GET IMAGE] image_id={image_id}")
    result = api_client.get_image(image_id)
    logger.info(f"[GET IMAGE] Success: image_id={image_id}")

    # Flatten JSON:API format
    image = flatten_jsonapi_resource(result)
    return jsonify(image)


@app.route('/api/images/install', methods=['POST'])
@handle_api_errors
def install_image():
    """
    Create a new image from pre-installation.

    This demonstrates the install_image() API method.

    JSON body:
        {
            "software_ids": [1, 2, 3],  // optional
            "base_image_id": 5,        // optional
            "name": "My Template"      // optional
        }
    """
    logger.info(f"[INSTALL IMAGE] Request received")
    data = request.get_json(silent=True) or {}

    software_ids = data.get('software_ids')
    base_image_id = data.get('base_image_id')
    name = data.get('name')

    logger.info(f"[INSTALL IMAGE] software_ids={software_ids}, base_image_id={base_image_id}, name={name}")

    result = api_client.install_image(
        software_ids=software_ids,
        base_image_id=base_image_id,
        name=name
    )
    logger.info(f"[INSTALL IMAGE] Success: result={result}")

    # Flatten JSON:API format
    image = flatten_jsonapi_resource(result)
    return jsonify(image)


@app.route('/api/images', methods=['POST'])
@handle_api_errors
def create_image():
    """
    Create a new image from a machine.

    This demonstrates the create_image() API method.

    JSON body:
        {
            "machine_id": 456,         // required
            "name": "My Template"      // optional
        }
    """
    logger.info(f"[CREATE IMAGE] Request received")
    data = request.get_json(silent=True) or {}

    machine_id = data.get('machine_id')
    name = data.get('name')

    if not machine_id:
        logger.error("[CREATE IMAGE] Missing machine_id parameter")
        return jsonify({
            'error': 'machine_id parameter is required',
            'client_code': 400,
            'status_code': 400
        }), 400

    logger.info(f"[CREATE IMAGE] machine_id={machine_id}, name={name}")

    result = api_client.create_image(
        machine_id=machine_id,
        name=name
    )
    logger.info(f"[CREATE IMAGE] Success: result={result}")

    # Flatten JSON:API format
    image = flatten_jsonapi_resource(result)
    return jsonify(image)


@app.route('/api/images/<int:image_id>/assign', methods=['POST'])
@handle_api_errors
def assign_image(image_id):
    """
    Assign an image to machines.

    This demonstrates the assign_image() API method.

    JSON body:
        {
            "machine_ids": [456, 789]  // required
        }
    """
    logger.info(f"[ASSIGN IMAGE] image_id={image_id}")
    data = request.get_json(silent=True) or {}

    machine_ids = data.get('machine_ids')
    if not machine_ids:
        logger.error("[ASSIGN IMAGE] Missing machine_ids parameter")
        return jsonify({
            'error': 'machine_ids parameter is required',
            'client_code': 400,
            'status_code': 400
        }), 400

    logger.info(f"[ASSIGN IMAGE] image_id={image_id}, machine_ids={machine_ids}")

    result = api_client.assign_image(
        image_id=image_id,
        machine_ids=machine_ids
    )
    logger.info(f"[ASSIGN IMAGE] Success: image_id={image_id}")

    return jsonify({'success': True, 'message': 'Image assigned to machines'})


@app.route('/api/images/<int:image_id>', methods=['DELETE'])
@handle_api_errors
def delete_image(image_id):
    """
    Delete an image.

    This demonstrates the delete_image() API method.
    """
    logger.info(f"[DELETE IMAGE] image_id={image_id}")
    result = api_client.delete_image(image_id)
    logger.info(f"[DELETE IMAGE] Success: image_id={image_id}")
    return jsonify({'success': True, 'message': 'Image deleted'})


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    # Check for API credentials
    if not os.getenv('VAGON_API_KEY') or not os.getenv('VAGON_API_SECRET'):
        print("\n" + "="*60)
        print("WARNING: API credentials not configured!")
        print("Please copy .env.example to .env and add your credentials.")
        print("="*60 + "\n")

    app.run(debug=True, port=5050)
    
