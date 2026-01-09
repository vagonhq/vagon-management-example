# Vagon Computer API Example

This project is a Python Flask project to showcase Vagon Computer APIs and their functionalities for the teams looking for a custom dashboard implementation. 

## Features

- **Computer Management**: List and view all computers with their associated seat information
- **Computer Control**: Start, stop, and create access links for computers
- **File Management**: Browse, upload, and download files (organization-wide and computer-specific)
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

# Create access link
access = client.create_machine_access(machine_id=123, expires_in=3600)
print(f"Access link: {access['connection_link']}")

# List organization files
files = client.list_files(parent_id=0)
for f in files['files']:
    print(f"{f['name']} ({f['object_type']})")

# Get storage capacity
capacity = client.get_capacity()
print(f"Used: {capacity['in_use']} / {capacity['total']} bytes")
```

## API Endpoints Reference for this Project

### Computers
- `GET /` - List all computers
- `GET /seats/<id>` - Computer details with files

### Machines (JSON API)
- `POST /api/machines/<id>/start` - Start computer
- `POST /api/machines/<id>/stop` - Stop computer
- `POST /api/machines/<id>/access` - Create access link to running computer

### Files (JSON API)
- `GET /api/files/capacity` - Get storage capacity
- `POST /api/files` - Create file or directory
- `GET /api/files/<id>/download` - Get download URL
- `POST /api/files/<id>/complete` - Complete multipart upload
- `DELETE /api/files/<id>` - Delete file or directory