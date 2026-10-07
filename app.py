from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import mysql.connector
import google.generativeai as genai
import os
import time
import json
import re
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("FLASK_SECRET_KEY is not set. Copy .env.example to .env and fill it in.")

#Configuring upload folder
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

#Setting up the api key for genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

#Database connection function
def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "smart_exam_db"),
    )

#Used for testing API connectivity and available models.
def generate_safe(inputs, prompt):
    models_to_try = ['gemini-flash-latest']
    for model_name in models_to_try:
        try:
            print(f"🤖 Connecting to AI Model: {model_name}...")
            model = genai.GenerativeModel(model_name)
            for attempt in range(3):
                try:
                    response = model.generate_content(inputs + [prompt])
                    return response
                except Exception as e:
                    if "429" in str(e):
                        print(f"⚠️ Quota Hit. Waiting 15s... (Attempt {attempt+1})")
                        time.sleep(15)
                        continue
                    else:
                        break
        except Exception as e:
            continue
    raise ValueError("All AI Models failed.")

#Json extraction function that can handle both list and dict formats.
def extract_json(text):
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        start = text.find('[')
        end = text.rfind(']') + 1
        if start != -1 and end != -1: return json.loads(text[start:end])
        start = text.find('{')
        end = text.rfind('}') + 1
        if start != -1 and end != -1: return json.loads(text[start:end])
        return None
    except:
        return None

#Core routes below

#For index page
@app.route('/')
def index():
    return render_template('index.html')

#to reset the database and undo changes
@app.route('/reset_db')
def reset_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        #Drop old tables
        cursor.execute("DROP TABLE IF EXISTS student_answers")
        cursor.execute("DROP TABLE IF EXISTS students")
        cursor.execute("DROP TABLE IF EXISTS exam_questions")
        cursor.execute("DROP TABLE IF EXISTS exams")
        cursor.execute("DROP TABLE IF EXISTS classes")
        
        #Recreate tables to the base structure
        cursor.execute("""
            CREATE TABLE classes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                teacher_id INT,
                name VARCHAR(255),
                subject VARCHAR(255),
                semester VARCHAR(50),
                year VARCHAR(10)
            )
        """)
        cursor.execute("""
            CREATE TABLE exams (
                id INT AUTO_INCREMENT PRIMARY KEY,
                class_id INT,
                name VARCHAR(255),
                total_marks INT,
                qp_path VARCHAR(255),
                scheme_path VARCHAR(255),
                sheet_link VARCHAR(255)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE exam_questions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                exam_id INT,
                q_label VARCHAR(50),
                max_marks FLOAT,
                or_group_id INT NULL,
                sub_unit_id VARCHAR(50) NULL,
                pick_count INT DEFAULT 1
            )
        """)
        
        cursor.execute("""
            CREATE TABLE students (
                id INT AUTO_INCREMENT PRIMARY KEY,
                exam_id INT,
                name VARCHAR(255),
                roll_no VARCHAR(50),
                answer_pdf_path VARCHAR(255),
                total_obtained FLOAT DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE student_answers (
                id INT AUTO_INCREMENT PRIMARY KEY,
                student_id INT,
                question_id INT,
                ocr_text TEXT,
                ai_score FLOAT,
                final_score FLOAT
            )
        """)
        
        conn.commit()
        conn.close()
        return "<h1>Database Reset & Upgraded. <a href='/dashboard'>Go to Dashboard</a></h1>"
    except Exception as e:
        return f"<h1>Reset Failed: {e}</h1>"

#For signup
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO teachers (name, email, password) VALUES (%s, %s, %s)", 
                       (request.form['name'], request.form['email'], request.form['password']))
        conn.commit()
        conn.close()
        return redirect(url_for('login'))
    return render_template('signup.html')

#for login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM teachers WHERE email = %s AND password = %s", 
                       (request.form['email'], request.form['password']))
        user = cursor.fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            return redirect(url_for('dashboard'))
    return render_template('login.html')

#for logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

#for dashboard
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM classes WHERE teacher_id = %s", (session['user_id'],))
    classes = cursor.fetchall()
    conn.close()
    return render_template('dashboard.html', classes=classes, user=session['user_name'])

#profile editing route
@app.route('/edit_profile', methods=['POST'])
def edit_profile():
    if 'user_id' not in session: return redirect(url_for('login'))
    new_name = request.form['name']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE teachers SET name = %s WHERE id = %s", (new_name, session['user_id']))
    conn.commit()
    conn.close()
    session['user_name'] = new_name 
    return redirect(url_for('dashboard'))

