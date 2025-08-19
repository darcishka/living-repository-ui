import os
import uuid
import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.utils import secure_filename
import MySQLdb
import bcrypt
import pytesseract
from PIL import Image
import fitz
from docx import Document as DocxDocument


app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.secret_key = "super-secret-key"  # change this in production!

def extract_word_text(path):
    text = ""
    doc = DocxDocument(path)
    for para in doc.paragraphs:
        text += para.text + "\n"
    return text

def extract_pdf_text(path):
    text = ""
    pdf = fitz.open(path)
    for page in pdf:
        text += page.get_text()
    pdf.close()
    return text

# --- Database connection helper ---
def get_db():
    return MySQLdb.connect(
        host="1.120.188.119",
        port=3306,
        user="root",
        passwd="4pplec4r7b$77ery",
        db="living_repository"
    )

@app.route("/")
def index():
    # If logged in → skip landing page → go to dashboard
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    # Otherwise → render the landing page
    return render_template("index.html", current_year=datetime.datetime.now().year)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/create_project", methods=["GET", "POST"])
def create_project():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template("create_project.html")

    title = request.form["title"]
    description = request.form["description"]

    project_id = str(uuid.uuid4())

    conn = get_db()
    cur = conn.cursor()

    # Insert into Project
    cur.execute("""
        INSERT INTO Project (project_id, title, description, creation_date)
        VALUES (%s,%s,%s,%s)
    """, (project_id, title, description, datetime.datetime.now()))

    # Also link creator into User_Project (with admin rights)
    cur.execute("""
        INSERT INTO User_Project (user_id, project_id, permission, join_date)
        VALUES (%s,%s,%s,%s)
    """, (session["user_id"], project_id, "admin", datetime.datetime.now()))

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("projects"))

# --- Login route ---
@app.route("/login", methods=["POST", "GET"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    
    email = request.form["email"]
    password = request.form["password"]

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, name, password_hash FROM User WHERE email = %s", (email,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if user is None:
        return "Invalid email or password"

    user_id, name, hashed = user

    if bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8")):
        session["user_id"] = user_id
        session["name"] = name
        return redirect(url_for("dashboard"))   # 👈 send to dashboard now
    else:
        return "Invalid email or password"


# new route for dashboard
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))  # not logged in → go to login
    return render_template("dashboard.html", name=session["name"])

# --- Signup route ---
@app.route("/signup", methods=["POST", "GET"])
def signup():
    if request.method == "GET":
        return render_template("signup.html")

    name = request.form.get("username")
    email = request.form.get("email")
    password = request.form.get("password")

    if not name or not email or not password:
        return "Missing field!"

    user_id = str(uuid.uuid4())
    role = "user"

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM User WHERE email=%s", (email,))
    (exists,) = cursor.fetchone()

    if exists > 0:
        return "Email already taken"

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    cursor.execute(
        "INSERT INTO User (user_id, name, email, role, password_hash) VALUES (%s,%s,%s,%s,%s)",
        (user_id, name, email, role, hashed.decode("utf-8"))
    )
    conn.commit()
    cursor.close()
    conn.close()

    return "Account created successfully! <a href='/login'>Login here</a>"

# ---------------- Projects Page ----------------
@app.route("/projects")
def projects():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    conn = get_db()
    cur = conn.cursor(MySQLdb.cursors.DictCursor)

    # Get all projects for this user
    cur.execute("""
        SELECT p.project_id, p.title, p.description, up.permission
        FROM Project p
        JOIN User_Project up ON p.project_id = up.project_id
        WHERE up.user_id = %s
    """, (user_id,))
    projects = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("projects.html", projects=projects)

