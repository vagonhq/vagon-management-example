# Vagon Computer API Example

This project is a Python Flask project to showcase Vagon Computer APIs and their functionalities for the teams looking for a custom dashboard implementation. 

## Features

- **Computer Management**: List and view all computers with their associated seat information
- **Computer Control**: Start, stop, reset, and create access links for computers
- **Machine Configuration**: Change machine type and view available machine types
- **File Management**: Browse, upload, and download files (organization-wide and computer-specific)
- **User Action Logs**: View activity logs for machines and users
- **Software Management**: List available softwares and golden images
- **Seat Management**: Create new seats with software pre-installation
- **Clean API Client**: Well-documented Python client for the Vagon API

## Project Structure

```
vagon-computer-api-example/
├── vagon_api.py          # Vagon API client
├── app.py                # Flask application with API routes
├── templates/
│   ├── base.html         # Base template with Tailwind CSS
│   ├── index.html        # Computers list page
│   ├── seat_detail.html  # Computer details and files
│   └── files.html        # Shared files directory
├── requirements.txt      # Python dependencies
├── .env.example          # Environment variables template
└── README.md
```

## Setup

1. **Clone and navigate to the project:**
   ```bash
   cd vagon-management-example
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and add your Vagon API credentials:
   ```
   VAGON_API_KEY=your_api_key
   VAGON_API_SECRET=your_api_secret
   VAGON_BASE_URL=https://api.vagon.io
   ```

5. **Run the application:**
   ```bash
   python app.py
   ```

6. **Open in browser:**
   ```
   http://localhost:5000
   ```

## API Client Usage

The `vagon_api.py` module can be used independently:

```python
from vagon_api import VagonAPI

# Initialize client
client = VagonAPI(
    api_key="your_api_key",
    api_secret="your_api_secret"
)

# List seats
seats = client.list_seats(page=1, per_page=20)
for seat in seats['seats']:
    print(f"{seat['name']}: {seat['status']}")

# Start a machine
client.start_machine(machine_id=123)

# Stop a machine
client.stop_machine(machine_id=123)

# Reset a stopped machine (deletes images, terminates instance, resets to silver image)
client.reset_machine(machine_id=123)

# Change machine type
client.set_machine_type(machine_id=123, machine_type_id=5)

# Get available machine types for a seat
machine_types = client.get_seat_available_machine_types(seat_id=456)

# Create access link (expires_in in seconds)
access = client.create_machine_access(machine_id=123, expires_in=3600)
print(f"Access link: {access['connection_link']}")

# List organization files
files = client.list_files(parent_id=0)
for f in files['files']:
    print(f"{f['name']} ({f['object_type']})")

# Get storage capacity
capacity = client.get_capacity()
print(f"Used: {capacity['in_use']} / {capacity['total']} bytes")

# View user action logs
from datetime import datetime, timedelta
start_date = (datetime.now() - timedelta(days=7)).iso8601()
end_date = datetime.now().iso8601()
logs = client.list_user_action_logs(
    start_date=start_date,
    end_date=end_date,
    organization_machine_id=123
)

# List available softwares
result = client.list_softwares()
for software in result['software']:
    print(f"{software['name']}: {software['size']} GB")

# Create a new seat
result = client.create_seat(
    seat_plan_id=1,
    quantity=2,
    software_ids=[1, 2, 3]
)
print(f"Created {result['count']} seats")
```

## API Endpoints Reference for this Project

### Web Pages
- `GET /` - List all computers (seats)
- `GET /seats/<id>` - Computer details with files
- `GET /files` - Browse organization-wide shared files
- `GET /logs` - View user action logs with filters

### Machines (JSON API)
- `GET /api/machines/<id>` - Get machine details
- `POST /api/machines/<id>/start` - Start computer
  - Optional body: `{"machine_type_id": 5, "region": "dublin"}`
- `POST /api/machines/<id>/stop` - Stop computer
- `POST /api/machines/<id>/reset` - Reset stopped computer
  - Deletes all machine images, terminates instance, resets to silver image if assigned
- `POST /api/machines/<id>/access` - Create access link to running computer
  - Body: `{"expires_in": 3600}` (expires_in in seconds)
- `POST /api/machines/<id>/machine-type` - Change machine type
  - Body: `{"machine_type_id": 5}`

### Seats (JSON API)
- `GET /api/seats/<id>/available-machine-types` - Get available machine types for seat
- `POST /api/seats/create` - Create new seats
  - Body: `{"seat_plan_id": 1, "quantity": 2, "software_ids": [1,2,3]}`
- `GET /api/seats/<id>/files` - Get seat-specific files

### Files (JSON API)
- `GET /api/files/capacity` - Get storage capacity
  - Optional query: `?seat_id=123` for seat-specific capacity
- `POST /api/files` - Create file or directory
- `POST /api/files/upload` - Upload file (multipart)
- `GET /api/files/<id>/download` - Get download URL
- `POST /api/files/<id>/complete` - Complete multipart upload
- `DELETE /api/files/<id>` - Delete file or directory

### User Action Logs (JSON API)
- `GET /api/user-action-logs` - Get recent logs (last 30 days)
  - Query params: `start_date`, `end_date`, `action_type`, `user_email`, `organization_machine_id`
- `GET /api/user-action-logs/archived-download-urls` - Get archived logs (older than 30 days)
  - Query params: `start_date`, `end_date`, `expires_in`

### Software Management (JSON API)
- `GET /api/software` - List available softwares and golden images