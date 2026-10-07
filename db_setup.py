# db_setup.py
import mysql.connector

# CONFIG: Change password if your XAMPP has one (default is empty)
DB_CONFIG = {'host': 'localhost', 'user': 'root', 'password': ''}

def setup_db():
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    # 1. Create Database
    cursor.execute("CREATE DATABASE IF NOT EXISTS smart_exam_db")
    cursor.execute("USE smart_exam_db")
    
    # 2. Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS teachers (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(100),
        email VARCHAR(100) UNIQUE,
        password VARCHAR(255)
    )""")
    
    # 3. Classes Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS classes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        teacher_id INT,
        name VARCHAR(100),
        subject VARCHAR(100),
        semester VARCHAR(20),
        year VARCHAR(20),
        FOREIGN KEY (teacher_id) REFERENCES teachers(id)
    )""")
    
    # 4. Exams Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS exams (
        id INT AUTO_INCREMENT PRIMARY KEY,
        class_id INT,
        name VARCHAR(100),
        total_marks INT,
        qp_path VARCHAR(255),
        scheme_path VARCHAR(255),
        sheet_link VARCHAR(500),  -- Google Sheet Link
        FOREIGN KEY (class_id) REFERENCES classes(id)
    )""")
    
    # 5. Exam Structure (The Skeleton of Questions)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS exam_questions (
        id INT AUTO_INCREMENT PRIMARY KEY,
        exam_id INT,
        q_label VARCHAR(20),      -- e.g., "Q1", "Q2a"
        max_marks FLOAT,
        or_group_id INT NULL,     -- If not NULL, these Qs are choices (OR logic)
        FOREIGN KEY (exam_id) REFERENCES exams(id)
    )""")
    
    # 6. Students Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id INT AUTO_INCREMENT PRIMARY KEY,
        exam_id INT,
        name VARCHAR(100),
        roll_no VARCHAR(50),
        answer_pdf_path VARCHAR(255),
        total_obtained FLOAT DEFAULT 0,
        FOREIGN KEY (exam_id) REFERENCES exams(id)
    )""")
    
    # 7. Student Answers (The AI Data)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS student_answers (
        id INT AUTO_INCREMENT PRIMARY KEY,
        student_id INT,
        question_id INT,          -- Links to exam_questions
        ocr_text TEXT,
        ai_score FLOAT,
        final_score FLOAT,
        teacher_comment TEXT,
        FOREIGN KEY (student_id) REFERENCES students(id),
        FOREIGN KEY (question_id) REFERENCES exam_questions(id)
    )""")
    
    print("✅ Database and Tables Created Successfully!")
    conn.close()

if __name__ == "__main__":
    setup_db()