# News Extraction and Aggregation Pipeline

## Description
This repository contains a robust, automated pipeline that extracts news articles from various top Indian news sites, generates vector embeddings for their content, and intelligently groups related articles into clustered topics using an AI similarity engine. It also exposes a RESTful FastAPI layer for an editorial UI to browse grouped articles and for schedulers to trigger the extraction jobs.

## Structure
- `api/`: FastAPI application containing all routing logic, pydantic models, and dependencies.
- `fetchers/`: Site-specific crawler scripts utilizing standard sitemaps.
- `pipeline/`: Core logic for text embedding (Cohere) and database connection operations.
- `logs/`: Timestamped JSON logs containing reports of each pipeline run.
- `main.py`: CLI entrypoint to manually trigger the pipeline.
- `server.py`: Uvicorn entrypoint for the FastAPI application.

---

## How to Run Locally

### 1. Requirements
- Python 3.10+
- PostgreSQL database with the `pgvector` extension installed.

### 2. Setup
Clone the repository, create a virtual environment, and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # Or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
```

### 3. Environment Variables
Create a `.env` file based on `.env.example`:
```env
SUPABASE_HOST=your_host
SUPABASE_PORT=5432
SUPABASE_DB=postgres
SUPABASE_USER=postgres
SUPABASE_PASSWORD=your_password
COHERE_API_KEY=your_cohere_key
API_HOST=0.0.0.0
API_PORT=8000
API_PREFIX=/api/v1
```

### 4. Running the Server
```bash
python server.py
```
*The API will be available at `http://localhost:8000`. Auto-generated Swagger docs are at `/docs`.*

---

## Pipeline Functionality (What Runs in What Order)

1. **Trigger:** The pipeline is initiated either manually via `python main.py` or through an automated scheduler calling the `POST /api/v1/pipeline/run` endpoint.
2. **Fetching:** The script iterates through the 6 predefined sources (News18, TOI, HT, Indian Express, ZeeNews, NDTV) and downloads their latest sitemap XMLs.
3. **Deduplication:** For each extracted article, it checks the database. If the `url_loc` already exists, the article is skipped.
4. **Embedding:** The article text (title + description) is sent to the Cohere API to generate a 512-dimensional vector embedding. Jaccard keywords are also extracted.
5. **Grouping (The Brain):**
   - **Phase 1 (Jaccard Pre-filter):** The article's keywords are compared against all active group keywords.
   - **Phase 2 (Vector Search):** If Jaccard similarity is high enough, the article's embedding is compared against the *anchor embeddings* of potential Jaccard matches using `pgvector` Cosine Distance (`<=>`).
6. **Database Write:** 
   - If a match is found (`similarity >= 0.67`), the article is assigned to that group and the group's keywords and `last_updated_at` timestamps are updated.
   - If no match is found, a new `article_group` is created, establishing its embedding as the permanent "anchor."
   - Finally, the article itself is saved to the `articles` table.
7. **Logging:** A JSON report of the entire run is saved to the `logs/` directory.

---

## API Documentation

### 1. Health Check
Checks if the database is reachable.
- **Method:** `GET`
- **URL:** `/api/v1/health`
- **Sample Request:**
  ```bash
  curl -X GET http://localhost:8000/api/v1/health
  ```
- **Output JSON Format:**
  ```json
  {
    "status": "healthy",
    "checks": {
      "database": "ok",
      "cohere_key_present": true
    },
    "version": "1.0.0",
    "timestamp": "2026-05-15T10:00:00+00:00"
  }
  ```

### 2. Trigger Pipeline Run
Executes the extraction script.
- **Method:** `POST`
- **URL:** `/api/v1/pipeline/run`
- **Sample Request:**
  ```bash
  curl -X POST http://localhost:8000/api/v1/pipeline/run \
       -H "Content-Type: application/json" \
       -d '{"sources": ["ndtv"], "limit": 10}'
  ```
- **Input JSON Format (Optional):**
  ```json
  {
    "sources": ["news18", "toi", "ht", "indianexpress", "zeenews", "ndtv"],
    "limit": 10
  }
  ```
