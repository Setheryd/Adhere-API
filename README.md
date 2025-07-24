# Adhere API

An API for processing X12 data for a list of members. This service accepts a list of member IDs, generates and sends X12 270 eligibility requests, and returns the results.

## Prerequisites

- Python 3.8+

## Setup and Installation

These steps will guide you through setting up the project in a properly encapsulated virtual environment.

### 1. Clone the Repository

```bash
git clone <https://github.com/Setheryd/Adhere-API.git>
cd Adhere-API
```

### 2. Create and Activate a Virtual Environment

Using a virtual environment is crucial to keep project dependencies isolated.

**On macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**On Windows:**
```bash
python -m venv venv
.\venv\Scripts\activate
```

After activation, you will see `(venv)` at the beginning of your command prompt line.

### 3. Install Dependencies

Install all the required Python packages from the `requirements.txt` file.

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

The API requires credentials to connect to the external service. Create a file named `.env` in the root of the project directory and add the necessary credentials. This file is listed in `.gitignore` and will not be committed to source control.

```
HCP_PASSWORD=your_secret_password_here
```

## Running the API

With the virtual environment active and dependencies installed, you can run the development server from the project root:

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

## Accessing the API Documentation

FastAPI automatically generates interactive API documentation (Swagger UI). Once the server is running, you can access it in your browser to test the endpoints:

-   **Swagger UI:** `http://127.0.0.1:8000/docs`