#class management routes
@app.route('/add_class', methods=['POST'])
def add_class():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO classes (teacher_id, name, subject, semester, year) VALUES (%s, %s, %s, %s, %s)",
                   (session['user_id'], request.form['name'], request.form['subject'], request.form['sem'], request.form['year']))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

#for deleting a class completely
@app.route('/delete_class/<int:class_id>')
def delete_class(class_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM classes WHERE id = %s", (class_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

#for editing class details
@app.route('/edit_class', methods=['POST'])
def edit_class():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    class_id = request.form['class_id']
    name = request.form['name']
    subject = request.form['subject']
    semester = request.form['sem']
    year = request.form['year']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE classes 
        SET name = %s, subject = %s, semester = %s, year = %s 
        WHERE id = %s
    """, (name, subject, semester, year, class_id))
    
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

#for viewing inside class
@app.route('/class/<int:class_id>')
def class_view(class_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM classes WHERE id = %s", (class_id,))
    class_info = cursor.fetchone()
    cursor.execute("SELECT * FROM exams WHERE class_id = %s", (class_id,))
    exams = cursor.fetchall()
    conn.close()
    return render_template('class_view.html', class_info=class_info, exams=exams)

#for viewing inside exams where the students are
@app.route('/exam/<int:exam_id>')
def exam_view(exam_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM exams WHERE id = %s", (exam_id,))
    exam = cursor.fetchone()
    
    if not exam:
        return "<h1>Exam Not Found</h1>", 404
        
    # --- FIXED: Sorted numerically using CAST and eliminated duplicates ---
    cursor.execute("SELECT * FROM students WHERE exam_id = %s ORDER BY CAST(roll_no AS UNSIGNED) ASC", (exam_id,))
    raw_students = cursor.fetchall()
    
    seen_rolls = set()
    students = []
    for student in raw_students:
        if student['roll_no'] not in seen_rolls:
            students.append(student)
            seen_rolls.add(student['roll_no'])
    # --------------------------------------------------------------------

    conn.close()
    return render_template('exam_view.html', exam=exam, students=students)

#to add exam using AI integration for question paper analysis and structure extraction.
@app.route('/add_exam', methods=['POST'])
def add_exam():
    class_id = request.form['class_id']
    name = request.form['name']
    marks = request.form['marks']
    sheet_link = request.form.get('sheet_link', '')

    qp_file = request.files['qp_file']
    scheme_file = request.files['scheme_file']
    
    qp_filename = secure_filename(qp_file.filename)
    scheme_filename = secure_filename(scheme_file.filename)
    qp_path = os.path.join(app.config['UPLOAD_FOLDER'], qp_filename)
    scheme_path = os.path.join(app.config['UPLOAD_FOLDER'], scheme_filename)
    qp_file.save(qp_path)
    scheme_file.save(scheme_path)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO exams (class_id, name, total_marks, qp_path, scheme_path, sheet_link) VALUES (%s, %s, %s, %s, %s, %s)",
            (class_id, name, marks, qp_filename, scheme_filename, sheet_link)
        )
        exam_id = cursor.lastrowid
    except Exception as e:
        return f"Database Error: {e}"

    print("🧠 Request 1: Analyzing QP...")
    try:
        print(f"☁️ Uploading {os.path.basename(qp_path)}...")
        qp_ai = genai.upload_file(qp_path, mime_type="application/pdf")
        time.sleep(5) 

        #Promt to generate the database in JSON format for the questionpaper
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

        if not questions: 
            cursor.execute("DELETE FROM exams WHERE id = %s", (exam_id,))
            conn.commit()
            return f"❌ AI failed to read Question Paper."

        for q in questions:
            cursor.execute("""
                INSERT INTO exam_questions (exam_id, q_label, max_marks, or_group_id, sub_unit_id, pick_count) 
                VALUES (%s, %s, %s, %s, %s, %s)""",
                (exam_id, q.get('q_label'), q.get('max_marks'), q.get('or_group_id'), q.get('sub_unit_id'), q.get('pick_count', 1)))

    except Exception as e:
        print(f"API Error: {e}")
        cursor.execute("DELETE FROM exams WHERE id = %s", (exam_id,))
        conn.commit()
        return f"API Error: {e}"

    conn.commit()
    conn.close()
    return redirect(url_for('class_view', class_id=class_id))

@app.route('/delete_exam/<int:exam_id>')
def delete_exam(exam_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT class_id FROM exams WHERE id = %s", (exam_id,))
    data = cursor.fetchone()
    if data:
        class_id = data[0]
        cursor.execute("DELETE FROM exams WHERE id = %s", (exam_id,))
        conn.commit()
        return redirect(url_for('class_view', class_id=class_id))
    conn.close()
    return redirect(url_for('dashboard'))

#For adding students and their answer sheets, and along the grading process using AI.
@app.route('/add_student', methods=['POST'])
def add_student():
    exam_id = request.form['exam_id']
    pdf_file = request.files['answer_pdf']
    filename = secure_filename(pdf_file.filename)
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    pdf_file.save(path)
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("INSERT INTO students (exam_id, name, roll_no, answer_pdf_path) VALUES (%s, %s, %s, %s)",
                   (exam_id, request.form['name'], request.form['roll'], filename))
    student_id = cursor.lastrowid
    
    cursor.execute("SELECT * FROM exams WHERE id = %s", (exam_id,))
    exam = cursor.fetchone()
    cursor.execute("SELECT * FROM exam_questions WHERE exam_id = %s", (exam_id,))
    questions = cursor.fetchall()
    
    print("🧠 Request 2: Grading...")
    try:
        student_ai = genai.upload_file(path, mime_type="application/pdf")
        time.sleep(2)
        scheme_path = os.path.join(app.config['UPLOAD_FOLDER'], exam['scheme_path'])
        scheme_ai = genai.upload_file(scheme_path, mime_type="application/pdf")
        time.sleep(2)

        # 1. Prepare the structure for the AI
        structure_str = json.dumps(questions, default=str)
        
        # 2. Extract labels given in the DB
        valid_labels = [q['q_label'] for q in questions]
        labels_str = ", ".join(f'"{lbl}"' for lbl in valid_labels)

        #Prompt for grading 
        prompt = f"""
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
        

        Output STRICT JSON: {{"{valid_labels[0]}": {{"text": "...", "score": 2.5}}, ...}}
        """
        
        response = generate_safe([student_ai, scheme_ai], prompt)
        print(f"AI Response: {response.text}")
        ai_data = extract_json(response.text)
        if not ai_data: ai_data = {}

        #matching the AI output with the questions and inserting into DB
        normalized_ai_data = {}
        for key, val in ai_data.items():
            # Normalize keys just in case AI messes up
            base_key = key.replace(" ", "").replace(".", "").upper()
            normalized_ai_data[base_key] = val
            
            if base_key.startswith("Q"):
                no_q_key = base_key[1:]
                if no_q_key: normalized_ai_data[no_q_key] = val
            else:
                with_q_key = "Q" + base_key
                normalized_ai_data[with_q_key] = val

        for q in questions:
            lbl = q['q_label']
            clean_lbl = lbl.replace(" ", "").replace(".", "").upper()
            
            d = None
            if clean_lbl in normalized_ai_data:
                d = normalized_ai_data[clean_lbl]
            
            if d:
                raw_score = float(d.get('score', 0))
                max_m = float(q['max_marks'])
                final_score = min(raw_score, max_m)
                
                cursor.execute("""
                    INSERT INTO student_answers (student_id, question_id, ocr_text, ai_score, final_score) 
                    VALUES (%s, %s, %s, %s, %s)""",
                    (student_id, q['id'], d.get('text', ''), final_score, final_score))
            else:
                cursor.execute("""
                    INSERT INTO student_answers (student_id, question_id, ocr_text, ai_score, final_score) 
                    VALUES (%s, %s, %s, %s, %s)""", 
                    (student_id, q['id'], "Not Found", 0, 0))

        calculate_total(student_id, conn)

    except Exception as e:
        print(f"❌ Grading Failed: {e}")
    
    conn.commit()
    conn.close()
    return redirect(url_for('exam_view', exam_id=exam_id))

#Full marks calculation logic
def calculate_total(student_id, conn):
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT sa.final_score, eq.or_group_id, eq.sub_unit_id, eq.pick_count 
        FROM student_answers sa 
        JOIN exam_questions eq ON sa.question_id = eq.id 
        WHERE sa.student_id = %s
    """, (student_id,))
    marks_data = cursor.fetchall()
    
    total = 0
    #structure: { group_id: { sub_unit_id: total_score_for_unit } }
    logic_groups = {} 
    pick_counts = {}

    for row in marks_data:
        score = row['final_score']
        grp = row['or_group_id']
        unit = row['sub_unit_id']
        pick = row['pick_count']

        if grp is None:
            #for compulsory questions
            total += score
        else:
            if grp not in logic_groups:
                logic_groups[grp] = {}
                pick_counts[grp] = pick
            
            # If no unit ID, treat as unique unit
            unit_key = unit if unit else f"SINGLE_Q_{row['final_score']}_{time.time()}"
            
            if unit_key not in logic_groups[grp]:
                logic_groups[grp][unit_key] = 0
            
            # Sum marks for this particular unit
            logic_groups[grp][unit_key] += score

    # Logic: For each choice group, pick the best N units
    for grp, units in logic_groups.items():
        limit = pick_counts[grp]
        # Get list of totals for each unit
        unit_scores = list(units.values())
        unit_scores.sort(reverse=True)
        # Sum the top N units
        best_scores = unit_scores[:limit]
        total += sum(best_scores)
        
    cursor.execute("UPDATE students SET total_obtained = %s WHERE id = %s", (total, student_id))
    conn.commit()

