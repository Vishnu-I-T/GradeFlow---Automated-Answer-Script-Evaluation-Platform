import os
import time
import json
import uuid
from functools import wraps

import mysql.connector
import google.generativeai as genai
from dotenv import load_dotenv
from flask import (Flask, render_template, request, redirect, url_for,
                   session, jsonify)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
app.secret_key = os.getenv("FLASK_SECRET_KEY")
if not app.secret_key:
    raise RuntimeError(
        "FLASK_SECRET_KEY is not set. Copy .env.example to .env and fill it in."
    )

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is not set. Copy .env.example to .env and fill it in."
    )
genai.configure(api_key=GEMINI_API_KEY)

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB per request
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "smart_exam_db"),
    )


def login_required(f):
    """Redirect to login if no teacher is logged in."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


# Ownership helpers: each returns the row only if it belongs to the
# logged-in teacher, otherwise None.
def get_owned_class(cursor, class_id):
    cursor.execute(
        "SELECT * FROM classes WHERE id = %s AND teacher_id = %s",
        (class_id, session['user_id']))
    return cursor.fetchone()


def get_owned_exam(cursor, exam_id):
    cursor.execute(
        """SELECT e.* FROM exams e
           JOIN classes c ON e.class_id = c.id
           WHERE e.id = %s AND c.teacher_id = %s""",
        (exam_id, session['user_id']))
    return cursor.fetchone()


def get_owned_student(cursor, student_id):
    cursor.execute(
        """SELECT s.* FROM students s
           JOIN exams e ON s.exam_id = e.id
           JOIN classes c ON e.class_id = c.id
           WHERE s.id = %s AND c.teacher_id = %s""",
        (student_id, session['user_id']))
    return cursor.fetchone()


def save_upload(file_storage):
    """Save an uploaded file with a unique, sanitized name. Returns (filename, path)."""
    original = secure_filename(file_storage.filename)
    filename = f"{uuid.uuid4().hex[:8]}_{original}"
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file_storage.save(path)
    return filename, path


def is_pdf(file_storage):
    return bool(file_storage and file_storage.filename and
                file_storage.filename.lower().endswith('.pdf'))


def generate_safe(inputs, prompt):
    """Call Gemini with retry on rate-limit (429) errors."""
    models_to_try = ['gemini-flash-latest']
    for model_name in models_to_try:
        try:
            print(f"Connecting to AI Model: {model_name}...")
            model = genai.GenerativeModel(model_name)
            for attempt in range(3):
                try:
                    return model.generate_content(inputs + [prompt])
                except Exception as e:
                    if "429" in str(e):
                        print(f"Quota hit. Waiting 15s... (Attempt {attempt + 1})")
                        time.sleep(15)
                        continue
                    break
        except Exception:
            continue
    raise ValueError("All AI Models failed.")


def extract_json(text):
    """Extract a JSON list or dict from an AI response."""
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        start = text.find('[')
        end = text.rfind(']') + 1
        if start != -1 and end != 0:
            return json.loads(text[start:end])
        start = text.find('{')
        end = text.rfind('}') + 1
        if start != -1 and end != 0:
            return json.loads(text[start:end])
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO teachers (name, email, password) VALUES (%s, %s, %s)",
                (request.form['name'], request.form['email'],
                 generate_password_hash(request.form['password'])))
            conn.commit()
        except mysql.connector.IntegrityError:
            conn.close()
            return render_template('signup.html',
                                   error="Email already registered")
        conn.close()
        return redirect(url_for('login'))
    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM teachers WHERE email = %s",
                       (request.form['email'],))
        user = cursor.fetchone()
        conn.close()
        if user and check_password_hash(user['password'],
                                        request.form['password']):
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            return redirect(url_for('dashboard'))
        return render_template('login.html',
                               error="Invalid email or password")
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


# ---------------------------------------------------------------------------
# Dashboard, profile and classes
# ---------------------------------------------------------------------------
@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM classes WHERE teacher_id = %s",
                   (session['user_id'],))
    classes = cursor.fetchall()
    conn.close()
    return render_template('dashboard.html', classes=classes,
                           user=session['user_name'])


@app.route('/edit_profile', methods=['POST'])
@login_required
def edit_profile():
    new_name = request.form['name']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE teachers SET name = %s WHERE id = %s",
                   (new_name, session['user_id']))
    conn.commit()
    conn.close()
    session['user_name'] = new_name
    return redirect(url_for('dashboard'))


@app.route('/add_class', methods=['POST'])
@login_required
def add_class():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO classes (teacher_id, name, subject, semester, year)
           VALUES (%s, %s, %s, %s, %s)""",
        (session['user_id'], request.form['name'], request.form['subject'],
         request.form['sem'], request.form['year']))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))


