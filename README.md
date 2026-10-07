# GradeFlow: Smart Exam Evaluation Platform

AI-assisted evaluation of handwritten answer scripts using Google Gemini,
Flask and MySQL. Teachers upload a question paper and marking scheme; the
system extracts the exam structure (including OR choices and "answer any N"
rules), grades scanned student answer booklets, and lets the teacher review
and override marks.

> B.Tech Project, Dept. of Information Technology, Government Engineering
> College Palakkad (APJ Abdul Kalam Technological University), 2025-26.

## Features
- Teacher signup/login, class and exam management
- Automatic question-paper parsing into structured JSON (Gemini)
- Handwritten answer grading against the marking scheme with a strict rubric
- OR-group / pick-count logic for correct total calculation
- Split-screen evaluation page with manual mark override and live recalculation

## Tech Stack
Python, Flask, MySQL, Google Gemini API, HTML/CSS, Bootstrap, JavaScript, Jinja2

## How It Works
1. **Exam creation:** upload QP + answer key → Gemini returns exam structure → stored in `exam_questions`.
2. **Evaluation:** upload student booklet → Gemini grades per question → `calculate_total` applies OR/pick-count rules.
3. **Review:** teacher checks AI marks and overrides if needed.

## Screenshots
![Dashboard](docs/dashboard.png)
![Evaluation](docs/evaluation.png)

## Setup
1. Clone the repo

git clone https://github.com/<Vishnu-I-T>/GradeFlow.git
cd GradeFlow

2. Create a virtual environment and install dependencies

python -m venv venv
venv\Scripts\activate # Windows
source venv/bin/activate # Linux/Mac
pip install -r requirements.txt

3. Create the database: run `schema.sql` in MySQL.
4. Copy `.env.example` to `.env` and fill in your Gemini API key
   (get one at https://aistudio.google.com/app/apikey) and DB details.
5. Run `python app.py` and open http://127.0.0.1:5000

## Known Limitations
- Passwords are stored in plain text (hashing planned)
- No per-teacher authorization checks on some routes
- Free-tier Gemini rate limits; weaker on highly descriptive answers
- Requires internet access for the AI API

## Team
- Vishnu I T: AI & API integration
- Adithya Manoj: Backend
- Raseena R: Database
- Sharfeena S: Frontend

Guide: Prof. Sasinas Alias Haritha

## License
MIT (or your choice)
