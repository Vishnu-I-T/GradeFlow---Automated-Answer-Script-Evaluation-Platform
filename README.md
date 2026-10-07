# GradeFlow: Smart Exam Evaluation Platform

AI-assisted evaluation of handwritten answer scripts using Google Gemini,
Flask and MySQL. Teachers upload a question paper and marking scheme; the
system extracts the exam structure (including OR choices and "answer any N"
rules), grades scanned student answer booklets, and lets the teacher review
and override marks.

> B.Tech Project, Dept. of Information Technology, Government Engineering
> College Palakkad (APJ Abdul Kalam Technological University), 2025-26.

## Features
- Teacher signup/login (hashed passwords), class and exam management
- Automatic question-paper parsing into structured JSON (Gemini)
- Handwritten answer grading against the marking scheme with a strict rubric
- OR-group / pick-count logic for correct total calculation
- Split-screen evaluation page with manual mark override and live recalculation

## Tech Stack
Python, Flask, MySQL, Google Gemini API, HTML/CSS, Bootstrap, JavaScript, Jinja2

## Screenshots
![Dashboard](docs/dashboard.png)
![Evaluation](docs/evaluation.png)

## Setup

**Prerequisites:** Python 3.9+, MySQL Server (or XAMPP), a Gemini API key
from https://aistudio.google.com/app/apikey

1. Clone the repo
```bash
   git clone https://github.com/Vishnu-I-T/GradeFlow---Automated-Answer-Script-Evaluation-Platform.git
   cd GradeFlow---Automated-Answer-Script-Evaluation-Platform
```
2. Create a virtual environment and install dependencies
```bash
   python -m venv venv
   venv\Scripts\activate          # Windows
   source venv/bin/activate       # Linux/Mac
   pip install -r requirements.txt
```
3. Create the database
```bash
   mysql -u root -p < schema.sql
```
4. Copy `.env.example` to `.env` and fill in your values
```bash
   cp .env.example .env
```
5. Run the app
```bash
   python app.py
```
   Open http://127.0.0.1:5000

## Environment Variables
| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Your Google Gemini API key |
| `FLASK_SECRET_KEY` | Long random string for session signing |
| `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | MySQL connection details |
| `FLASK_DEBUG` | Set to `1` for local development only |

## Known Limitations
- Depends on Gemini free-tier rate limits and needs internet access
- AI grading is weaker on highly descriptive, open-ended answers; manual review is recommended
- No HTTPS or rate limiting (planned for production deployment)

## Team
- Vishnu I T: AI and API integration
- Adithya Manoj: Backend
- Raseena R: Database
- Sharfeena S: Frontend

Guide: Prof. Sasinas Alias Haritha

## License
MIT. See [LICENSE](LICENSE).