@app.route('/delete_class/<int:class_id>')
@login_required
def delete_class(class_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    if get_owned_class(cursor, class_id):
        cursor.execute("DELETE FROM classes WHERE id = %s", (class_id,))
        conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))


@app.route('/edit_class', methods=['POST'])
@login_required
def edit_class():
    class_id = request.form['class_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    if get_owned_class(cursor, class_id):
        cursor.execute(
            """UPDATE classes
               SET name = %s, subject = %s, semester = %s, year = %s
               WHERE id = %s""",
            (request.form['name'], request.form['subject'],
             request.form['sem'], request.form['year'], class_id))
        conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))


@app.route('/class/<int:class_id>')
@login_required
def class_view(class_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    class_info = get_owned_class(cursor, class_id)
    if not class_info:
        conn.close()
        return "<h1>Class Not Found</h1>", 404
    cursor.execute("SELECT * FROM exams WHERE class_id = %s", (class_id,))
    exams = cursor.fetchall()
    conn.close()
    return render_template('class_view.html', class_info=class_info,
                           exams=exams)


# ---------------------------------------------------------------------------
# Exams
# ---------------------------------------------------------------------------
@app.route('/exam/<int:exam_id>')
@login_required
def exam_view(exam_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    exam = get_owned_exam(cursor, exam_id)
    if not exam:
        conn.close()
        return "<h1>Exam Not Found</h1>", 404

    # Sorted numerically by roll number; duplicate roll numbers are hidden.
    cursor.execute(
        "SELECT * FROM students WHERE exam_id = %s "
        "ORDER BY CAST(roll_no AS UNSIGNED) ASC", (exam_id,))
    raw_students = cursor.fetchall()
    conn.close()

    seen_rolls = set()
    students = []
    for student in raw_students:
        if student['roll_no'] not in seen_rolls:
            students.append(student)
            seen_rolls.add(student['roll_no'])

    return render_template('exam_view.html', exam=exam, students=students)


@app.route('/add_exam', methods=['POST'])
@login_required
def add_exam():
    """Create an exam and use Gemini to extract its structure from the QP."""
    class_id = request.form['class_id']
    name = request.form['name']
    marks = request.form['marks']
    sheet_link = request.form.get('sheet_link', '')

    qp_file = request.files.get('qp_file')
    scheme_file = request.files.get('scheme_file')
    if not is_pdf(qp_file) or not is_pdf(scheme_file):
        return "Both the Question Paper and the Answer Key must be PDF files.", 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    if not get_owned_class(cursor, class_id):
        conn.close()
        return "<h1>Class Not Found</h1>", 404

    qp_filename, qp_path = save_upload(qp_file)
    scheme_filename, _ = save_upload(scheme_file)

    try:
        cursor.execute(
            """INSERT INTO exams (class_id, name, total_marks, qp_path,
                                  scheme_path, sheet_link)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (class_id, name, marks, qp_filename, scheme_filename, sheet_link))
        exam_id = cursor.lastrowid

        print("Request 1: Analyzing QP...")
        print(f"Uploading {os.path.basename(qp_path)}...")
        qp_ai = genai.upload_file(qp_path, mime_type="application/pdf")
        time.sleep(5)

        # Prompt to extract the question paper structure as JSON
        prompt = """
        You are an Exam Structure Architect. Convert this Question Paper into a structured JSON.

        CRITICAL HIERARCHY RULES:
        1. CHECK INSTRUCTIONS FIRST:
           - If a section says "Answer ALL questions", 'or_group_id' MUST be null (Compulsory).
           - Only use 'or_group_id' if you explicitly see "OR" or "Answer any X".

        2. CHOICE (Q3 OR Q4):
           - Set same 'or_group_id' (e.g. 100).
           - Set 'pick_count' to 1.
           - Assign 'sub_unit_id' (e.g., "UNIT_Q3") to keep sub-parts together.

        3. SECTION CHOICE (Answer any 2):
           - Same 'or_group_id', 'pick_count' = 2, 'sub_unit_id' null.

        Output STRICT JSON:
        [
          {"q_label": "Q1", "max_marks": 5, "or_group_id": null, "sub_unit_id": null, "pick_count": 0},
          {"q_label": "Q3(a)", "max_marks": 10, "or_group_id": 100, "sub_unit_id": "UNIT_Q3", "pick_count": 1},
          {"q_label": "Q3(b)", "max_marks": 10, "or_group_id": 100, "sub_unit_id": "UNIT_Q3", "pick_count": 1},
          {"q_label": "Q4(a)", "max_marks": 10, "or_group_id": 100, "sub_unit_id": "UNIT_Q4", "pick_count": 1}
        ]
        """

        response = generate_safe([qp_ai], prompt)
        print(f"AI Response: {response.text}")
        questions = extract_json(response.text)

        if not questions or not isinstance(questions, list):
            conn.rollback()  # undo the exam insert
            conn.close()
            return "AI failed to read the Question Paper.", 500

        for q in questions:
            pick = q.get('pick_count')
            cursor.execute(
                """INSERT INTO exam_questions
                   (exam_id, q_label, max_marks, or_group_id, sub_unit_id, pick_count)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (exam_id, q.get('q_label'), q.get('max_marks'),
                 q.get('or_group_id'), q.get('sub_unit_id'),
                 1 if pick is None else pick))

        conn.commit()
    except Exception as e:
        print(f"API Error: {e}")
        conn.rollback()
        conn.close()
        return f"API Error: {e}", 500

    conn.close()
    return redirect(url_for('class_view', class_id=class_id))


@app.route('/edit_exam', methods=['POST'])
@login_required
def edit_exam():
    exam_id = request.form['exam_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    exam = get_owned_exam(cursor, exam_id)
    if not exam:
        conn.close()
        return "<h1>Exam Not Found</h1>", 404

    cursor.execute(
        """UPDATE exams SET name = %s, total_marks = %s, sheet_link = %s
           WHERE id = %s""",
        (request.form['name'], request.form['total_marks'],
         request.form.get('sheet_link', ''), exam_id))
    conn.commit()
    conn.close()
    return redirect(url_for('class_view', class_id=exam['class_id']))


@app.route('/delete_exam/<int:exam_id>')
@login_required
def delete_exam(exam_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    exam = get_owned_exam(cursor, exam_id)
    if not exam:
        conn.close()
        return redirect(url_for('dashboard'))
    cursor.execute("DELETE FROM exams WHERE id = %s", (exam_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('class_view', class_id=exam['class_id']))


# ---------------------------------------------------------------------------
# Students and AI grading
# ---------------------------------------------------------------------------
@app.route('/add_student', methods=['POST'])
@login_required
def add_student():
    """Upload a student's answer booklet and grade it with Gemini."""
    exam_id = request.form['exam_id']
    pdf_file = request.files.get('answer_pdf')
    if not is_pdf(pdf_file):
        return "The answer booklet must be a PDF file.", 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    exam = get_owned_exam(cursor, exam_id)
    if not exam:
        conn.close()
        return "<h1>Exam Not Found</h1>", 404

    filename, path = save_upload(pdf_file)

    cursor.execute(
        """INSERT INTO students (exam_id, name, roll_no, answer_pdf_path)
           VALUES (%s, %s, %s, %s)""",
        (exam_id, request.form['name'], request.form['roll'], filename))
    student_id = cursor.lastrowid

    cursor.execute("SELECT * FROM exam_questions WHERE exam_id = %s",
                   (exam_id,))
    questions = cursor.fetchall()

    print("Request 2: Grading...")
    try:
        student_ai = genai.upload_file(path, mime_type="application/pdf")
        time.sleep(2)
        scheme_path = os.path.join(app.config['UPLOAD_FOLDER'],
                                   exam['scheme_path'])
        scheme_ai = genai.upload_file(scheme_path,
                                      mime_type="application/pdf")
        time.sleep(2)

        # 1. Structure of the exam for the AI
        structure_str = json.dumps(questions, default=str)

        # 2. Valid labels from the DB
        valid_labels = [q['q_label'] for q in questions]
        labels_str = ", ".join(f'"{lbl}"' for lbl in valid_labels)
        first_label = valid_labels[0] if valid_labels else "1"

        # Grading prompt
        prompt = f """
        ROLE: Strict University Professor who is correcting Answer booklet of student trying their best to score good marks.
        TASK: Grade the student script strictly based on the Max Marks available. If the student shows potential to score high marks, you help them achieve maximum marks by giving extra marks only for those questions that you feel deserved some additional marks. For Half range marks you show less liniency than high.

        EXAM DATA: {structure_str}

        CRITICAL INSTRUCTION - KEYS:
        You must output a JSON object where the keys match the question labels EXACTLY.
        Allowed Keys: [{labels_str}]

        Do NOT add "Q" prefixes if they are not in the list above.
        (e.g. If the list says "1", do NOT output "Q1". Output "1".)

        CRITICAL GRADING RUBRIC:
        1. **THE "LIST vs EXPLAIN" RULE**:
           - If a question asks to "Explain", "Discuss", or "Describe" (worth 4+ marks) and the student only provides a **List** or **Bullet points** without sentences:
           - **MAXIMUM SCORE IS 50%**. (e.g., if Max is 5, give 2.5).

        2. **THE VOLUME PENALTY (Graduated)**:
           - **10 Mark Questions**: Requires 3+ paragraphs or detailed steps. One-liners get max **2 marks**.
           - **4-6 Mark Questions**: Requires 2-3 sentences minimum. One-liners get max **1.5 marks**.
           - **Definition Questions (2-3 Marks)**: One precise sentence is acceptable for full marks.

        3. **KEYWORD PRECISION**:
           - Student answers must contain specific technical keywords from the Answer Key.
           - Synonyms are okay, but generic descriptions ("it manages stuff") get 0.

        Output STRICT JSON: {{"{first_label}": {{"text": "...", "score": 2.5}}, ...}}
        """

        response = generate_safe([student_ai, scheme_ai], prompt)
        print(f"AI Response: {response.text}")
        ai_data = extract_json(response.text)
        if not isinstance(ai_data, dict):
            ai_data = {}

        # Normalize AI keys so they match the DB labels
        normalized_ai_data = {}
        for key, val in ai_data.items():
            base_key = str(key).replace(" ", "").replace(".", "").upper()
            normalized_ai_data[base_key] = val
            if base_key.startswith("Q"):
                no_q_key = base_key[1:]
                if no_q_key:
                    normalized_ai_data[no_q_key] = val
            else:
                normalized_ai_data["Q" + base_key] = val

        for q in questions:
            clean_lbl = q['q_label'].replace(" ", "").replace(".", "").upper()
            d = normalized_ai_data.get(clean_lbl)

            if isinstance(d, dict):
                try:
                    raw_score = float(d.get('score', 0))
                except (ValueError, TypeError):
                    raw_score = 0.0
                max_m = float(q['max_marks'])
                # Ceiling: AI can never award more than the max marks
                final_score = max(0.0, min(raw_score, max_m))
                text = d.get('text', '')
            else:
                final_score = 0
                text = "Not Found"

            cursor.execute(
                """INSERT INTO student_answers
                   (student_id, question_id, ocr_text, ai_score, final_score)
                   VALUES (%s, %s, %s, %s, %s)""",
                (student_id, q['id'], text, final_score, final_score))

        calculate_total(student_id, conn)

    except Exception as e:
        print(f"Grading Failed: {e}")

    conn.commit()
    conn.close()
    return redirect(url_for('exam_view', exam_id=exam_id))


def calculate_total(student_id, conn):
    """Compute a student's total, applying OR-group / pick-count rules."""
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """SELECT sa.final_score, eq.or_group_id, eq.sub_unit_id, eq.pick_count
           FROM student_answers sa
           JOIN exam_questions eq ON sa.question_id = eq.id
           WHERE sa.student_id = %s""", (student_id,))
    marks_data = cursor.fetchall()

    total = 0
    # structure: { group_id: { sub_unit_id: total_score_for_unit } }
    logic_groups = {}
    pick_counts = {}

    for idx, row in enumerate(marks_data):
        score = row['final_score'] or 0
        grp = row['or_group_id']
        unit = row['sub_unit_id']
        pick = row['pick_count']

        if grp is None:
            # Compulsory question
            total += score
        else:
            if grp not in logic_groups:
                logic_groups[grp] = {}
                pick_counts[grp] = pick

            # If there is no unit id, treat the question as its own unit
            unit_key = unit if unit else f"SINGLE_Q_{idx}"
            logic_groups[grp][unit_key] = logic_groups[grp].get(unit_key, 0) + score

    # For each choice group, keep only the best N units
    for grp, units in logic_groups.items():
        limit = pick_counts[grp] or 1  # guard against pick_count of 0/None
        best_scores = sorted(units.values(), reverse=True)[:limit]
        total += sum(best_scores)

    cursor.execute("UPDATE students SET total_obtained = %s WHERE id = %s",
                   (total, student_id))
    conn.commit()


@app.route('/evaluate/<int:student_id>')
@login_required
def evaluate(student_id):
    """Show a student's answers, AI marks and manual override inputs."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    student = get_owned_student(cursor, student_id)
    if not student:
        conn.close()
        return "<h1>Student Not Found</h1>", 404

    exam = get_owned_exam(cursor, student['exam_id'])
    cursor.execute(
        """SELECT sa.*, eq.q_label, eq.max_marks
           FROM student_answers sa
           JOIN exam_questions eq ON sa.question_id = eq.id
           WHERE sa.student_id = %s ORDER BY eq.id""", (student_id,))
    answers = cursor.fetchall()
    conn.close()

    return render_template('evaluation.html', student=student,
                           answers=answers, exam=exam)


@app.route('/update_mark', methods=['POST'])
@login_required
def update_mark():
    """AJAX route: manual mark override, then recalculate the total."""
    data = request.get_json(silent=True) or {}
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        """SELECT sa.student_id, eq.max_marks
           FROM student_answers sa
           JOIN exam_questions eq ON sa.question_id = eq.id
           WHERE sa.id = %s""", (data.get('answer_id'),))
    row = cursor.fetchone()
    if not row or not get_owned_student(cursor, row['student_id']):
        conn.close()
        return jsonify({"success": False}), 403

    try:
        score = max(0.0, min(float(data['score']), float(row['max_marks'])))
    except (ValueError, TypeError, KeyError):
        conn.close()
        return jsonify({"success": False}), 400

    cursor.execute("UPDATE student_answers SET final_score = %s WHERE id = %s",
                   (score, data['answer_id']))
    calculate_total(row['student_id'], conn)

    cursor.execute("SELECT total_obtained FROM students WHERE id = %s",
                   (row['student_id'],))
    new_total = cursor.fetchone()['total_obtained']
    conn.close()
    return jsonify({"success": True, "new_total": new_total})


@app.route('/edit_student', methods=['POST'])
@login_required
def edit_student():
    student_id = request.form['student_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    student = get_owned_student(cursor, student_id)
    if not student:
        conn.close()
        return "<h1>Student Not Found</h1>", 404

    cursor.execute("UPDATE students SET name = %s, roll_no = %s WHERE id = %s",
                   (request.form['name'], request.form['roll_no'], student_id))
    conn.commit()
    conn.close()
    return redirect(url_for('exam_view', exam_id=student['exam_id']))


@app.route('/delete_student/<int:student_id>')
@login_required
def delete_student(student_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    student = get_owned_student(cursor, student_id)
    if not student:
        conn.close()
        return redirect(url_for('dashboard'))

    # student_answers rows are removed automatically (ON DELETE CASCADE)
    cursor.execute("DELETE FROM students WHERE id = %s", (student_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('exam_view', exam_id=student['exam_id']))


if __name__ == '__main__':
    # Debug mode only when explicitly enabled (local development)
    app.run(debug=os.getenv("FLASK_DEBUG") == "1")