#Route to evaluate a student's answers and show the breakdown, along with options to adjust marks.
#also to see the question paper and scheme again.
@app.route('/evaluate/<int:student_id>')
def evaluate(student_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # 1. Get Student
    cursor.execute("SELECT * FROM students WHERE id = %s", (student_id,))
    student = cursor.fetchone()
    
    # 2. Get Exam Details for the student
    cursor.execute("SELECT * FROM exams WHERE id = %s", (student['exam_id'],))
    exam = cursor.fetchone()
    
    # 3. Get Answers
    cursor.execute("""
        SELECT sa.*, eq.q_label, eq.max_marks 
        FROM student_answers sa 
        JOIN exam_questions eq ON sa.question_id = eq.id 
        WHERE sa.student_id = %s ORDER BY eq.id
    """, (student_id,))
    answers = cursor.fetchall()
    
    conn.close()
    
    # Pass 'exam' to the template
    return render_template('evaluation.html', student=student, answers=answers, exam=exam)

#API route to update marks after manual adjustment, and to recalculate totals accordingly.
@app.route('/update_mark', methods=['POST'])
def update_mark():
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE student_answers SET final_score = %s WHERE id = %s", (data['score'], data['answer_id']))
    
    cursor.execute("SELECT student_id FROM student_answers WHERE id = %s", (data['answer_id'],))
    student_id = cursor.fetchone()[0]
    
    calculate_total(student_id, conn)
    
    cursor.execute("SELECT total_obtained FROM students WHERE id = %s", (student_id,))
    new_total = cursor.fetchone()[0]
    conn.close()
    return jsonify({"success": True, "new_total": new_total})

#for editing students.
@app.route('/edit_student', methods=['POST'])
def edit_student():
    student_id = request.form['student_id']
    new_name = request.form['name']
    new_roll = request.form['roll_no']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE students SET name = %s, roll_no = %s WHERE id = %s", 
                   (new_name, new_roll, student_id))
    conn.commit()
    
    # Get exam_id to redirect back
    cursor.execute("SELECT exam_id FROM students WHERE id = %s", (student_id,))
    exam_id = cursor.fetchone()[0]
    conn.close()
    
    return redirect(url_for('exam_view', exam_id=exam_id))

