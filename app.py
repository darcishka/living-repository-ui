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
import google.generativeai as genai
import re


app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.secret_key = "super-secret-key"  # change this in production!
genai.configure(api_key="AIzaSyAYH1bmWz4hI1s2rgFXvAR5ygtOmoXf4Cs")
model = genai.GenerativeModel("Gemini 2.5-Flash-Lite")

# ------------------ Functions -----------------------


# --- Tags ---
def generate_tags(text):
    """Use Gemini to generate tags from document text."""
    try:
        model = genai.GenerativeModel("gemini-2.5-flash-lite")
        prompt = f"Extract 5-10 concise topic tags for the following document, respond with the tags only, seperated by commas:\n\n{text[:3000]}"
        response = model.generate_content(prompt)
        tags = response.text.strip().split(",")
        return [t.strip() for t in tags if t.strip()]
    except Exception as e:
        print("Tagging error:", e)
        return []

def get_or_create_tag(cur, label, category="auto"):
    """Fetch a tag_id if exists, otherwise create one with a UUID."""
    # Check if tag already exists
    cur.execute("SELECT tag_id FROM Tag WHERE label = %s", (label,))
    row = cur.fetchone()
    if row:
        return row["tag_id"]

    # Generate UUID and insert new tag
    new_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO Tag (tag_id, label, category) VALUES (%s, %s, %s)",
        (new_id, label, category)
    )
    return new_id


# --- Extract Text ---
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
        host="110.147.201.243",
        port=3306,
        user="root",
        passwd="4pplec4r7b$77ery",
        db="living_repository"
    )



# ------------------ Pages / Routes -----------------------
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
    return redirect(url_for("index"))

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

    # Render the template with chatbox included
    return render_template(
        "project_detail.html",
        project_id=project_id,
        project_title=project["title"],
        project_description=project["description"],
        documents=documents,
        current_year=datetime.datetime.now().year
    )

@app.route("/project/<project_id>/chat", methods=["POST"])
def project_chat(project_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user_message = request.json.get("message", "")

    conn = get_db()
    cur = conn.cursor(MySQLdb.cursors.DictCursor)

    # Collect docs & tags for context
    cur.execute("""
        SELECT d.title, d.ocr_text, GROUP_CONCAT(t.label) as tags
        FROM Document d
        LEFT JOIN Document_Tag dt ON d.doc_id = dt.document_id
        LEFT JOIN Tag t ON dt.tag_id = t.tag_id
        JOIN Project_Document pd ON d.doc_id = pd.document_id
        WHERE pd.project_id = %s
        GROUP BY d.doc_id
    """, (project_id,))
    docs = cur.fetchall()
    print(docs)
    cur.close()
    conn.close()

    # Build context string
    context_parts = []
    for d in docs:
        tags_str = f" [tags: {d['tags']}]" if d['tags'] else ""
        context_parts.append(f"Document: {d['title']}{tags_str}\n{d.get('ocr_text','')[:1000]}")

    context = "\n\n".join(context_parts)

    # Gemini request
    try:
        prompt = f"""
        You are assisting a user with project documents.

        Project Documents:
        {context}

        User Question: {user_message}
        """
        model = genai.GenerativeModel("gemini-2.5-flash-lite")
        response = model.generate_content(prompt)
        reply = response.text.strip()
    except Exception as e:
        print("Chat error:", e)
        reply = "Sorry, I had trouble generating a response."

    return jsonify({"reply": reply})
    
@app.route("/project/<project_id>/upload", methods=["POST"])
def project_upload(project_id):
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    conn = get_db()
    cur = conn.cursor(MySQLdb.cursors.DictCursor)

    file = request.files["file"]
    title = request.form["title"]
    description = request.form.get("description")
    privacy = request.form["privacy"]
    user_id = session["user_id"]

    filename = secure_filename(file.filename)
    path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(path)

    # Detect type + OCR
    ext = filename.split(".")[-1].lower()
    if ext in ["pdf"]:
        doc_type = "pdf"
        ocr_text = extract_pdf_text(path)
    elif ext in ["doc", "docx"]:
        doc_type = "word"
        ocr_text = extract_word_text(path)
    elif ext in ["jpg", "jpeg", "png", "tiff"]:
        doc_type = "image"
        ocr_text = pytesseract.image_to_string(Image.open(path))
    else:
        doc_type = "other"
        ocr_text = ""

    # Clean up OCR text    
    ocr_text = re.sub(r"\n{2,}", "\n", ocr_text).strip()
    # Generate tags with Gemini
    tags = generate_tags(ocr_text or description or title)

    # Insert document
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

    # Link document to project
    cur.execute("""
        INSERT INTO Project_Document (project_id, document_id)
        VALUES (%s,%s)
    """, (project_id, doc_id))

    # Insert tags and link them
    for tag in tags:
        tag_id = get_or_create_tag(cur, tag)
        cur.execute(
            "INSERT INTO Document_Tag (document_id, tag_id) VALUES (%s, %s)",
            (doc_id, tag_id)
        )

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"success": True, "doc_id": doc_id, "title": title, "tags": tags})

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

    # Project documents with tags
    cur.execute("""
        SELECT d.doc_id,
               d.title,
               d.upload_date,
               u.name AS author,
               d.status,
               GROUP_CONCAT(t.label) AS tags
        FROM Document d
        JOIN Project_Document pd ON d.doc_id = pd.document_id
        LEFT JOIN User u ON d.uploader_id = u.user_id
        LEFT JOIN Document_Tag dt ON d.doc_id = dt.document_id
        LEFT JOIN Tag t ON dt.tag_id = t.tag_id
        WHERE pd.project_id = %s
        GROUP BY d.doc_id
        ORDER BY d.upload_date DESC
    """, (project_id,))
    documents = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "ingestion.html",
        project=project,
        project_id=project_id,
        documents=documents
    )

