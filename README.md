# uwu

A CLI tool to upload zip files to OpenWebUI's RAG (Retrieval Augmented Generation) endpoint. Automatically extracts files from zip archives, uploads them to OpenWebUI, waits for processing, and adds them to a knowledge collection.

## Features

- 📦 Upload zip files from local filesystem or download from URLs
- 🔄 Batch processing: Upload all files, then monitor processing status
- 🔐 Supports both Bearer token and cookie-based authentication
- 📊 Progress tracking and detailed status reporting
- 🧹 Automatic cleanup of temporary files
- ⚡ Efficient polling-based status monitoring

## Installation

This project uses [uv](https://github.com/astral-sh/uv) for package management.

```bash
# Install dependencies
uv sync

# The CLI will be available as `uwu` after installation
```

## Usage

### Basic Usage

```bash
uv run uwu \
  --host http://localhost:3000 \
  --bearer-token YOUR_API_TOKEN \
  --zip-file knowledge.zip
```

### With Cookie Authentication

```bash
uv run uwu \
  --host http://localhost:3000 \
  --bearer-token YOUR_API_TOKEN \
  --cookie "session=abc123" \
  --zip-file knowledge.zip
```

### Download and Upload from URL

```bash
uv run uwu \
  --host http://localhost:3000 \
  --bearer-token YOUR_API_TOKEN \
  --zip-file "https://github.com/acmesh-official/acme.sh/archive/refs/heads/master.zip"
```

### Custom Timeout and Poll Interval

```bash
uv run uwu \
  --host http://localhost:3000 \
  --bearer-token YOUR_API_TOKEN \
  --zip-file knowledge.zip \
  --timeout 600 \
  --poll-interval 5
```

## Command-Line Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--host` | Yes | - | OpenWebUI host URL (e.g., `http://localhost:3000`) |
| `--bearer-token` | Yes | - | Bearer token for authentication |
| `--cookie` | No | - | Cookie string for authentication (format: `name=value` or `name=value; name2=value2`) |
| `--zip-file` | Yes | - | Path to local zip file or URL to download zip from |
| `--timeout` | No | 300 | Timeout in seconds for file processing |
| `--poll-interval` | No | 2 | Polling interval in seconds for checking file status |
| `--help` | No | - | Show help message and exit |

## How It Works

1. **Create Knowledge Collection**: Creates a new knowledge collection in OpenWebUI using the zip filename (or URL-derived name) as the collection name.

2. **Extract Files**: Extracts all files from the zip archive to a temporary directory.

3. **Upload Files**: Uploads all files to OpenWebUI in sequence, collecting file IDs.

4. **Monitor Processing**: Polls the processing status of all uploaded files until they complete or fail.

5. **Add to Collection**: Adds all successfully processed files to the knowledge collection.

6. **Cleanup**: Automatically removes temporary files (including downloaded zip files from URLs).

## Examples

### Example 1: Upload Local Zip File

```bash
uv run uwu \
  --host http://localhost:3000 \
  --bearer-token sk-1234567890abcdef \
  --zip-file ./documents.zip
```

This will:
- Create a knowledge collection named "documents"
- Extract and upload all files from `documents.zip`
- Wait for processing to complete
- Add files to the collection

### Example 2: Download and Process GitHub Repository

```bash
uv run uwu \
  --host http://localhost:3000 \
  --bearer-token sk-1234567890abcdef \
  --zip-file "https://github.com/user/repo/archive/refs/heads/main.zip"
```

This will:
- Download the zip file from GitHub
- Create a knowledge collection named "main" (derived from the URL)
- Process all files in the repository archive

### Example 3: With Custom Authentication

```bash
uv run uwu \
  --host https://openwebui.example.com \
  --bearer-token sk-1234567890abcdef \
  --cookie "session_id=abc123; csrf_token=xyz789" \
  --zip-file ./data.zip
```

## Output

The tool provides detailed progress information:

```
Connecting to OpenWebUI at http://localhost:3000...
Creating knowledge collection 'knowledge'...
✓ Created knowledge collection with ID: 47e90d0b-2712-405f-98e3-e291d29ec56f

Extracting files from knowledge.zip...
Found 5 file(s) in archive

Uploading 5 file(s)...
[1/5] Uploading: document1.pdf
  ✓ Uploaded with ID: file-id-1
[2/5] Uploading: document2.txt
  ✓ Uploaded with ID: file-id-2
...

Waiting for 5 file(s) to finish processing...
Checking status: document1.pdf
  ✓ Processing completed
...

Adding 5 file(s) to knowledge collection...
Adding: document1.pdf
  ✓ Added to collection
...

============================================================
Summary:
  Knowledge Collection ID: 47e90d0b-2712-405f-98e3-e291d29ec56f
  Files extracted: 5
  Files uploaded: 5
  Files completed processing: 5
  Files added to collection: 5

  Successfully added files:
    - document1.pdf (ID: file-id-1)
    - document2.txt (ID: file-id-2)
    ...
```

## Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager
- OpenWebUI instance with RAG endpoints enabled
- Valid API token or authentication credentials

## Error Handling

The tool handles various error scenarios:

- **Invalid zip files**: Reports error and exits
- **Network errors**: Retries with exponential backoff
- **Processing failures**: Continues with other files and reports failures in summary
- **Authentication errors**: Reports detailed error messages
- **Timeouts**: Reports timeout errors for individual files

Failed files are tracked separately and reported in the summary, allowing partial success scenarios.

## License

See project license file for details.