#for deleting a student and their answers.
@app.route('/delete_student/<int:student_id>')
def delete_student(student_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    #Get exam_id first for redirection
    cursor.execute("SELECT exam_id FROM students WHERE id = %s", (student_id,))
    data = cursor.fetchone()
    if not data:
        conn.close()
        return redirect(url_for('dashboard'))
    
    exam_id = data[0]
    
    #Delete student answers first (cleanup)
    cursor.execute("DELETE FROM student_answers WHERE student_id = %s", (student_id,))
    #Delete the student
    cursor.execute("DELETE FROM students WHERE id = %s", (student_id,))
    
    conn.commit()
    conn.close()
    return redirect(url_for('exam_view', exam_id=exam_id))

#for editing exam
@app.route('/edit_exam', methods=['POST'])
def edit_exam():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    exam_id = request.form['exam_id']
    new_name = request.form['name']
    new_marks = request.form['total_marks']
    new_link = request.form.get('sheet_link', '')

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Update the exam details
    cursor.execute("""
        UPDATE exams 
        SET name = %s, total_marks = %s, sheet_link = %s 
        WHERE id = %s
    """, (new_name, new_marks, new_link, exam_id))
    
    # 2. Get class_id to redirect back to the right page
    cursor.execute("SELECT class_id FROM exams WHERE id = %s", (exam_id,))
    class_id = cursor.fetchone()[0]
    
    conn.commit()
    conn.close()
    
    return redirect(url_for('class_view', class_id=class_id))

if __name__ == '__main__':
    app.run(debug=os.getenv("FLASK_DEBUG") == "1")
