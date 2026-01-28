"""Main CLI entry point for OpenWebUI RAG upload tool."""

import time
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
    
    def get_file_processing_status(self, file_id: str) -> dict:
        """Get the current processing status of a file."""
        url = f"{self.base_url}/api/v1/files/{file_id}/process/status"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()
    
    def wait_for_file_processing(self, file_id: str, timeout: int = 300, poll_interval: int = 2) -> dict:
        """
        Wait for a file to finish processing using polling.
        
        Returns:
            dict: Final status with 'status' key ('completed' or 'failed')
        
        Raises:
            TimeoutError: If processing doesn't complete within timeout
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            result = self.get_file_processing_status(file_id)
            status = result.get("status")
            
            if status == "completed":
                return result
            elif status == "failed":
                error = result.get("error", "Unknown error")
                raise Exception(f"File processing failed: {error}")
            
            time.sleep(poll_interval)
        
        raise TimeoutError(f"File processing did not complete within {timeout} seconds")
    
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
@click.option(
    "--poll-interval",
    default=2,
    type=int,
    help="Polling interval in seconds for checking file status (default: 2)"
)
def cli(host: str, bearer_token: str, cookie: Optional[str], zip_file: Path, timeout: int, poll_interval: int):
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
    
    # Step 2: Extract files from zip and upload all files
    click.echo(f"\nExtracting files from {zip_file}...")
    file_info_list = []  # List of (file_path, extracted_path) tuples
    uploaded_files = []  # List of (file_path, file_id) tuples
    
    import tempfile
    
    try:
        with zipfile.ZipFile(zip_file, "r") as zip_ref:
            file_list = [f for f in zip_ref.namelist() if not f.endswith("/")]
            click.echo(f"Found {len(file_list)} file(s) in archive")
            
            # Create temporary directory for extracted files
            # Keep it open until all uploads are complete
            with tempfile.TemporaryDirectory() as temp_dir:
                # Extract all files
                for file_path in file_list:
                    extracted_path = Path(temp_dir) / file_path
                    extracted_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    with zip_ref.open(file_path) as source, open(extracted_path, "wb") as target:
                        target.write(source.read())
                    
                    file_info_list.append((file_path, extracted_path))
                
                # Step 3: Upload all files
                click.echo(f"\nUploading {len(file_info_list)} file(s)...")
                
                for idx, (file_path, extracted_path) in enumerate(file_info_list, 1):
                    click.echo(f"[{idx}/{len(file_info_list)}] Uploading: {file_path}")
                    try:
                        file_data = client.upload_file(extracted_path)
                        file_id = file_data["id"]
                        click.echo(f"  ✓ Uploaded with ID: {file_id}")
                        uploaded_files.append((file_path, file_id))
                    except Exception as e:
                        click.echo(f"  ✗ Failed to upload {file_path}: {e}", err=True)
                        continue
    
    except zipfile.BadZipFile:
        click.echo(f"✗ Invalid zip file: {zip_file}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"✗ Error processing zip file: {e}", err=True)
        raise click.Abort()
    
    if not uploaded_files:
        click.echo("✗ No files were successfully uploaded", err=True)
        raise click.Abort()
    
    # Step 4: Wait for all files to finish processing
    click.echo(f"\nWaiting for {len(uploaded_files)} file(s) to finish processing...")
    completed_files = []  # List of (file_path, file_id) tuples
    failed_files = []  # List of (file_path, file_id, error) tuples
    
    for file_path, file_id in uploaded_files:
        click.echo(f"Checking status: {file_path}")
        try:
            client.wait_for_file_processing(file_id, timeout=timeout, poll_interval=poll_interval)
            click.echo(f"  ✓ Processing completed")
            completed_files.append((file_path, file_id))
        except TimeoutError as e:
            click.echo(f"  ✗ Timeout: {e}", err=True)
            failed_files.append((file_path, file_id, str(e)))
        except Exception as e:
            click.echo(f"  ✗ Processing failed: {e}", err=True)
            failed_files.append((file_path, file_id, str(e)))
    
    if not completed_files:
        click.echo("✗ No files completed processing successfully", err=True)
        raise click.Abort()
    
    # Step 5: Add all completed files to knowledge collection
    click.echo(f"\nAdding {len(completed_files)} file(s) to knowledge collection...")
    added_files = []  # List of (file_path, file_id) tuples
    
    for file_path, file_id in completed_files:
        click.echo(f"Adding: {file_path}")
        try:
            client.add_file_to_knowledge(collection_id, file_id)
            click.echo(f"  ✓ Added to collection")
            added_files.append((file_path, file_id))
        except Exception as e:
            click.echo(f"  ✗ Failed to add {file_path}: {e}", err=True)
            continue
    
    # Summary
    click.echo(f"\n{'='*60}")
    click.echo(f"Summary:")
    click.echo(f"  Knowledge Collection ID: {collection_id}")
    click.echo(f"  Files extracted: {len(file_info_list)}")
    click.echo(f"  Files uploaded: {len(uploaded_files)}")
    click.echo(f"  Files completed processing: {len(completed_files)}")
    click.echo(f"  Files added to collection: {len(added_files)}")
    
    if added_files:
        click.echo(f"\n  Successfully added files:")
        for file_path, file_id in added_files:
            click.echo(f"    - {file_path} (ID: {file_id})")
    
    if failed_files:
        click.echo(f"\n  Failed files:")
        for file_path, file_id, error in failed_files:
            click.echo(f"    - {file_path} (ID: {file_id}): {error}")


if __name__ == "__main__":
    cli()