@app.route("/project/<project_id>/document/<doc_id>/process", methods=["POST"])
def process_document(project_id, doc_id):
    if "user_id" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    conn = get_db()
    cur = conn.cursor(MySQLdb.cursors.DictCursor)

    try:
        # --- get document text ---
        cur.execute("SELECT ocr_text FROM Document WHERE doc_id=%s", (doc_id,))
        doc = cur.fetchone()
        if not doc or not doc["ocr_text"]:
            return jsonify({"success": False, "error": "Document has no text"}), 400

        # --- get project context ---
        cur.execute("SELECT title, description FROM Project WHERE project_id=%s", (project_id,))
        project = cur.fetchone()
        if not project:
            return jsonify({"success": False, "error": "Project not found"}), 404

        # --- generate contextual summary with Gemini ---
        model = genai.GenerativeModel("gemini-2.5-flash-lite")
        prompt = f"""
        Project: {project['title']}
        Project Description: {project['description']}

        Document Text:
        {doc['ocr_text'][:6000]}

        Task: Write a concise summary (3–5 sentences) of this document,
        emphasizing only the parts relevant to the project’s goals and context, prioritize relevant statistics above all.
        """
        response = model.generate_content(prompt)
        summary = response.text.strip() if response and response.text else None

        if not summary:
            return jsonify({"success": False, "error": "AI did not return summary"}), 500

        # --- update Project_Document contextual_summary ---
        cur.execute("""
            UPDATE Project_Document
            SET contextual_summary=%s
            WHERE project_id=%s AND document_id=%s
        """, (summary, project_id, doc_id))

        # --- update Document status ---
        cur.execute("""
            UPDATE Document
            SET status=%s
            WHERE doc_id=%s
        """, ("Complete", doc_id))

        conn.commit()

        return jsonify({"success": True, "summary": summary})

    except Exception as e:
        conn.rollback()
        print("Error processing doc:", e)
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    app.run(debug=True)