- **Output JSON Format:**
  ```json
  {
    "run_id": "20260515_100000",
    "started_at": "...",
    "finished_at": "...",
    "duration_seconds": 15.5,
    "sources_processed": ["ndtv"],
    "sources_failed": [],
    "summary": {
      "total_fetched": 10,
      "total_inserted": 5,
      "total_skipped_duplicate": 5,
      "total_errors": 0,
      "new_groups_created": 2,
      "articles_grouped": 3
    },
    "log_file": "logs/20260515_100000.json",
    "per_source": { }
  }
  ```

### 3. List Past Pipeline Runs
Retrieves a paginated list of all log files.
- **Method:** `GET`
- **URL:** `/api/v1/pipeline/runs?limit=10&page=1`
- **Sample Request:**
  ```bash
  curl -X GET "http://localhost:8000/api/v1/pipeline/runs?limit=10&page=1"
  ```
- **Output JSON Format:**
  ```json
  {
    "runs": [
      {
        "run_id": "20260515_100000",
        "log_file": "logs/20260515_100000.json",
        "size_bytes": 15000
      }
    ],
    "total": 1
  }
  ```

### 4. Fetch Specific Pipeline Run
Retrieves the full JSON report for a single extraction run.
- **Method:** `GET`
- **URL:** `/api/v1/pipeline/runs/{run_id}`
- **Sample Request:**
  ```bash
  curl -X GET http://localhost:8000/api/v1/pipeline/runs/20260515_100000
  ```
- **Output JSON Format:** *(Directly returns the contents of the log file)*
  ```json
  [
    {
      "article": { "title": "...", "url": "..." },
      "scoring": { },
      "final_action": "new_group",
      "assigned_id": 42
    }
  ]
  ```

### 5. List Grouped Articles (MAIN)
Primary endpoint for the UI. Retrieves active clustered groups sorted by most recently updated.
- **Method:** `GET`
- **URL:** `/api/v1/articles/groups?limit=20&page=1&active_only=true`
- **Sample Request:**
  ```bash
  curl -X GET "http://localhost:8000/api/v1/articles/groups?limit=20"
  ```
- **Output JSON Format:**
  ```json
  {
    "groups": [
      {
        "group_id": 42,
        "topic_label": "Petrol minister Puri highlights mounting losses...",
        "article_count": 3,
        "last_updated_at": "2026-05-15T10:00:00+00:00",
        "expires_at": "2026-05-17T10:00:00+00:00",
        "articles": [
          {
            "id": 100,
            "title": "Petrol minister Puri highlights mounting losses...",
            "url_loc": "https://...",
            "source": "toi",
            "group_id": 42,
            "publication_date": "2026-05-15T09:30:00+00:00"
          }
        ]
      }
    ],
    "total": 1,
    "page": 1,
    "limit": 20
  }
  ```

### 6. View Single Group
Expand a single group to see all of its associated articles.
- **Method:** `GET`
- **URL:** `/api/v1/articles/groups/{group_id}`
- **Sample Request:**
  ```bash
  curl -X GET http://localhost:8000/api/v1/articles/groups/42
  ```
- **Output JSON Format:**
  ```json
  {
    "group_id": 42,
    "topic_label": "Petrol minister Puri highlights mounting losses...",
    "article_count": 3,
    "last_updated_at": "2026-05-15T10:00:00+00:00",
    "expires_at": "2026-05-17T10:00:00+00:00",
    "articles": [
      {
        "id": 100,
        "title": "Petrol minister Puri highlights mounting losses...",
        "url_loc": "https://...",
        "source": "toi",
        "group_id": 42,
        "publication_date": "2026-05-15T09:30:00+00:00"
      }
    ]
  }
  ```

### 7. Raw Article Search/Filter
Secondary endpoint to query all stored articles individually with filtering.
- **Method:** `GET`
- **URL:** `/api/v1/articles?source=news18&limit=10&page=1`
- **Sample Request:**
  ```bash
  curl -X GET "http://localhost:8000/api/v1/articles?source=news18"
  ```
- **Output JSON Format:**
  ```json
  {
    "articles": [
      {
        "id": 99,
        "title": "Some raw article title",
        "url_loc": "https://...",
        "source_id": 1,
        "group_id": 12,
        "publication_date": "2026-05-15T09:00:00+00:00",
        "image_loc": "https://..."
      }
    ],
    "total": 500,
    "page": 1,
    "limit": 10
  }
  ```