@app.route("/projects/add", methods=["GET", "POST"])
def add_project():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template("add_project.html")  # create a form template

    # POST handling
    title = request.form.get("title")
    description = request.form.get("description", "")
    project_id = str(uuid.uuid4())

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO Project (project_id, title, description, creation_date)
        VALUES (%s, %s, %s, %s)
    """, (project_id, title, description, datetime.datetime.now()))

    # Add current user to User_Project junction with 'admin' permission
    cur.execute("""
        INSERT INTO User_Project (user_id, project_id, permission, join_date)
        VALUES (%s, %s, %s, %s)
    """, (session["user_id"], project_id, "admin", datetime.datetime.now()))

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("projects"))


@app.route("/project/<project_id>")
def project_detail(project_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor(MySQLdb.cursors.DictCursor)

    # Get project title & description
    cur.execute("SELECT title, description FROM Project WHERE project_id=%s", (project_id,))
    project = cur.fetchone()
    if not project:
        cur.close()
        conn.close()
        return "Project not found"

    # Get project documents
    cur.execute("""
        SELECT d.doc_id, d.title
        FROM Document d
        JOIN Project_Document pd ON d.doc_id = pd.document_id
        WHERE pd.project_id = %s
    """, (project_id,))
    documents = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "project_detail.html",
        project_id=project_id,
        project_title=project["title"],
        project_description=project["description"],
        documents=documents
    )
    
@app.route("/project/<project_id>/upload", methods=["GET", "POST"])
def project_upload(project_id):
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        file = request.files["file"]
        title = request.form["title"]
        description = request.form.get("description")
        privacy = request.form["privacy"]
        user_id = session["user_id"]

        filename = secure_filename(file.filename)
        path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(path)

        # Detect type
        ext = filename.split(".")[-1].lower()
        if ext in ["pdf"]:
            doc_type = "pdf"
        elif ext in ["doc", "docx"]:
            doc_type = "word"
        elif ext in ["jpg", "jpeg", "png", "tiff"]:
            doc_type = "image"
        else:
            doc_type = "other"

        pytesseract.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"

        # OCR extraction (optional)
        ocr_text = None
        if doc_type == "image":
            ocr_text = pytesseract.image_to_string(Image.open(path))
        elif doc_type == "pdf":
            ocr_text = extract_pdf_text(path)
        elif doc_type == "word":
            ocr_text = extract_word_text(path)

        doc_id = str(uuid.uuid4())

        cur.execute("""
        INSERT INTO Document (doc_id, uploader_id, title, description, url, upload_date, type, ocr_text, privacy_level, status)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            doc_id,
            user_id,
            title,
            description,
            path,
            datetime.datetime.now(),
            doc_type,
            ocr_text,
            privacy,
            "pending"
        ))

        cur.execute("""
        INSERT INTO Project_Document (project_id, document_id)
        VALUES (%s,%s)
        """, (project_id, doc_id))

        conn.commit()
        cur.close()
        conn.close()

        # Return JSON for AJAX
        return jsonify({"success": True, "doc_id": doc_id, "title": title, "description": description})

    # GET requests can still render dashboard
    cur.execute("""
        SELECT d.doc_id, d.title, d.description, d.upload_date, d.status, u.username as author
        FROM Document d
        JOIN Project_Document pd ON d.doc_id = pd.document_id
        LEFT JOIN User u ON d.uploader_id = u.user_id
        WHERE pd.project_id=%s
        ORDER BY d.upload_date DESC
    """, (project_id,))
    documents = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("ingestion.html", project_id=project_id, project={"title": "Example"}, documents=documents)

@app.route("/document/<doc_id>", methods=["GET", "POST"])
def document_detail(doc_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor(MySQLdb.cursors.DictCursor)

    if request.method == "POST":
        # If Delete button pressed
        if "delete" in request.form:
            # First, find project_id to redirect back
            cur.execute("""
                SELECT project_id FROM Project_Document WHERE document_id = %s
            """, (doc_id,))
            row = cur.fetchone()
            project_id = row["project_id"] if row else None

            # Delete document (will also delete metadata, tags, reviews due to ON DELETE CASCADE)
            cur.execute("DELETE FROM Document WHERE doc_id = %s", (doc_id,))
            conn.commit()

            cur.close()
            conn.close()

            if project_id:
                return redirect(url_for("project_detail", project_id=project_id))
            else:
                return redirect(url_for("dashboard"))

    # --- Display Document Details ---
    cur.execute("""
        SELECT d.doc_id, d.title, d.url, d.upload_date, d.type, d.privacy_level, d.ocr_text, 
               u.name as uploader_name, p.project_id, p.title as project_title
        FROM Document d
        LEFT JOIN User u ON d.uploader_id = u.user_id
        LEFT JOIN Project_Document pd ON d.doc_id = pd.document_id
        LEFT JOIN Project p ON pd.project_id = p.project_id
        WHERE d.doc_id = %s
    """, (doc_id,))
    document = cur.fetchone()

    cur.close()
    conn.close()

    return render_template("document_detail.html", document=document)

@app.route("/project/<project_id>/ingestion")
def ingestion(project_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor(MySQLdb.cursors.DictCursor)


    # Project info
    cur.execute("SELECT title, description FROM Project WHERE project_id=%s", (project_id,))
    project = cur.fetchone()

    # Project documents
    cur.execute("""
        SELECT d.doc_id, d.title, d.upload_date, u.name AS author, d.status
        FROM Document d
        JOIN Project_Document pd ON d.doc_id = pd.document_id
        LEFT JOIN User u ON d.uploader_id = u.user_id
        WHERE pd.project_id = %s
        ORDER BY d.upload_date DESC
    """, (project_id,))
    documents = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("ingestion.html",
                           project=project,
                           project_id=project_id,
                           documents=documents)

if __name__ == "__main__":
    app.run(debug=True)