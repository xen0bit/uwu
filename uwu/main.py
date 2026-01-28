"""Main CLI entry point for OpenWebUI RAG upload tool."""

import json
import zipfile
from pathlib import Path
from typing import Optional

import click
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class OpenWebUIClient:
    """Client for interacting with OpenWebUI API."""

    def __init__(self, base_url: str, bearer_token: Optional[str] = None, cookie: Optional[str] = None):
        """Initialize the client with authentication."""
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        
        # Set up retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set authentication headers
        if bearer_token:
            self.session.headers.update({"Authorization": f"Bearer {bearer_token}"})
        
        if cookie:
            # Parse cookie string (format: "name=value" or "name=value; name2=value2")
            for cookie_pair in cookie.split(";"):
                cookie_pair = cookie_pair.strip()
                if "=" in cookie_pair:
                    name, value = cookie_pair.split("=", 1)
                    self.session.cookies.set(name.strip(), value.strip())
    
    def create_knowledge_collection(self, name: str, description: str) -> dict:
        """Create a new knowledge collection."""
        url = f"{self.base_url}/api/v1/knowledge/create"
        payload = {
            "name": name,
            "description": description,
            "access_control": None
        }
        
        response = self.session.post(url, json=payload)
        response.raise_for_status()
        return response.json()
    
    def upload_file(self, file_path: Path, process: bool = True, process_in_background: bool = True) -> dict:
        """Upload a file to OpenWebUI."""
        url = f"{self.base_url}/api/v1/files/"
        params = {
            "process": str(process).lower(),
            "process_in_background": str(process_in_background).lower()
        }
        
        with open(file_path, "rb") as f:
            # Let requests detect content type from filename
            response = self.session.post(
                url,
                files={"file": (file_path.name, f)},
                params=params,
                headers={"Accept": "application/json"}
            )
        
        response.raise_for_status()
        return response.json()
    
    def wait_for_file_processing(self, file_id: str, timeout: int = 300) -> dict:
        """Wait for file processing to complete using SSE stream."""
        url = f"{self.base_url}/api/v1/files/{file_id}/process/status"
        params = {"stream": "true"}
        
        response = self.session.get(url, params=params, stream=True, timeout=timeout)
        response.raise_for_status()
        
        # Parse SSE stream
        for line in response.iter_lines():
            if not line:
                continue  # Skip empty lines
            
            line = line.decode("utf-8").strip()
            if not line or not line.startswith("data: "):
                continue  # Skip non-data lines
            
            try:
                data = json.loads(line[6:])  # Remove "data: " prefix
                status = data.get("status")
                
                if status == "completed":
                    return data
                elif status == "failed":
                    error = data.get("error", "Unknown error")
                    raise Exception(f"File processing failed: {error}")
                # Continue for "pending" status
            except json.JSONDecodeError:
                continue
        
        raise Exception("Stream ended unexpectedly without completion")
    
    def add_file_to_knowledge(self, knowledge_id: str, file_id: str) -> dict:
        """Add a file to a knowledge collection."""
        url = f"{self.base_url}/api/v1/knowledge/{knowledge_id}/file/add"
        payload = {"file_id": file_id}
        
        response = self.session.post(url, json=payload)
        response.raise_for_status()
        return response.json()


@click.command()
@click.option(
    "--host",
    required=True,
    help="OpenWebUI host URL (e.g., http://localhost:3000)"
)
@click.option(
    "--bearer-token",
    required=True,
    help="Bearer token for authentication"
)
@click.option(
    "--cookie",
    default=None,
    help="Cookie string for authentication (optional, format: 'name=value' or 'name=value; name2=value2')"
)
@click.option(
    "--zip-file",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to the zip file to upload"
)
@click.option(
    "--timeout",
    default=300,
    type=int,
    help="Timeout in seconds for file processing (default: 300)"
)
def cli(host: str, bearer_token: str, cookie: Optional[str], zip_file: Path, timeout: int):
    """Upload contents of a zip file to OpenWebUI RAG endpoint."""
    
    # Extract name and description from zip filename
    zip_name = zip_file.stem  # filename without extension
    name = zip_name
    description = zip_name
    
    click.echo(f"Connecting to OpenWebUI at {host}...")
    client = OpenWebUIClient(host, bearer_token, cookie)
    
    # Step 1: Create knowledge collection
    click.echo(f"Creating knowledge collection '{name}'...")
    try:
        collection = client.create_knowledge_collection(name, description)
        collection_id = collection["id"]
        click.echo(f"✓ Created knowledge collection with ID: {collection_id}")
    except requests.exceptions.RequestException as e:
        click.echo(f"✗ Failed to create knowledge collection: {e}", err=True)
        if hasattr(e, "response") and e.response is not None:
            click.echo(f"  Response: {e.response.text}", err=True)
        raise click.Abort()
    
    # Step 2: Extract and upload files from zip
    click.echo(f"\nExtracting files from {zip_file}...")
    uploaded_files = []
    
    try:
        with zipfile.ZipFile(zip_file, "r") as zip_ref:
            file_list = zip_ref.namelist()
            click.echo(f"Found {len(file_list)} file(s) in archive")
            
            # Create temporary directory for extracted files
            import tempfile
            
            with tempfile.TemporaryDirectory() as temp_dir:
                for idx, file_path in enumerate(file_list, 1):
                    # Skip directories
                    if file_path.endswith("/"):
                        continue
                    
                    # Extract file
                    extracted_path = Path(temp_dir) / file_path
                    extracted_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    click.echo(f"\n[{idx}/{len(file_list)}] Processing: {file_path}")
                    
                    try:
                        # Extract file from zip
                        with zip_ref.open(file_path) as source, open(extracted_path, "wb") as target:
                            target.write(source.read())
                        
                        # Upload file
                        click.echo(f"  Uploading...")
                        file_data = client.upload_file(extracted_path)
                        file_id = file_data["id"]
                        click.echo(f"  ✓ Uploaded with ID: {file_id}")
                        
                        # Wait for processing
                        click.echo(f"  Waiting for processing...")
                        try:
                            client.wait_for_file_processing(file_id, timeout=timeout)
                            click.echo(f"  ✓ Processing completed")
                            
                            # Add to knowledge collection
                            click.echo(f"  Adding to knowledge collection...")
                            client.add_file_to_knowledge(collection_id, file_id)
                            click.echo(f"  ✓ Added to collection")
                            
                            uploaded_files.append((file_path, file_id))
                        except Exception as e:
                            click.echo(f"  ✗ Processing failed: {e}", err=True)
                            continue
                    
                    except Exception as e:
                        click.echo(f"  ✗ Failed to process {file_path}: {e}", err=True)
                        continue
    
    except zipfile.BadZipFile:
        click.echo(f"✗ Invalid zip file: {zip_file}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"✗ Error processing zip file: {e}", err=True)
        raise click.Abort()
    
    # Summary
    click.echo(f"\n{'='*60}")
    click.echo(f"Summary:")
    click.echo(f"  Knowledge Collection ID: {collection_id}")
    click.echo(f"  Files successfully uploaded: {len(uploaded_files)}/{len(file_list)}")
    if uploaded_files:
        click.echo(f"\n  Uploaded files:")
        for file_path, file_id in uploaded_files:
            click.echo(f"    - {file_path} (ID: {file_id})")


if __name__ == "__main__":
    cli()
