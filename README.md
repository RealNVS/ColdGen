# ColdGen

ColdGen is a small Flask app that scrapes a job description and generates a tailored cold email using Groq.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Add your Groq API key to `.env`:

```env
GROQ_API_KEY=your_groq_api_key_here
```

## Run

```powershell
python main.py
```

Open `http://127.0.0.1:5000`.

## Project Structure

```text
.
├── chains.py
├── main.py
├── portfolio.py
├── requirements.txt
├── resource/
│   └── project_portfolio.csv
├── templates/
│   ├── 404.html
│   ├── 500.html
│   └── index.html
└── utils.py
```
